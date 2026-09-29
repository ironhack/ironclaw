#!/usr/bin/env python3
"""Argos Performance Report collector.

3 timeframes (7d/14d/30d) x 4 levels (campaign / ad_group / keyword / ad), each with:
  - standard KPIs (impressions, clicks, cost, conversions, value, CTR, CPC, CPA, ROAS)
  - channel classification (brand / generic / pmax / display) from the campaign name
  - conversions broken down by funnel stage (Apps > QApps > TI > SA > BST)
  - device breakdown (desktop / mobile / tablet), each with its own funnel breakdown
+ auction insights for brand campaigns.

Output:
  - Full dataset written to --out (default /tmp/argos_perf_data.json). This is what
    generate_performance_report.py consumes.
  - A compact summary JSON printed to stdout (totals, channel split, funnel, devices,
    top movers at campaign / ad group / keyword level). This is what the cron job
    injects into the agent prompt for the Slack post. Use --full-stdout to print the
    full dataset instead (legacy behaviour).
"""

import argparse
import json
import os
import sys
import tempfile
from datetime import date, timedelta
from collections import defaultdict

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException


# ── Auth ──────────────────────────────────────────────────────────────
SERVICE_ACCOUNT_INFO = json.loads(os.environ["GOOGLE_APPLICATION_CREDENTIALS_JSON"])
CUSTOMER_IDS = [cid.strip() for cid in os.environ["GADS_CUSTOMER_ID"].split(",") if cid.strip()]
LOGIN_CUSTOMER_ID = os.environ["GOOGLE_ADS_LOGIN_CUSTOMER_ID"]
DEV_TOKEN = os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"]

_keyfile = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
json.dump(SERVICE_ACCOUNT_INFO, _keyfile)
_keyfile.close()

client = GoogleAdsClient.load_from_dict({
    "developer_token": DEV_TOKEN,
    "login_customer_id": LOGIN_CUSTOMER_ID,
    "use_proto_plus": True,
    "json_key_file_path": _keyfile.name,
})

ga_service = client.get_service("GoogleAdsService")


# ── Date ranges ───────────────────────────────────────────────────────
today = date.today()
yesterday = today - timedelta(days=1)


def date_str(d):
    return d.strftime("%Y-%m-%d")


# We query 60 days back from yesterday once per level, then split client-side
QUERY_START = yesterday - timedelta(days=60)
QUERY_END = yesterday
DATE_WHERE = f"segments.date BETWEEN '{date_str(QUERY_START)}' AND '{date_str(QUERY_END)}'"

TIMEFRAMES = {
    "last_7d": {
        "label": "Last 7 Days",
        "current":  (yesterday - timedelta(days=6),  yesterday),
        "previous": (yesterday - timedelta(days=13), yesterday - timedelta(days=7)),
    },
    "last_14d": {
        "label": "Last 14 Days",
        "current":  (yesterday - timedelta(days=13), yesterday),
        "previous": (yesterday - timedelta(days=27), yesterday - timedelta(days=14)),
    },
    "last_30d": {
        "label": "Last 30 Days",
        "current":  (yesterday - timedelta(days=29), yesterday),
        "previous": (yesterday - timedelta(days=59), yesterday - timedelta(days=30)),
    },
}


# ── Channel classification (per Pablo, 2026-09-21) ────────────────────
# Based on the campaign name:
#   contains "brand"                    -> brand
#   contains "pmax"                     -> pmax   (checked before generic: "Generic_PMAX" is pmax)
#   contains "generic" (and not pmax)   -> generic
#   contains "display" or "youtube"     -> display
# Fallback on advertising_channel_type for anything unnamed.
CHANNELS = ["brand", "generic", "pmax", "display"]


