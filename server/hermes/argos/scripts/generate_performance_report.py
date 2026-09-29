"""
generate_performance_report.py — Generates the branded HTML performance report
from the JSON dataset produced by performance_report.py, uploads it to S3 and
prints the public URL.

Report layout:
  timeframe tabs (7d / 14d / 30d)  x  channel tabs (All / Brand / Generic / PMAX / Display)
  Each tab: KPI cards, funnel-stage strip, device split, key takeaways, then the
  campaign / ad group / keyword / ad tables. Every table row carries the funnel
  breakdown and can be expanded into its device split.

Usage: python3 generate_performance_report.py [/tmp/argos_perf_data.json] [--preview] [--local out.html]
  --preview   upload as performance-preview.html instead of overwriting performance.html
  --local F   write the HTML to F and skip the S3 upload (for testing)
"""
import argparse
import html
import json
import os
import sys
from datetime import date
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from report_s3 import upload_html, load_logo

TEMPLATE_PATH = (
    "/home/openclaw/.hermes/profiles/argos/skills/marketing/"
    "argos-reports/templates/performance-report.html"
)

CHANNEL_LABELS = {
    "all": "All channels",
    "brand": "Brand",
    "generic": "Generic",
    "pmax": "PMAX",
    "display": "Display / YouTube",
    "other": "Other",
}
DEVICE_LABELS = {
    "DESKTOP": "Desktop", "MOBILE": "Mobile", "TABLET": "Tablet",
    "CONNECTED_TV": "TV", "OTHER": "Other", "UNKNOWN": "Unknown",
}
DEFAULT_FUNNEL = ["Apps", "QApps", "TI", "SA", "BST"]


# ── Formatting helpers ────────────────────────────────────────────────
def esc(s):
    return html.escape(str(s if s is not None else ""), quote=True)


def fmt_num(v, decimals=0):
    if v is None or (v == 0 and decimals == 0):
        return "—" if decimals == 0 else "0"
    try:
        if decimals == 0:
            return f"{int(v):,}"
        return f"{v:,.{decimals}f}"
    except (TypeError, ValueError):
        return str(v) if v else "—"


def fmt_money(v):
    if v is None or v == 0:
        return "—"
    return f"€{v:,.2f}"


def fmt_pct(v):
    if v is None:
        return "—"
    return f"{v * 100:.2f}%"


def fmt_conv(v):
    """Conversions can be fractional (data-driven attribution)."""
    if not v:
        return "0"
    s = f"{v:.1f}"
    return s[:-2] if s.endswith(".0") else s


def fmt_roas(v):
    return f"{v:.2f}x" if v else "—"


def _delta_span(curr, prev, up_cls, down_cls):
    if curr is None or prev is None or prev == 0:
        if curr and curr > 0 and not prev:
            return '<span class="delta delta-new">new</span>'
        return '<span class="delta delta-flat">—</span>'
    d = (curr - prev) / prev * 100
    if d > 0:
        return f'<span class="delta {up_cls}">↑ {d:.1f}%</span>'
    if d < 0:
        return f'<span class="delta {down_cls}">↓ {abs(d):.1f}%</span>'
    return '<span class="delta delta-flat">0%</span>'


def delta_pct(curr, prev):
    """Neutral % change (impressions, clicks)."""
    return _delta_span(curr, prev, "delta-up", "delta-down")


def delta_cost(curr, prev):
    """Cost / CPA / CPC: up is bad."""
    return _delta_span(curr, prev, "delta-up", "delta-down")


def delta_good(curr, prev):
    """Conversions / ROAS / value: up is good."""
    return _delta_span(curr, prev, "delta-up-good", "delta-down-bad")


def delta_pp(curr, prev):
    """Percentage-point change for rates (CTR, share)."""
    if curr is None or prev is None:
        return '<span class="delta delta-flat">—</span>'
    d = curr - prev
    if d > 0:
        return f'<span class="delta delta-up-good">↑ {d * 100:.1f}pp</span>'
    if d < 0:
        return f'<span class="delta delta-down-bad">↓ {abs(d) * 100:.1f}pp</span>'
    return '<span class="delta delta-flat">0pp</span>'


def cell(curr, prev, fmt_fn, delta_fn):
    return f"{fmt_fn(curr)}<br>{delta_fn(curr, prev)}"


def pct_change_text(curr, prev):
    if not prev:
        return "new" if curr else "—"
    d = (curr - prev) / prev * 100
    return f"{'+' if d >= 0 else '−'}{abs(d):.0f}%"


# ── Badges ────────────────────────────────────────────────────────────
BADGE_LABELS = {"brand": "Brand", "generic": "Generic", "pmax": "PMAX", "display": "Display", "other": "Other"}


