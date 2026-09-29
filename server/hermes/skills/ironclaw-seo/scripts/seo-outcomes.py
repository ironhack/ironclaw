#!/usr/bin/env python3
"""seo-outcomes.py - did the fix change what we expected it to change?

For every resolved backlog item that carries an `outcome` definition (see seo-backlog.py
set-outcome), measure the chosen metric on the chosen pages/queries/markets:

  baseline  = the `baseline_days` (default 14) before fix_date
  post      = complete 7-day weeks starting fix_date + 3 days (crawl/index buffer),
              up to the latest GSC date available (today - 4)
  control   = the same metric for the whole market(s) over the same windows

and assign a verdict:
  measuring    fewer than 1 complete post week (or fewer than 3 weeks and no clear move yet)
  confirmed    moved in the expected direction by >= min_effect_pct AND clearly more than the market control
  beat_market  did not move as hoped in absolute terms, but outperformed the market control by >= min_effect_pct
  market_wide  moved, but the whole market moved the same way (not attributable to the fix)
  no_effect    3+ weeks measured and |effect| < min_effect_pct and no clear edge vs market
  regressed    moved the opposite way by >= min_effect_pct AND worse than (or no better than) the market
  new          baseline was zero and the pages now get traffic
  no_data      nothing in baseline nor post windows
Verdicts become `final` after horizon_weeks (default 8).

Writes outcomes-DATE.json and stores `outcome.last` on each backlog item.
Usage: python3 seo-outcomes.py [--date YYYY-MM-DD] [--out outcomes.json] [--dry-run]
"""
import argparse
import os
import re
import sys
from collections import defaultdict
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from seo_common import *  # noqa

BUFFER_DAYS = 3


def metric_value(rows, metric):
    """rows: list of {clicks, impressions, position}. Returns aggregated metric value."""
    clicks = sum(r["clicks"] for r in rows)
    imp = sum(r["impressions"] for r in rows)
    if metric == "clicks":
        return clicks
    if metric == "impressions":
        return imp
    if metric == "ctr":
        return clicks / imp if imp else 0.0
    if metric == "position":
        return (sum(r["position"] * r["impressions"] for r in rows) / imp) if imp else 0.0
    return 0.0


def window_stats(day_rows, start, end, metric):
    """day_rows: {date: [rows]} -> value over [start, end]; for count metrics also daily avg."""
    days = [(start + timedelta(days=i)) for i in range((end - start).days + 1)]
    rows = [r for d in days for r in day_rows.get(str(d), [])]
    val = metric_value(rows, metric)
    n = len(days)
    if metric in ("clicks", "impressions"):
        return {"total": val, "daily_avg": val / n if n else 0.0, "days": n}
    return {"total": val, "daily_avg": val, "days": n}


def effect(base, post, metric, direction):
    """Signed effect in the expected direction (positive = moved as hoped)."""
    b, p = base["daily_avg"], post["daily_avg"]
    if metric == "position":
        if not b:
            return None
        raw = (b - p) / b * 100.0          # lower position is better
    else:
        if not b:
            return None if not p else float("inf")
        raw = (p - b) / b * 100.0
    return raw if direction == "up" else -raw