def campaign_channel(name, channel_type=None):
    nm = (name or "").lower()
    if "brand" in nm:
        return "brand"
    if "pmax" in nm or "performance_max" in nm or "performance max" in nm:
        return "pmax"
    if "generic" in nm:
        return "generic"
    if "display" in nm or "youtube" in nm:
        return "display"
    ct = channel_type.name if hasattr(channel_type, "name") else str(channel_type or "")
    ct = ct.upper()
    if ct == "PERFORMANCE_MAX":
        return "pmax"
    if ct in ("DISPLAY", "VIDEO", "DEMAND_GEN", "DISCOVERY"):
        return "display"
    if ct == "SEARCH":
        return "generic"
    return "other"


# ── Funnel stages ─────────────────────────────────────────────────────
# Primary conversion actions are named like "Zapier Aug 25 | Apps". The stage
# is the part after the last "|". Known order of the Ironhack funnel:
FUNNEL_ORDER = ["Apps", "QApps", "TI", "SA", "BST"]
STAGE_LABELS = {
    "Apps": "Applications",
    "QApps": "Qualified Apps",
    "TI": "Technical Interview",
    "SA": "Student Agreement",
    "BST": "Booked Student",
}
DEVICES_ORDER = ["DESKTOP", "MOBILE", "TABLET", "CONNECTED_TV", "OTHER", "UNKNOWN"]


def stage_key(conversion_action_name):
    nm = (conversion_action_name or "").strip()
    if "|" in nm:
        nm = nm.rsplit("|", 1)[1].strip()
    return nm or "Unknown"


def stage_sort_key(stage):
    return (FUNNEL_ORDER.index(stage) if stage in FUNNEL_ORDER else len(FUNNEL_ORDER), stage)


def device_sort_key(dev):
    return (DEVICES_ORDER.index(dev) if dev in DEVICES_ORDER else len(DEVICES_ORDER), dev)


# ── Helpers ───────────────────────────────────────────────────────────
def micros_to_float(val):
    if val is None or val == 0:
        return 0.0
    return float(val) / 1_000_000.0


def safe_div(a, b):
    return a / b if b else 0.0


def date_in_range(d, date_range):
    start, end = date_range
    return start <= d <= end


def run_query(customer_id, query):
    """Run a GAQL stream query and collect all rows."""
    rows = []
    try:
        stream = ga_service.search_stream(customer_id=customer_id, query=query)
        for batch in stream:
            for row in batch.results:
                rows.append(row)
    except GoogleAdsException as ex:
        msg = ex.failure.errors[0].message if ex.failure.errors else str(ex)
        print(f"  ⚠ Query failed for {customer_id}: {msg}", file=sys.stderr)
    return rows


def extract_date(row):
    seg = getattr(row, "segments", None)
    if seg and hasattr(seg, "date") and seg.date:
        return date.fromisoformat(seg.date)
    return None


def extract_metrics(metrics):
    """Standard KPIs from a metrics object (daily row)."""
    cost = micros_to_float(getattr(metrics, "cost_micros", 0) or 0)
    conversions = round(getattr(metrics, "conversions", 0) or 0, 2)
    cv = float(getattr(metrics, "conversions_value", 0) or 0)
    return {
        "impressions": getattr(metrics, "impressions", 0) or 0,
        "clicks": getattr(metrics, "clicks", 0) or 0,
        "cost": cost,
        "conversions": conversions,
        "conversions_value": cv,
    }


def derive(agg):
    agg["ctr"] = safe_div(agg["clicks"], agg["impressions"])
    agg["cpc"] = safe_div(agg["cost"], agg["clicks"])
    agg["cost_per_conversion"] = safe_div(agg["cost"], agg["conversions"])
    agg["roas"] = safe_div(agg["conversions_value"], agg["cost"])
    return agg


META_KEYS = ("account_id", "campaign_id", "campaign_name", "type", "channel",
             "ad_group_id", "ad_group_name", "ad_group_status", "keyword_text",
             "match_type", "keyword_status", "ad_id", "ad_name", "ad_type",
             "channel_type", "status")


# ── Bucketing ─────────────────────────────────────────────────────────
def init_buckets():
    return {tf: {"current": defaultdict(list), "previous": defaultdict(list)} for tf in TIMEFRAMES}