def channel_badge(ch):
    ch = ch or "other"
    cls = f"badge-{ch}" if ch in ("brand", "generic", "pmax", "display") else "badge-other"
    return f'<span class="badge {cls}">{esc(BADGE_LABELS.get(ch, ch))}</span>'


def match_badge(mt):
    mt_lower = (mt or "").lower()
    if "exact" in mt_lower:
        return '<span class="badge badge-exact">exact</span>'
    if "phrase" in mt_lower:
        return '<span class="badge badge-phrase">phrase</span>'
    if "broad" in mt_lower:
        return '<span class="badge badge-broad">broad</span>'
    return f'<span class="badge badge-other">{esc(mt or "?")}</span>'


def status_badge(status):
    if status and status != "ENABLED":
        return f' <span class="badge badge-paused">{esc(status.lower())}</span>'
    return ""


# ── Aggregation ───────────────────────────────────────────────────────
def filter_channel(entities, ch):
    if ch == "all":
        return entities
    return {k: v for k, v in entities.items() if v.get("channel", v.get("type")) == ch}


def _empty_totals():
    return {"impressions": 0, "clicks": 0, "cost": 0.0, "conversions": 0.0, "conversions_value": 0.0}


def _derive(t):
    t["ctr"] = t["clicks"] / t["impressions"] if t["impressions"] else 0.0
    t["cpc"] = t["cost"] / t["clicks"] if t["clicks"] else 0.0
    t["cpa"] = t["cost"] / t["conversions"] if t["conversions"] else 0.0
    t["cost_per_conversion"] = t["cpa"]
    t["roas"] = t["conversions_value"] / t["cost"] if t["cost"] else 0.0
    return t


def agg_totals(entities):
    """Totals across a {id: record} dict, including funnel stages and devices."""
    t = _empty_totals()
    stages = defaultdict(float)
    devices = defaultdict(_empty_totals)
    dev_stages = defaultdict(lambda: defaultdict(float))
    for r in entities.values():
        for k in _empty_totals():
            t[k] += r.get(k, 0) or 0
        for s, v in (r.get("stages") or {}).items():
            stages[s] += v
        for d, dv in (r.get("devices") or {}).items():
            for k in _empty_totals():
                devices[d][k] += dv.get(k, 0) or 0
            for s, v in (dv.get("stages") or {}).items():
                dev_stages[d][s] += v
    _derive(t)
    t["stages"] = dict(stages)
    t["devices"] = {}
    for d in devices:
        dd = _derive(devices[d])
        dd["stages"] = dict(dev_stages[d])
        t["devices"][d] = dd
    return t


def stage_order(data, *dicts):
    """Funnel order: report metadata first, then anything else seen."""
    order = list(data.get("report_metadata", {}).get("funnel_stages") or [])
    if not order:
        order = list(DEFAULT_FUNNEL)
    for d in dicts:
        for s in (d or {}):
            if s not in order:
                order.append(s)
    return order


def device_order(data):
    order = list(data.get("report_metadata", {}).get("devices") or [])
    return order or ["DESKTOP", "MOBILE", "TABLET"]


# ── Funnel cell ───────────────────────────────────────────────────────
def funnel_header(order):
    return " › ".join(esc(s) for s in order)


def funnel_cell(cur_stages, prev_stages, order):
    cur = " › ".join(fmt_conv((cur_stages or {}).get(s, 0)) for s in order)
    prev = " › ".join(fmt_conv((prev_stages or {}).get(s, 0)) for s in order)
    return f'{cur}<span class="funnel-prev">prev {prev}</span>'


# ── KPI cells shared by main rows and device sub-rows ─────────────────
def kpi_cells(c, p, order, with_value):
    c = c or {}
    p = p or {}
    cells = [
        cell(c.get("impressions"), p.get("impressions"), fmt_num, delta_pct),
        cell(c.get("clicks"), p.get("clicks"), fmt_num, delta_pct),
        cell(c.get("ctr"), p.get("ctr"), fmt_pct, delta_pp),
        cell(c.get("cpc"), p.get("cpc"), fmt_money, delta_cost),
        cell(c.get("cost"), p.get("cost"), fmt_money, delta_cost),
        cell(c.get("conversions"), p.get("conversions"), fmt_conv, delta_good),
        cell(c.get("cost_per_conversion"), p.get("cost_per_conversion"), fmt_money, delta_cost),
    ]
    if with_value:
        cells.append(cell(c.get("conversions_value"), p.get("conversions_value"), fmt_money, delta_good))
    cells.append(cell(c.get("roas"), p.get("roas"), fmt_roas, delta_good))
    out = "".join(f'<td class="num">{x}</td>' for x in cells)
    out += f'<td class="funnel-cell">{funnel_cell(c.get("stages"), p.get("stages"), order)}</td>'
    return out