def measure_item(item, creds, control_days, end):
    oc = item["outcome"]
    metric, direction = oc["metric"], oc["direction"]
    fix = date.fromisoformat(oc["fix_date"])
    base_start = fix - timedelta(days=oc.get("baseline_days", 14))
    base_end = fix - timedelta(days=1)
    post_start = fix + timedelta(days=BUFFER_DAYS)
    scope = oc.get("scope", {})
    markets = scope.get("markets") or None
    out = {"id": item["id"], "issue": clean_text(item.get("issue", ""))[:160], "hypothesis": clean_text(oc.get("hypothesis", "")),
           "metric": metric, "direction": direction, "fix_date": oc["fix_date"], "scope": scope,
           "baseline_window": {"start": str(base_start), "end": str(base_end)}, "post_weeks": [], "final": False}

    if metric == "sessions":
        out.update({"verdict": "unsupported", "summary": "sessions outcome needs GA4 page data (not wired yet)"})
        return out

    filters = [{"dimension": "page", "operator": "includingRegex", "expression": scope["pages_regex"]}]
    if scope.get("queries_regex"):
        filters.append({"dimension": "query", "operator": "includingRegex", "expression": scope["queries_regex"]})
    try:
        rows = gsc_query(base_start, end, ["page", "country", "date"], creds=creds, filters=filters)
    except RuntimeError as e:
        out.update({"verdict": "error", "summary": str(e)[:160]})
        return out
    if markets:
        rows = [r for r in rows if r["keys"][1] in markets]
    day_rows = defaultdict(list)
    for r in rows:
        day_rows[r["keys"][2]].append(r)
    ctrl_rows = defaultdict(list)
    for d, lst in control_days.items():
        ctrl_rows[d] = [r for r in lst if not markets or r["keys"][0] in markets]

    base = window_stats(day_rows, base_start, base_end, metric)
    cbase = window_stats(ctrl_rows, base_start, base_end, metric)
    out["baseline"] = base
    out["pages_seen"] = len(set(r["keys"][0] for r in rows))

    # complete post weeks
    weeks = []
    ws = post_start
    while ws + timedelta(days=6) <= end:
        we = ws + timedelta(days=6)
        w = window_stats(day_rows, ws, we, metric)
        cw = window_stats(ctrl_rows, ws, we, metric)
        w.update({"start": str(ws), "end": str(we), "label": week_label(ws, we),
                  "effect_pct": effect(base, w, metric, direction),
                  "control_pct": effect(cbase, cw, metric, direction)})
        weeks.append(w)
        ws = we + timedelta(days=1)
    out["post_weeks"] = weeks
    days_post = max(0, (end - post_start).days + 1)
    out["days_post"] = days_post
    out["weeks_measured"] = len(weeks)
    horizon = oc.get("horizon_weeks", 8)
    min_eff = float(oc.get("min_effect_pct", 10))

    if not weeks:
        out.update({"verdict": "measuring", "summary": f"{days_post} day(s) of post-fix data, first complete week not reached"})
        return out

    post_all = window_stats(day_rows, post_start, weeks[-1]["end"] and date.fromisoformat(weeks[-1]["end"]), metric)
    cpost_all = window_stats(ctrl_rows, post_start, date.fromisoformat(weeks[-1]["end"]), metric)
    eff = effect(base, post_all, metric, direction)
    ctrl = effect(cbase, cpost_all, metric, direction)
    latest = weeks[-1]
    out.update({"post": post_all, "effect_pct": eff, "control_pct": ctrl,
                "latest_week_effect_pct": latest["effect_pct"],
                "net_pct": (eff - ctrl) if (eff not in (None, float("inf")) and ctrl not in (None, float("inf"))) else None})

    unit = {"clicks": "clicks/day", "impressions": "imp/day", "ctr": "CTR", "position": "avg position"}[metric]
    def fv(v):
        if metric == "ctr":
            return f"{v * 100:.2f}%"
        return f"{v:.1f}"
    base_s, post_s = fv(base["daily_avg"]), fv(post_all["daily_avg"])
    sign = 1 if direction == "up" else -1
    raw = (eff * sign) if eff not in (None, float("inf")) else eff          # raw % change of the metric
    raw_ctrl = (ctrl * sign) if ctrl not in (None, float("inf")) else ctrl
    raw_latest = (latest["effect_pct"] * sign) if latest["effect_pct"] not in (None, float("inf")) else latest["effect_pct"]
    out["raw_pct"], out["raw_control_pct"], out["raw_latest_pct"] = raw, raw_ctrl, raw_latest

    # context metrics so a CTR move can be read against clicks/impressions
    ctx = {}
    for m in ("clicks", "impressions", "ctr", "position"):
        if m == metric:
            continue
        b = window_stats(day_rows, base_start, base_end, m)["daily_avg"]
        pp = window_stats(day_rows, post_start, date.fromisoformat(weeks[-1]["end"]), m)["daily_avg"]
        ctx[m] = {"baseline": b, "post": pp, "pct": pct(pp, b)}
    out["context"] = ctx
    def cfmt(m):
        c = ctx[m]
        if m == "ctr":
            return f"CTR {c['baseline'] * 100:.2f}%->{c['post'] * 100:.2f}%"
        if m == "position":
            return f"pos {c['baseline']:.1f}->{c['post']:.1f}"
        return f"{m}/day {c['baseline']:.1f}->{c['post']:.1f} ({fmt_pct(c['pct'], 0)})"
    ctx_s = ", ".join(cfmt(m) for m in ("clicks", "impressions", "ctr", "position") if m in ctx and m != "position")

    # volume guard: rates on tiny samples are noise
    base_imp = window_stats(day_rows, base_start, base_end, "impressions")["total"]
    post_imp = window_stats(day_rows, post_start, date.fromisoformat(weeks[-1]["end"]), "impressions")["total"]
    base_clk = window_stats(day_rows, base_start, base_end, "clicks")["total"]
    post_clk = window_stats(day_rows, post_start, date.fromisoformat(weeks[-1]["end"]), "clicks")["total"]
    low_volume = ((metric in ("ctr", "position") and (base_imp < 300 or post_imp < 150))
                  or (metric == "clicks" and base_clk + post_clk < 30))
    out["low_volume"] = low_volume

    if base["daily_avg"] == 0 and post_all["daily_avg"] == 0:
        verdict, why = "no_data", "no traffic in baseline or post windows"
    elif low_volume and base["daily_avg"] > 0:
        verdict = "low_volume"
        why = (f"too little volume to judge ({fmt_int(base_imp)} baseline imp / {fmt_int(base_clk)} clicks, "
               f"{fmt_int(post_imp)} post imp / {fmt_int(post_clk)} clicks): {unit} {base_s} -> {post_s} "
               f"({fmt_pct((eff * sign) if eff not in (None, float('inf')) else eff, 0)}) over {len(weeks)} week(s). {ctx_s}")
    elif base["daily_avg"] == 0:
        verdict, why = "new", f"no baseline; now {post_s} {unit} over {len(weeks)} week(s). {ctx_s}"
    elif eff is None:
        verdict, why = "no_data", "cannot compute"
    else:
        ctrl_s = f"market {fmt_pct(raw_ctrl, 0)}" if raw_ctrl not in (None, float("inf")) else "market n/a"
        net = out["net_pct"]
        if len(weeks) < 2:
            verdict = "measuring"
            lead = "early read (1 week): "
        else:
            lead = ""
            if net is None:  # no control available: judge on the raw effect only
                verdict = ("confirmed" if eff >= min_eff else "regressed" if eff <= -min_eff
                           else "no_effect" if len(weeks) >= 3 else "measuring")
            elif eff >= min_eff and net >= min_eff / 2:
                verdict = "confirmed"          # moved as hoped, and more than the market
            elif eff <= -min_eff and net <= -min_eff / 2:
                verdict = "regressed"          # moved the wrong way, and worse than the market
            elif net >= min_eff:
                verdict = "beat_market"        # did not rise (or fell) but clearly outperformed the market
            elif abs(eff) >= min_eff:
                verdict = "market_wide"        # moved, but the whole market moved the same way
            elif len(weeks) >= 3:
                verdict = "no_effect"
            else:
                verdict = "measuring"
        why = (f"{lead}{unit} {base_s} -> {post_s} ({fmt_pct(raw, 0)}, expected {direction}; {ctrl_s}) over "
               f"{len(weeks)} week(s), latest {fmt_pct(raw_latest, 0)}. Context: {ctx_s}")
    if len(weeks) >= horizon and verdict not in ("measuring",):
        out["final"] = True
    out.update({"verdict": verdict, "summary": why})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--out", default=None)
    ap.add_argument("--end", default=None, help="last GSC date to use (default today-4)")
    ap.add_argument("--dry-run", action="store_true", help="do not write outcome.last back to the backlog")
    a = ap.parse_args()
    out_path = a.out or os.path.join(MEMORY_DIR, f"outcomes-{a.date}.json")
    end = date.fromisoformat(a.end) if a.end else date.today() - timedelta(days=GSC_LAG_DAYS)

    bl = load_json(BACKLOG_PATH)
    if not bl:
        sys.exit("cannot read backlog")
    items = [i for i in bl["items"] if i.get("outcome") and not i["outcome"].get("not_measurable")
             and i["outcome"].get("fix_date") and i["outcome"].get("scope", {}).get("pages_regex")]
    results = []
    if items:
        creds = gsc_creds()
        earliest = min(date.fromisoformat(i["outcome"]["fix_date"]) - timedelta(days=i["outcome"].get("baseline_days", 14)) for i in items)
        earliest = max(earliest, end - timedelta(days=480))
        print(f"outcomes: {len(items)} item(s); control window {earliest}..{end}", file=sys.stderr)
        try:
            ctrl = gsc_query(earliest, end, ["country", "date"], creds=creds, countries=set(COUNTRIES))
        except RuntimeError as e:
            print(f"control query failed: {e}", file=sys.stderr)
            ctrl = []
        control_days = defaultdict(list)
        for r in ctrl:
            control_days[r["keys"][1]].append(r)
        for it in items:
            try:
                res = measure_item(it, creds, control_days, end)
            except Exception as e:  # noqa
                res = {"id": it["id"], "verdict": "error", "summary": f"{type(e).__name__}: {e}"[:160], "fix_date": it["outcome"].get("fix_date")}
            res["measured"] = a.date
            results.append(res)
            print(f"  {it['id']:40s} {res['verdict']:12s} {res.get('summary', '')[:100]}", file=sys.stderr)
            if not a.dry_run:
                it["outcome"]["last"] = {k: res.get(k) for k in ("measured", "verdict", "effect_pct", "control_pct", "net_pct", "weeks_measured", "summary", "final")}
    # not-measurable items are listed too so the report can show them
    for i in bl["items"]:
        oc = i.get("outcome")
        if oc and oc.get("not_measurable"):
            results.append({"id": i["id"], "issue": clean_text(i.get("issue", ""))[:160], "fix_date": oc.get("fix_date"),
                            "verdict": "not_measurable", "summary": oc.get("reason", ""), "measured": a.date})
    order = {"regressed": 0, "no_effect": 1, "confirmed": 2, "beat_market": 3, "market_wide": 4, "measuring": 5, "new": 6,
             "low_volume": 7, "no_data": 8, "error": 9, "unsupported": 10, "not_measurable": 11}
    results.sort(key=lambda r: (order.get(r["verdict"], 9), r.get("fix_date") or ""), reverse=False)
    save_json(out_path, results)
    if not a.dry_run and items:
        save_json(BACKLOG_PATH, bl)
    print(f"wrote {out_path} ({len(results)} outcomes)", file=sys.stderr)


if __name__ == "__main__":
    main()