def route_to_buckets(row_date, entity_id, record, buckets):
    for tf_key, tf in TIMEFRAMES.items():
        if date_in_range(row_date, tf["current"]):
            buckets[tf_key]["current"][entity_id].append(record)
        if date_in_range(row_date, tf["previous"]):
            buckets[tf_key]["previous"][entity_id].append(record)


def aggregate_base(records):
    agg = {
        "impressions": sum(r["impressions"] for r in records),
        "clicks": sum(r["clicks"] for r in records),
        "cost": sum(r["cost"] for r in records),
        "conversions": round(sum(r["conversions"] for r in records), 2),
        "conversions_value": sum(r["conversions_value"] for r in records),
    }
    derive(agg)
    first = records[0]
    for k in META_KEYS:
        if k in first:
            agg[k] = first[k]
    # Campaign-level IS metrics: average over days with impressions (they are ratios)
    if "search_impression_share" in first:
        days = [r for r in records if r.get("impressions", 0) > 0]
        for k in ("search_impression_share", "search_budget_lost_is", "search_rank_lost_is"):
            agg[k] = round(safe_div(sum(r.get(k, 0) for r in days), len(days)), 4) if days else 0.0
    return agg


def aggregate_devices(records):
    """records: daily rows with 'device' -> {device: kpis}"""
    per_dev = defaultdict(lambda: {"impressions": 0, "clicks": 0, "cost": 0.0,
                                   "conversions": 0.0, "conversions_value": 0.0})
    for r in records:
        d = per_dev[r["device"]]
        d["impressions"] += r["impressions"]
        d["clicks"] += r["clicks"]
        d["cost"] += r["cost"]
        d["conversions"] += r["conversions"]
        d["conversions_value"] += r["conversions_value"]
    out = {}
    for dev in sorted(per_dev, key=device_sort_key):
        d = per_dev[dev]
        d["conversions"] = round(d["conversions"], 2)
        out[dev] = derive(d)
    return out


def aggregate_stages(records):
    """records: rows with 'device','stage','conversions','conversions_value'
    -> (stages, stages_value, device_stages)"""
    stages = defaultdict(float)
    stages_value = defaultdict(float)
    dev_stages = defaultdict(lambda: defaultdict(float))
    for r in records:
        if not r["conversions"] and not r["conversions_value"]:
            continue
        stages[r["stage"]] += r["conversions"]
        stages_value[r["stage"]] += r["conversions_value"]
        dev_stages[r["device"]][r["stage"]] += r["conversions"]
    ordered = lambda d: {k: round(d[k], 2) for k in sorted(d, key=stage_sort_key)}
    return (ordered(stages), ordered(stages_value),
            {dev: ordered(dev_stages[dev]) for dev in sorted(dev_stages, key=device_sort_key)})


def assemble(base_b, dev_b, stage_b):
    """Aggregate all buckets and attach device + stage breakdowns to each entity."""
    result = {}
    for tf in TIMEFRAMES:
        result[tf] = {}
        for period in ("current", "previous"):
            ents = {}
            for eid, records in base_b[tf][period].items():
                agg = aggregate_base(records)
                st, stv, dev_st = aggregate_stages(stage_b[tf][period].get(eid, []))
                agg["stages"] = st
                agg["stages_value"] = stv
                devices = aggregate_devices(dev_b[tf][period].get(eid, []))
                for dev, d in devices.items():
                    d["stages"] = dev_st.get(dev, {})
                agg["devices"] = devices
                ents[eid] = agg
            result[tf][period] = ents
    return result


# ── Level definitions ─────────────────────────────────────────────────
STD_METRICS = "metrics.impressions, metrics.clicks, metrics.cost_micros, metrics.conversions, metrics.conversions_value"
CONV_METRICS = "metrics.conversions, metrics.conversions_value"