def kpi_headers(order, with_value):
    h = ['<th class="num">Impr.</th>', '<th class="num">Clicks</th>', '<th class="num">CTR</th>',
         '<th class="num">CPC</th>', '<th class="num">Spend</th>', '<th class="num">Conv.</th>',
         '<th class="num">Cost/Conv.</th>']
    if with_value:
        h.append('<th class="num">Conv. Value</th>')
    h.append('<th class="num">ROAS</th>')
    h.append(f'<th class="funnel-head">Funnel: {funnel_header(order)}</th>')
    return "".join(h)


def device_rows(rowid, c, p, order, with_value, n_label_cols, devices):
    """Hidden sub-rows with the device split for one entity."""
    rows = []
    cdev = (c or {}).get("devices") or {}
    pdev = (p or {}).get("devices") or {}
    for d in devices:
        if d not in cdev and d not in pdev:
            continue
        cd, pd = cdev.get(d, {}), pdev.get(d, {})
        rows.append(
            f'<tr class="dev-row" data-parent="{rowid}" style="display:none">'
            f'<td class="dev-label" colspan="{n_label_cols}">↳ {esc(DEVICE_LABELS.get(d, d.title()))}</td>'
            f'{kpi_cells(cd, pd, order, with_value)}</tr>'
        )
    return "".join(rows)


def dev_toggle(rowid, c):
    if not (c or {}).get("devices"):
        return ""
    return f'<button class="dev-toggle" onclick="toggleDevices(this)" title="Device split"></button>'


# ── Generic table builder ─────────────────────────────────────────────
LEVEL_SPECS = {
    "campaigns": {
        "title": "Campaign Performance",
        "with_value": True,
        "label_headers": ["Campaign", "Channel"],
        "label_cells": lambda c: [
            f'{esc(c.get("campaign_name", "?"))}{status_badge(c.get("status"))}',
            channel_badge(c.get("channel", c.get("type"))),
        ],
    },
    "ad_groups": {
        "title": "Ad Group Performance",
        "with_value": False,
        "label_headers": ["Campaign", "Ad Group", "Channel"],
        "label_cells": lambda c: [
            esc(c.get("campaign_name", "?")),
            esc(c.get("ad_group_name", "?")),
            channel_badge(c.get("channel", c.get("type"))),
        ],
    },
    "keywords": {
        "title": "Keyword Performance",
        "with_value": False,
        "label_headers": ["Campaign", "Keyword", "Match", "Channel"],
        "label_cells": lambda c: [
            esc(c.get("campaign_name", "?")),
            esc(c.get("keyword_text", "?")),
            match_badge(c.get("match_type")),
            channel_badge(c.get("channel", c.get("type"))),
        ],
    },
    "ads": {
        "title": "Ad Performance",
        "with_value": False,
        "label_headers": ["Campaign", "Ad Group", "Ad", "Channel"],
        "label_cells": lambda c: [
            esc(c.get("campaign_name", "?")),
            esc(c.get("ad_group_name", "?")),
            esc(c.get("ad_name", "?")),
            channel_badge(c.get("channel", c.get("type"))),
        ],
    },
}


def build_level_table(level, curr_dict, prev_dict, order, devices, tab_id, limit=30):
    spec = LEVEL_SPECS[level]
    if not curr_dict:
        return f'<p style="color:#888;font-size:13px;">No {spec["title"].split()[0].lower()} data for this period.</p>'

    sorted_ids = sorted(curr_dict.keys(), key=lambda k: curr_dict[k].get("cost", 0) or 0, reverse=True)[:limit]
    n_label = len(spec["label_headers"])
    rows = []
    for i, eid in enumerate(sorted_ids):
        c = curr_dict[eid]
        p = prev_dict.get(eid, {})
        rowid = f"{tab_id}-{level}-{i}"
        labels = spec["label_cells"](c)
        labels[0] = dev_toggle(rowid, c) + labels[0]
        label_td = "".join(f'<td class="lbl">{x}</td>' for x in labels)
        rows.append(f'<tr data-rowid="{rowid}">{label_td}{kpi_cells(c, p, order, spec["with_value"])}</tr>')
        rows.append(device_rows(rowid, c, p, order, spec["with_value"], n_label, devices))

    header = "".join(f"<th>{h}</th>" for h in spec["label_headers"]) + kpi_headers(order, spec["with_value"])
    tools = ('<div class="table-tools">'
             '<button class="link-btn" onclick="toggleAllDevices(this)">Show all device splits</button></div>')
    shown = f'<p class="period-note">Top {len(sorted_ids)} of {len(curr_dict)} by spend. ▸ expands the device split.</p>'
    return f'{tools}{shown}<div class="table-wrap"><table><thead><tr>{header}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