LEVELS = {
    "campaigns": {
        "resource": "campaign",
        "ids": "campaign.id, campaign.name, campaign.status, campaign.advertising_channel_type",
        "base_extra": ", campaign_budget.amount_micros, metrics.average_cpc, metrics.ctr, "
                      "metrics.search_impression_share, metrics.search_budget_lost_impression_share, "
                      "metrics.search_rank_lost_impression_share",
        "where": "campaign.status != 'REMOVED'",
        "order": "campaign.id",
    },
    "ad_groups": {
        "resource": "ad_group",
        "ids": "campaign.id, campaign.name, campaign.advertising_channel_type, ad_group.id, ad_group.name, ad_group.status",
        "base_extra": "",
        "where": "campaign.status != 'REMOVED' AND ad_group.status != 'REMOVED'",
        "order": "campaign.id, ad_group.id",
    },
    "keywords": {
        "resource": "keyword_view",
        "ids": "campaign.id, campaign.name, campaign.advertising_channel_type, ad_group.id, ad_group.name, "
               "ad_group_criterion.keyword.text, ad_group_criterion.keyword.match_type, ad_group_criterion.status",
        "base_extra": "",
        "where": "campaign.status != 'REMOVED' AND ad_group.status != 'REMOVED' AND ad_group_criterion.status != 'REMOVED'",
        "order": "campaign.id, ad_group.id, ad_group_criterion.keyword.text",
    },
    "ads": {
        "resource": "ad_group_ad",
        "ids": "campaign.id, campaign.name, campaign.advertising_channel_type, ad_group.id, ad_group.name, "
               "ad_group_ad.ad.id, ad_group_ad.ad.name, ad_group_ad.ad.type",
        "base_extra": "",
        "where": "campaign.status != 'REMOVED' AND ad_group.status != 'REMOVED' AND ad_group_ad.status != 'REMOVED'",
        "order": "campaign.id, ad_group.id, ad_group_ad.ad.id",
    },
}


def build_queries(level):
    L = LEVELS[level]
    base = (f"SELECT {L['ids']}, segments.date, {STD_METRICS}{L['base_extra']} "
            f"FROM {L['resource']} WHERE {DATE_WHERE} AND {L['where']} ORDER BY {L['order']}, segments.date")
    device = (f"SELECT {L['ids']}, segments.date, segments.device, {STD_METRICS} "
              f"FROM {L['resource']} WHERE {DATE_WHERE} AND {L['where']}")
    stage = (f"SELECT {L['ids']}, segments.date, segments.device, segments.conversion_action_name, {CONV_METRICS} "
             f"FROM {L['resource']} WHERE {DATE_WHERE} AND {L['where']}")
    return base, device, stage


def entity_and_meta(level, row, cid):
    """Return (entity_id, metadata dict) for a row at the given level."""
    camp = row.campaign
    channel = campaign_channel(camp.name, camp.advertising_channel_type)
    meta = {
        "account_id": cid,
        "campaign_id": str(camp.id),
        "campaign_name": camp.name,
        "channel": channel,
        "type": channel,   # kept for backward compatibility with older consumers
    }
    if level == "campaigns":
        meta["status"] = camp.status.name if camp.status else "UNKNOWN"
        meta["channel_type"] = camp.advertising_channel_type.name if camp.advertising_channel_type else "UNKNOWN"
        return str(camp.id), meta
    ag = row.ad_group
    meta["ad_group_id"] = str(ag.id)
    meta["ad_group_name"] = ag.name
    if level == "ad_groups":
        meta["ad_group_status"] = ag.status.name if ag.status else "UNKNOWN"
        return f"{camp.id}:{ag.id}", meta
    if level == "keywords":
        kw = row.ad_group_criterion.keyword
        meta["keyword_text"] = kw.text
        meta["match_type"] = kw.match_type.name if kw.match_type else "UNKNOWN"
        meta["keyword_status"] = row.ad_group_criterion.status.name if row.ad_group_criterion.status else "UNKNOWN"
        return f"{camp.id}:{ag.id}:{kw.text}", meta
    ad = row.ad_group_ad.ad
    meta["ad_id"] = str(ad.id)
    meta["ad_name"] = ad.name if ad.name else f"Ad #{str(ad.id)[-6:]}"
    meta["ad_type"] = ad.type.name if ad.type else "UNKNOWN"
    return f"{camp.id}:{ag.id}:{ad.id}", meta