# ── Auction insights ──────────────────────────────────────────────────
def build_auction_insights_table(auction_data):
    if not auction_data:
        return ('<p style="color:#888;font-size:13px;">'
                'No auction insight data available. '
                'This may be due to API access restrictions — '
                'the developer token needs Auction Insights permissions. '
                'Contact Google Ads API support to enable this feature.</p>')
    by_campaign = defaultdict(list)
    for entry in auction_data:
        by_campaign[entry["campaign_name"]].append(entry)
    sections = []
    for camp_name in sorted(by_campaign.keys()):
        entries = sorted(by_campaign[camp_name], key=lambda e: e.get("impression_share", 0), reverse=True)
        rows = []
        for e in entries:
            rows.append(f'''<tr>
              <td>{esc(e["domain"])}</td>
              <td class="num">{e.get("impression_share", 0) * 100:.1f}%</td>
              <td class="num">{e.get("overlap_rate", 0) * 100:.1f}%</td>
              <td class="num">{e.get("position_above_rate", 0) * 100:.1f}%</td>
              <td class="num">{e.get("top_impression_pct", 0) * 100:.1f}%</td>
              <td class="num">{e.get("outranking_share", 0) * 100:.1f}%</td>
            </tr>''')
        sections.append(f'''<p style="font-weight:bold;margin:12px 0 6px;color:#0d1b2a;">{esc(camp_name)}</p>
        <div class="table-wrap"><table>
        <thead><tr>
          <th>Domain</th>
          <th class="num">Impr. Share</th>
          <th class="num">Overlap Rate</th>
          <th class="num">Pos. Above Rate</th>
          <th class="num">Top Impr. %</th>
          <th class="num">Outranking Share</th>
        </tr></thead><tbody>{"".join(rows)}</tbody></table></div>''')
    return "\n".join(sections)


# ── Summary blocks ────────────────────────────────────────────────────
def build_summary_cards(ct, pt):
    cards = [
        ("Spend", fmt_money(ct["cost"]), delta_cost(ct["cost"], pt["cost"])),
        ("Impressions", fmt_num(ct["impressions"]), delta_pct(ct["impressions"], pt["impressions"])),
        ("Clicks", fmt_num(ct["clicks"]), delta_pct(ct["clicks"], pt["clicks"])),
        ("Conversions", fmt_conv(ct["conversions"]), delta_good(ct["conversions"], pt["conversions"])),
        ("CPA", fmt_money(ct["cpa"]), delta_cost(ct["cpa"], pt["cpa"])),
        ("ROAS", fmt_roas(ct["roas"]), delta_good(ct["roas"], pt["roas"])),
    ]
    return '<div class="summary-grid">' + "\n".join(
        f'<div class="summary-card"><div class="summary-label">{label}</div>'
        f'<div class="summary-value">{val}</div><div style="font-size:12px;margin-top:2px;">{delta}</div></div>'
        for label, val, delta in cards
    ) + "</div>"


def build_funnel_strip(ct, pt, order, labels):
    cards = []
    prev_stage_val = None
    for s in order:
        cv = ct["stages"].get(s, 0)
        pv = pt["stages"].get(s, 0)
        cpa_c = ct["cost"] / cv if cv else 0
        cpa_p = pt["cost"] / pv if pv else 0
        rate = ""
        if prev_stage_val:
            rate = f'<div class="stage-rate">{cv / prev_stage_val * 100:.0f}% of previous stage</div>'
        prev_stage_val = cv
        cards.append(
            f'<div class="funnel-card"><div class="summary-label">{esc(s)} · {esc(labels.get(s, s))}</div>'
            f'<div class="summary-value">{fmt_conv(cv)}</div>'
            f'<div style="font-size:12px;margin-top:2px;">{delta_good(cv, pv)}</div>'
            f'<div class="summary-sub">cost per {esc(s)}: {fmt_money(cpa_c)} {delta_cost(cpa_c, cpa_p)}</div>{rate}</div>'
        )
    if not cards:
        return ""
    return f'<div class="funnel-title">Conversions by funnel stage</div><div class="funnel-grid">{"".join(cards)}</div>'


def build_device_table(ct, pt, order, devices):
    cdev, pdev = ct["devices"], pt["devices"]
    if not cdev:
        return ""
    tot_c = sum(d["conversions"] for d in cdev.values()) or 0
    tot_p = sum(d["conversions"] for d in pdev.values()) or 0
    rows = []
    for d in devices:
        if d not in cdev and d not in pdev:
            continue
        c, p = cdev.get(d, _derive(_empty_totals())), pdev.get(d, _derive(_empty_totals()))
        share_c = c["conversions"] / tot_c if tot_c else 0
        share_p = p["conversions"] / tot_p if tot_p else 0
        rows.append(
            f'<tr><td>{esc(DEVICE_LABELS.get(d, d.title()))}</td>'
            f'<td class="num">{share_c * 100:.1f}%<br>{delta_pp(share_c, share_p)}</td>'
            f'{kpi_cells(c, p, order, False)}</tr>'
        )
    header = ('<th>Device</th><th class="num">Conv. share</th>' + kpi_headers(order, False))
    return (f'<div class="section-title" onclick="toggleSection(this)"><span class="arrow">▼</span> Device Split</div>'
            f'<div class="section-body"><div class="table-wrap"><table><thead><tr>{header}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div></div>')


def build_channel_table(curr_camps, prev_camps, order, channels):
    rows = []
    for ch in channels:
        cc, pc = filter_channel(curr_camps, ch), filter_channel(prev_camps, ch)
        if not cc and not pc:
            continue
        ct, pt = agg_totals(cc), agg_totals(pc)
        rows.append(
            f'<tr><td><a href="#" onclick="switchChannel(\'{ch}\');return false;">{channel_badge(ch)}</a></td>'
            f'<td class="num">{len(cc)}</td>{kpi_cells(ct, pt, order, True)}</tr>'
        )
    if not rows:
        return ""
    header = '<th>Channel</th><th class="num">Campaigns</th>' + kpi_headers(order, True)
    return (f'<div class="section-title" onclick="toggleSection(this)"><span class="arrow">▼</span> By Channel</div>'
            f'<div class="section-body"><div class="section-hint">💡 Channel is derived from the campaign name: '
            f'<em>brand</em> → Brand, <em>PMAX</em> → PMAX, <em>generic</em> (not PMAX) → Generic, '
            f'<em>display</em> / <em>YouTube</em> → Display. Click a channel to filter the whole report.</div>'
            f'<div class="table-wrap"><table><thead><tr>{header}</tr></thead><tbody>{"".join(rows)}</tbody></table></div></div>')