def collect_level(level):
    base_q, device_q, stage_q = build_queries(level)
    base_b, dev_b, stage_b = init_buckets(), init_buckets(), init_buckets()
    for cid in CUSTOMER_IDS:
        print(f"  {level}: account {cid} ...", file=sys.stderr)
        # 1. base KPIs (per day)
        for row in run_query(cid, base_q):
            d = extract_date(row)
            if d is None:
                continue
            eid, meta = entity_and_meta(level, row, cid)
            rec = extract_metrics(row.metrics)
            rec.update(meta)
            if level == "campaigns":
                m = row.metrics
                rec["search_impression_share"] = round(getattr(m, "search_impression_share", 0) or 0, 4)
                rec["search_budget_lost_is"] = round(getattr(m, "search_budget_lost_impression_share", 0) or 0, 4)
                rec["search_rank_lost_is"] = round(getattr(m, "search_rank_lost_impression_share", 0) or 0, 4)
            route_to_buckets(d, eid, rec, base_b)
        # 2. device split (per day x device)
        for row in run_query(cid, device_q):
            d = extract_date(row)
            if d is None:
                continue
            eid, _ = entity_and_meta(level, row, cid)
            rec = extract_metrics(row.metrics)
            rec["device"] = row.segments.device.name if row.segments.device else "UNKNOWN"
            route_to_buckets(d, eid, rec, dev_b)
        # 3. funnel stages (per day x device x conversion action)
        for row in run_query(cid, stage_q):
            d = extract_date(row)
            if d is None:
                continue
            conv = round(getattr(row.metrics, "conversions", 0) or 0, 2)
            val = float(getattr(row.metrics, "conversions_value", 0) or 0)
            if not conv and not val:
                continue
            eid, _ = entity_and_meta(level, row, cid)
            rec = {
                "device": row.segments.device.name if row.segments.device else "UNKNOWN",
                "stage": stage_key(row.segments.conversion_action_name),
                "conversions": conv,
                "conversions_value": val,
            }
            route_to_buckets(d, eid, rec, stage_b)
    return assemble(base_b, dev_b, stage_b)


# ── Auction Insights (brand campaigns only) ───────────────────────────
def auction_query(start, end):
    return f"""
    SELECT
      campaign.id,
      campaign.name,
      segments.auction_insight_domain,
      metrics.auction_insight_search_impression_share,
      metrics.auction_insight_search_overlap_rate,
      metrics.auction_insight_search_position_above_rate,
      metrics.auction_insight_search_top_impression_percentage,
      metrics.auction_insight_search_outranking_share
    FROM campaign
    WHERE segments.date BETWEEN '{date_str(start)}' AND '{date_str(end)}'
    ORDER BY campaign.id, metrics.auction_insight_search_impression_share DESC
    """


def collect_auction_insights():
    results = {"last_7d": [], "last_30d": []}
    queries = {
        "last_7d": auction_query(yesterday - timedelta(days=6), yesterday),
        "last_30d": auction_query(yesterday - timedelta(days=29), yesterday),
    }
    for period, query in queries.items():
        for cid in CUSTOMER_IDS:
            for row in run_query(cid, query):
                camp = row.campaign
                if campaign_channel(camp.name, getattr(camp, "advertising_channel_type", None)) != "brand":
                    continue
                domain = getattr(row.segments, "auction_insight_domain", None)
                if not domain:
                    continue
                m = row.metrics
                results[period].append({
                    "account_id": cid,
                    "campaign_id": str(camp.id),
                    "campaign_name": camp.name,
                    "domain": domain,
                    "impression_share": round(getattr(m, "auction_insight_search_impression_share", 0) or 0, 4),
                    "overlap_rate": round(getattr(m, "auction_insight_search_overlap_rate", 0) or 0, 4),
                    "position_above_rate": round(getattr(m, "auction_insight_search_position_above_rate", 0) or 0, 4),
                    "top_impression_pct": round(getattr(m, "auction_insight_search_top_impression_percentage", 0) or 0, 4),
                    "outranking_share": round(getattr(m, "auction_insight_search_outranking_share", 0) or 0, 4),
                })
    return results