# ── Insights ──────────────────────────────────────────────────────────
def build_tab_insights(curr_camps, prev_camps, ct, pt, order, labels, devices, channel):
    insights = []

    # 1. Overall direction
    spend_delta = delta_cost(ct["cost"], pt["cost"])
    conv_delta = delta_good(ct["conversions"], pt["conversions"])
    roas_delta = delta_good(ct["roas"], pt["roas"])
    cpa_delta = delta_cost(ct["cpa"], pt["cpa"])
    spend_up = (ct["cost"] - pt["cost"]) > 0
    conv_up = (ct["conversions"] - pt["conversions"]) > 0
    scope = "" if channel == "all" else f" ({esc(CHANNEL_LABELS.get(channel, channel))})"
    if spend_up and conv_up:
        insights.append(f"📈 Spend {spend_delta} and conversions {conv_delta}{scope}. CPA {cpa_delta}, ROAS {roas_delta} — "
                        f"{'efficiency is improving' if ct['roas'] > pt['roas'] else 'watch CPA drift'}.")
    elif spend_up and not conv_up:
        insights.append(f"⚠️ Spend {spend_delta} but conversions {conv_delta}{scope}. CPA {cpa_delta} — paying more for fewer conversions.")
    elif not spend_up and conv_up:
        insights.append(f"✅ Spend {spend_delta} but conversions {conv_delta}{scope}. CPA {cpa_delta}, ROAS {roas_delta} — efficiency is improving.")
    else:
        insights.append(f"Spend {spend_delta}, conversions {conv_delta}{scope}. CPA {cpa_delta}, ROAS {roas_delta}.")

    # 2. Funnel: where does the change concentrate?
    stage_moves = []
    for s in order:
        cv, pv = ct["stages"].get(s, 0), pt["stages"].get(s, 0)
        if pv >= 1 or cv >= 1:
            stage_moves.append((s, cv, pv, (cv - pv) / pv if pv else None))
    if stage_moves:
        parts = " · ".join(f"{esc(s)} {fmt_conv(pv)}→{fmt_conv(cv)} ({pct_change_text(cv, pv)})" for s, cv, pv, _ in stage_moves)
        with_rate = [m for m in stage_moves if m[3] is not None and max(m[1], m[2]) >= 5]
        line = f"🧭 Funnel: {parts}."
        if with_rate and not conv_up:
            worst = min(with_rate, key=lambda m: m[3])
            if worst[3] < -0.1:
                line += f" Largest drop at <strong>{esc(labels.get(worst[0], worst[0]))}</strong> ({worst[3] * 100:.0f}%)."
        elif with_rate and conv_up:
            best = max(with_rate, key=lambda m: m[3])
            if best[3] > 0.1:
                line += f" Largest gain at <strong>{esc(labels.get(best[0], best[0]))}</strong> (+{best[3] * 100:.0f}%)."
        deep = [m for m in with_rate if m[0] in ("SA", "BST")]
        top = [m for m in with_rate if m[0] == "Apps"]
        if top and deep and top[0][3] > 0.05 and min(d[3] for d in deep) < -0.15:
            line += " Applications are up but bottom-of-funnel stages are down — check lead quality / sales follow-up."
        insights.append(line)

    # 3. Device share shift
    cdev, pdev = ct["devices"], pt["devices"]
    tot_c = sum(d["conversions"] for d in cdev.values())
    tot_p = sum(d["conversions"] for d in pdev.values())
    if tot_c and tot_p:
        shifts = []
        for d in devices:
            if d not in cdev and d not in pdev:
                continue
            sc = cdev.get(d, {}).get("conversions", 0) / tot_c
            sp = pdev.get(d, {}).get("conversions", 0) / tot_p
            shifts.append((d, sc, sp, sc - sp))
        big = [s for s in shifts if abs(s[3]) >= 0.05]
        if big:
            b = max(big, key=lambda s: abs(s[3]))
            cpa_txt = ""
            dc = cdev.get(b[0], {})
            if dc.get("cpa"):
                cpa_txt = f" CPA on {esc(DEVICE_LABELS.get(b[0], b[0]))}: {fmt_money(dc['cpa'])}."
            insights.append(f"📱 Device mix shifted: <strong>{esc(DEVICE_LABELS.get(b[0], b[0]))}</strong> share of conversions "
                            f"{b[2] * 100:.0f}% → {b[1] * 100:.0f}% ({'+' if b[3] > 0 else '−'}{abs(b[3]) * 100:.0f}pp).{cpa_txt}")
        else:
            mix = ", ".join(f"{esc(DEVICE_LABELS.get(d, d))} {sc * 100:.0f}%" for d, sc, _, _ in shifts if sc >= 0.02)
            insights.append(f"📱 Device mix stable ({mix}).")

    # 4. Biggest spend movers
    changes = []
    for cid, c in curr_camps.items():
        p = prev_camps.get(cid, {})
        delta = (c.get("cost", 0) or 0) - (p.get("cost", 0) or 0)
        if abs(delta) > 10:
            tag = " (paused)" if c.get("status") and c.get("status") != "ENABLED" else ""
            changes.append((esc(c.get("campaign_name", cid)) + tag, delta, c.get("conversions", 0), p.get("conversions", 0)))
    changes.sort(key=lambda x: -abs(x[1]))
    top_up = [c for c in changes if c[1] > 0][:2]
    top_down = [c for c in changes if c[1] < 0][:2]
    if top_up:
        insights.append("🔺 Biggest spend increases: " + ", ".join(
            f"<strong>{n}</strong> (+{fmt_money(abs(d))}, conv {fmt_conv(pc)}→{fmt_conv(cc)})" for n, d, cc, pc in top_up) + ".")
    if top_down:
        insights.append("🔻 Biggest spend decreases: " + ", ".join(
            f"<strong>{n}</strong> (−{fmt_money(abs(d))}, conv {fmt_conv(pc)}→{fmt_conv(cc)})" for n, d, cc, pc in top_down) + ".")

    # 5. Biggest conversion movers (the alert Pablo reads in Slack)
    cmoves = []
    for cid in set(curr_camps) | set(prev_camps):
        c, p = curr_camps.get(cid, {}), prev_camps.get(cid, {})
        d = (c.get("conversions", 0) or 0) - (p.get("conversions", 0) or 0)
        if abs(d) >= 1:
            cmoves.append((esc((c or p).get("campaign_name", cid)), d, c.get("conversions", 0) or 0, p.get("conversions", 0) or 0))
    cmoves.sort(key=lambda x: -abs(x[1]))
    if cmoves:
        insights.append("🎯 Biggest conversion movers: " + ", ".join(
            f"<strong>{n}</strong> {fmt_conv(pc)}→{fmt_conv(cc)} ({'+' if d > 0 else '−'}{fmt_conv(abs(d))})" for n, d, cc, pc in cmoves[:3]) + ".")

    # 6. ROAS outliers
    roas_entries = [(esc(c.get("campaign_name", "?")), c.get("roas", 0) or 0, c.get("cost", 0) or 0)
                    for c in curr_camps.values() if (c.get("cost", 0) or 0) > 50]
    if roas_entries:
        roas_entries.sort(key=lambda x: -x[1])
        best, worst = roas_entries[0], roas_entries[-1]
        if best[1] > 3:
            insights.append(f"🏆 Best ROAS: <strong>{best[0]}</strong> at {best[1]:.1f}x (€{best[2]:,.0f} spend).")
        if worst[1] < 1 and worst[0] != best[0]:
            insights.append(f"⚠️ Worst ROAS: <strong>{worst[0]}</strong> at {worst[1]:.1f}x — losing money on this one.")

    # 7. CPC anomaly
    cpc_changes = []
    for cid, c in curr_camps.items():
        p = prev_camps.get(cid, {})
        cc, pc = c.get("cpc", 0) or 0, p.get("cpc", 0) or 0
        if cc > 0 and pc > 0 and (cc - pc) / pc > 0.3:
            cpc_changes.append((esc(c.get("campaign_name", cid)), (cc - pc) / pc, cc, pc))
    cpc_changes.sort(key=lambda x: -x[1])
    if cpc_changes:
        t = cpc_changes[0]
        insights.append(f"📊 CPC watch: <strong>{t[0]}</strong> CPC jumped {t[1] * 100:.0f}% (€{t[2]:.2f} vs €{t[3]:.2f}). "
                        f"Check auction competition or quality score.")

    if not insights:
        insights.append("No significant changes to report.")
    items = "\n".join(f'<div class="insight-row">{i}</div>' for i in insights)
    return f'<div class="insights-box"><div class="insights-title">🔍 Key Takeaways</div>{items}</div>'


SECTION_HYPOTHESES = {
    "campaigns": ("Campaign-level view shows where your budget is going. Focus on the campaigns with the largest "
                  "spend changes and check whether ROAS justifies the shift. The funnel column shows how the "
                  "conversions split by stage — a drop in total conversions that sits only in the late stages "
                  "(SA / BST) is usually processing lag, not performance."),
    "ad_groups": ("Ad group performance reveals which targeting segments are working. Look for ad groups where CPA "
                  "is low and ROAS is high — those are candidates for budget reallocation. Ad groups with rising "
                  "CPC may indicate increasing competition."),
    "keywords": ("Keyword-level data shows exactly which search terms drive results. High-CPA keywords may need "
                 "lower bids or negatives. Low-CTR keywords with high spend are wasting budget — check if the ad "
                 "copy matches the intent."),
    "ads": ("Ad-level performance reveals creative effectiveness. Ads with high CTR but low conversions may have a "
            "landing page mismatch. Ads with low CTR need copy or creative refresh. Use this to identify A/B test winners."),
}


def build_section_hypothesis(key):
    text = SECTION_HYPOTHESES.get(key, "")
    return f'<div class="section-hint">💡 {text}</div>' if text else ""


# ── Tab builder ───────────────────────────────────────────────────────
def build_tab_content(tf_key, ch, tf_meta, data, order, labels, devices, channels):
    d = data.get("data", {})
    tab_id = f"{tf_key}-{ch}"
    lv = {}
    for level in ("campaigns", "ad_groups", "keywords", "ads"):
        tf = d.get(level, {}).get(tf_key, {})
        lv[level] = (filter_channel(tf.get("current", {}), ch), filter_channel(tf.get("previous", {}), ch))

    curr_camps, prev_camps = lv["campaigns"]
    ct, pt = agg_totals(curr_camps), agg_totals(prev_camps)
    period_note = (f'Current: {tf_meta.get("current", {}).get("start", "?")} → {tf_meta.get("current", {}).get("end", "?")}'
                   f'  |  vs. previous: {tf_meta.get("previous", {}).get("start", "?")} → {tf_meta.get("previous", {}).get("end", "?")}'
                   f'  |  Channel: {esc(CHANNEL_LABELS.get(ch, ch))}')

    if not curr_camps and not prev_camps:
        return (f'<p class="period-note">{period_note}</p>'
                f'<p style="color:#888;font-size:13px;">No {esc(CHANNEL_LABELS.get(ch, ch))} campaigns in this period.</p>')

    sections = [
        build_summary_cards(ct, pt),
        f'<p class="period-note">{period_note}</p>',
        build_funnel_strip(ct, pt, order, labels),
        build_tab_insights(curr_camps, prev_camps, ct, pt, order, labels, devices, ch),
    ]
    if ch == "all":
        sections.append(build_channel_table(curr_camps, prev_camps, order, channels))
    sections.append(build_device_table(ct, pt, order, devices))

    for level in ("campaigns", "ad_groups", "keywords", "ads"):
        spec = LEVEL_SPECS[level]
        cur, prev = lv[level]
        sections.append(
            f'<div class="section-title" onclick="toggleSection(this)"><span class="arrow">▼</span> {spec["title"]}</div>'
            f'<div class="section-body">{build_section_hypothesis(level)}'
            f'{build_level_table(level, cur, prev, order, devices, tab_id)}</div>'
        )

    if tf_key in ("last_7d", "last_30d") and ch in ("all", "brand"):
        ai = d.get("auction_insights", {}).get(tf_key, [])
        sections.append(
            f'<div class="section-title" onclick="toggleSection(this)"><span class="arrow">▼</span> Auction Insights — Brand Campaigns</div>'
            f'<div class="section-body">{build_auction_insights_table(ai)}</div>'
        )
    return "\n".join(sections)