# ── Summary for the agent (stdout) ────────────────────────────────────
def _totals(entities, channel=None):
    t = {"impressions": 0, "clicks": 0, "cost": 0.0, "conversions": 0.0, "conversions_value": 0.0}
    st = defaultdict(float)
    dev = defaultdict(lambda: {"cost": 0.0, "conversions": 0.0, "clicks": 0})
    for e in entities.values():
        if channel and e.get("channel") != channel:
            continue
        for k in t:
            t[k] += e.get(k, 0) or 0
        for s, v in e.get("stages", {}).items():
            st[s] += v
        for d, dv in e.get("devices", {}).items():
            dev[d]["cost"] += dv.get("cost", 0)
            dev[d]["conversions"] += dv.get("conversions", 0)
            dev[d]["clicks"] += dv.get("clicks", 0)
    t["conversions"] = round(t["conversions"], 1)
    t["cost"] = round(t["cost"], 2)
    t["conversions_value"] = round(t["conversions_value"], 2)
    t["cpa"] = round(safe_div(t["cost"], t["conversions"]), 2)
    t["roas"] = round(safe_div(t["conversions_value"], t["cost"]), 2)
    t["stages"] = {s: round(st[s], 1) for s in sorted(st, key=stage_sort_key)}
    total_conv = sum(dv["conversions"] for dv in dev.values())
    t["devices"] = {
        d: {"cost": round(dev[d]["cost"], 2), "conversions": round(dev[d]["conversions"], 1),
            "cpa": round(safe_div(dev[d]["cost"], dev[d]["conversions"]), 2),
            "conv_share": round(safe_div(dev[d]["conversions"], total_conv), 3)}
        for d in sorted(dev, key=device_sort_key)
    }
    return t


def _mover_entry(level, eid, cur, prev):
    c, p = cur or {}, prev or {}
    e = {
        "campaign": (c or p).get("campaign_name"),
        "channel": (c or p).get("channel"),
        "cost": round(c.get("cost", 0), 2), "cost_prev": round(p.get("cost", 0), 2),
        "conversions": round(c.get("conversions", 0), 1), "conversions_prev": round(p.get("conversions", 0), 1),
        "roas": round(c.get("roas", 0), 2), "roas_prev": round(p.get("roas", 0), 2),
        "cpa": round(c.get("cost_per_conversion", 0), 2), "cpa_prev": round(p.get("cost_per_conversion", 0), 2),
        "stages": c.get("stages", {}), "stages_prev": p.get("stages", {}),
    }
    e["cost_delta"] = round(e["cost"] - e["cost_prev"], 2)
    e["conversions_delta"] = round(e["conversions"] - e["conversions_prev"], 1)
    if level == "campaigns":
        e["status"] = (c or p).get("status")
    if level in ("ad_groups", "keywords", "ads"):
        e["ad_group"] = (c or p).get("ad_group_name")
    if level == "keywords":
        e["keyword"] = (c or p).get("keyword_text")
        e["match_type"] = (c or p).get("match_type")
    if level == "ads":
        e["ad"] = (c or p).get("ad_name")
    return e


def _movers(level, tf_data, n_each=5, min_cost=10.0, min_conv=1.0):
    cur, prev = tf_data["current"], tf_data["previous"]
    entries = []
    for eid in set(cur) | set(prev):
        e = _mover_entry(level, eid, cur.get(eid), prev.get(eid))
        if abs(e["cost_delta"]) < min_cost and abs(e["conversions_delta"]) < min_conv:
            continue
        entries.append(e)
    by_conv = sorted(entries, key=lambda e: -abs(e["conversions_delta"]))
    by_cost = sorted(entries, key=lambda e: -abs(e["cost_delta"]))
    return {
        "conversions_up": [e for e in by_conv if e["conversions_delta"] > 0][:n_each],
        "conversions_down": [e for e in by_conv if e["conversions_delta"] < 0][:n_each],
        "cost_up": [e for e in by_cost if e["cost_delta"] > 0][:n_each],
        "cost_down": [e for e in by_cost if e["cost_delta"] < 0][:n_each],
    }