# ── Main generator ────────────────────────────────────────────────────
def generate(data: dict) -> str:
    logo = load_logo()
    meta = data.get("report_metadata", {})
    today = meta.get("generated", date.today().isoformat())
    timeframes_meta = meta.get("timeframes", {})
    labels = meta.get("stage_labels") or {}
    devices = device_order(data)

    # Channels present anywhere in the campaign data (ordered)
    camp_data = data.get("data", {}).get("campaigns", {})
    present = set()
    for tf in camp_data.values():
        for period in tf.values():
            for e in period.values():
                present.add(e.get("channel", e.get("type", "other")))
    channels = [c for c in ["brand", "generic", "pmax", "display", "other"] if c in present]

    all_stage_dicts = []
    for tf in camp_data.values():
        for period in tf.values():
            for e in period.values():
                all_stage_dicts.append(e.get("stages"))
    order = stage_order(data, *all_stage_dicts)

    channel_tabs = ['    <button class="tab-btn active" data-ch="all" onclick="switchChannel(\'all\')">All</button>']
    for ch in channels:
        channel_tabs.append(f'    <button class="tab-btn" data-ch="{ch}" onclick="switchChannel(\'{ch}\')">{esc(CHANNEL_LABELS.get(ch, ch))}</button>')

    parts = []
    for tf_key in ("last_7d", "last_14d", "last_30d"):
        tf_meta = timeframes_meta.get(tf_key, {})
        for ch in ["all"] + channels:
            active = ' active' if (tf_key == "last_7d" and ch == "all") else ''
            content = build_tab_content(tf_key, ch, tf_meta, data, order, labels, devices, channels)
            parts.append(f'<div class="tab-content{active}" id="tab-{tf_key}-{ch}">\n{content}\n</div>')

    with open(TEMPLATE_PATH) as f:
        template = f.read()
    return template.format(
        logo_b64=logo,
        date=today,
        channel_tabs_html="\n".join(channel_tabs),
        tabs_html="\n".join(parts),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data", nargs="?", default="/tmp/argos_perf_data.json")
    ap.add_argument("--preview", action="store_true", help="upload as performance-preview.html")
    ap.add_argument("--local", help="write HTML to this path and skip the S3 upload")
    ap.add_argument("--narrative", help="agent-written JSON (headline, findings, actions, channel_notes) for the Slack post")
    ap.add_argument("--post", action="store_true", help="post the Block Kit summary (+ details thread) to Slack")
    ap.add_argument("--to", default=None, help="Slack channel or user id for --post (default: Argos home channel)")
    ap.add_argument("--blocks-out", default="/tmp/argos_slack_blocks.json", help="write the Block Kit JSON here")
    args = ap.parse_args()

    if args.data == "-":
        data = json.load(sys.stdin)
    else:
        with open(args.data) as f:
            data = json.load(f)

    html_out = generate(data)
    if args.local:
        with open(args.local, "w", encoding="utf-8") as f:
            f.write(html_out)
        url = args.local
        print(url)
    else:
        url = upload_html(html_out, "performance-preview.html" if args.preview else "performance.html")
        print(url)

    narrative = {}
    if args.narrative:
        with open(args.narrative) as f:
            narrative = json.load(f)
    import argos_slack
    main_blocks, thread_blocks, text = argos_slack.build_blocks(data, narrative, url if not args.local else argos_slack.REPORT_URL)
    with open(args.blocks_out, "w", encoding="utf-8") as f:
        json.dump({"main": main_blocks, "thread": thread_blocks, "text": text}, f, indent=1, ensure_ascii=False)
    if args.post:
        channel = args.to or argos_slack.CHANNEL
        ts = argos_slack.post(main_blocks, text, channel)
        argos_slack.post(thread_blocks, "Details", channel, thread_ts=ts)
        print(f"SLACK_POSTED channel={channel} ts={ts}")


if __name__ == "__main__":
    main()