def build_summary(output, data_file):
    data = output["data"]
    camps = data["campaigns"]["last_7d"]
    summary = {
        "generated": output["report_metadata"]["generated"],
        "data_file": data_file,
        "note": ("Full dataset (all timeframes/levels, with channel, funnel-stage and device breakdowns) "
                 "is in data_file. Everything below is last_7d vs the previous 7 days, all accounts, "
                 "pre-computed from that same file."),
        "timeframes": output["report_metadata"]["timeframes"],
        "accounts": output["report_metadata"]["accounts"],
        "counts": {lvl: len(data[lvl]["last_7d"]["current"]) for lvl in LEVELS},
        "funnel_order": output["report_metadata"]["funnel_stages"],
        "stage_labels": STAGE_LABELS,
        "totals_7d": {"current": _totals(camps["current"]), "previous": _totals(camps["previous"])},
        "by_channel_7d": {
            ch: {"current": _totals(camps["current"], ch), "previous": _totals(camps["previous"], ch)}
            for ch in CHANNELS + ["other"]
            if any(e.get("channel") == ch for e in list(camps["current"].values()) + list(camps["previous"].values()))
        },
        "movers_7d": {
            "campaigns": _movers("campaigns", camps, n_each=5),
            "ad_groups": _movers("ad_groups", data["ad_groups"]["last_7d"], n_each=5),
            "keywords": _movers("keywords", data["keywords"]["last_7d"], n_each=5),
        },
    }
    return summary


# ── Main ──────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=os.environ.get("ARGOS_PERF_OUT", "/tmp/argos_perf_data.json"),
                    help="where to write the full dataset (default /tmp/argos_perf_data.json)")
    ap.add_argument("--full-stdout", action="store_true",
                    help="print the full dataset to stdout instead of the compact summary")
    args = ap.parse_args()

    print("📡 Argos Performance Report — collecting data...", file=sys.stderr)
    levels = {lvl: collect_level(lvl) for lvl in LEVELS}
    auction_insights = collect_auction_insights()

    timeframe_meta = {
        tf_key: {
            "label": tf["label"],
            "current":  {"start": date_str(tf["current"][0]),  "end": date_str(tf["current"][1])},
            "previous": {"start": date_str(tf["previous"][0]), "end": date_str(tf["previous"][1])},
        }
        for tf_key, tf in TIMEFRAMES.items()
    }

    # Stages and devices actually present (ordered)
    stages_seen, devices_seen = set(), set()
    for lvl in levels.values():
        for tf in lvl.values():
            for period in tf.values():
                for e in period.values():
                    stages_seen.update(e.get("stages", {}).keys())
                    devices_seen.update(e.get("devices", {}).keys())

    output = {
        "report_metadata": {
            "generated": today.isoformat(),
            "timeframes": timeframe_meta,
            "accounts": CUSTOMER_IDS,
            "accounts_count": len(CUSTOMER_IDS),
            "channels": CHANNELS,
            "funnel_stages": sorted(stages_seen, key=stage_sort_key),
            "stage_labels": STAGE_LABELS,
            "devices": sorted(devices_seen, key=device_sort_key),
        },
        "data": {**levels, "auction_insights": auction_insights},
    }

    if args.full_stdout:
        print(json.dumps(output, indent=2, default=str))
        return

    tmp = args.out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(output, f, default=str)
    os.replace(tmp, args.out)
    print(f"  ✓ full dataset written to {args.out} ({os.path.getsize(args.out):,} bytes)", file=sys.stderr)

    print(json.dumps(build_summary(output, args.out), indent=2, default=str))


if __name__ == "__main__":
    main()
