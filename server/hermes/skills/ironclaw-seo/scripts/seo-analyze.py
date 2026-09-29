#!/usr/bin/env python3
"""seo-analyze.py - turn the raw GSC / GA4 / PR / live / news / outcome files of one run
into ONE structured dataset (seo-data-DATE.json) and a short markdown digest for the agent.

Usage:
  python3 seo-analyze.py --date YYYY-MM-DD [--memory DIR] [--out seo-data.json] [--digest digest.md]

Expects in --memory (all written by seo-data-fetch.sh):
  gsc-trend28-DATE.json      query,country,date rows for the 28-day window (recent + previous derived from it)
  gsc-pages-DATE.json        page,country rows, recent 7d
  gsc-pages-prev-DATE.json   page,country rows, previous 7d
  ga4-all-DATE.json / ga4-organic-DATE.json            recent 7d
  ga4-all-prev-DATE.json / ga4-organic-prev-DATE.json  previous 7d
  pr-impact-DATE.json        (optional) from pr-impact.py --json
  pr-open-DATE.json          (optional) open SEO-relevant PRs
  live-check-DATE.json       (optional) from seo-live-check.py
  news-DATE.json             (optional) from seo-news-fetch.py
  outcomes-DATE.json         (optional) from seo-outcomes.py

Every rule the analyst persona applies by hand is implemented here so the numbers and
the flags are deterministic: brand split, WoW deltas, 4-week trend, GA4 engagement and
organic share, GSC-vs-GA4 divergence, zero-click head-term skew (false position signal),
artifact-page exclusion, AI-Overview risk, UTM fragmentation, small-sample volatility,
3-week consecutive decline, bot/repeat-session ratio.
"""
import argparse
import os
import re
import sys
from collections import defaultdict
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from seo_common import *  # noqa


# ── aggregation helpers ───────────────────────────────────────────────
def agg_rows(rows):
    """rows with keys [query, country, date] -> per country totals + brand split."""
    out = {c: {"clicks": 0, "impressions": 0, "pos_w": 0.0, "brand_clicks": 0, "brand_imp": 0,
               "nonbrand_clicks": 0, "nonbrand_imp": 0} for c in COUNTRIES}
    for r in rows:
        c = r["keys"][1]
        if c not in out:
            continue
        d = out[c]
        d["clicks"] += r["clicks"]
        d["impressions"] += r["impressions"]
        d["pos_w"] += r["position"] * r["impressions"]
        k = "brand" if is_brand(r["keys"][0]) else "nonbrand"
        d[f"{k}_clicks"] += r["clicks"]
        d[f"{k}_imp"] += r["impressions"]
    for c, d in out.items():
        d["ctr"] = d["clicks"] / d["impressions"] if d["impressions"] else 0.0
        d["position"] = d["pos_w"] / d["impressions"] if d["impressions"] else 0.0
        d["brand_share"] = d["brand_clicks"] / d["clicks"] if d["clicks"] else 0.0
        del d["pos_w"]
    return out


def totals_of(agg):
    t = {"clicks": 0, "impressions": 0, "brand_clicks": 0, "nonbrand_clicks": 0}
    for d in agg.values():
        for k in t:
            t[k] += d[k]
    t["ctr"] = t["clicks"] / t["impressions"] if t["impressions"] else 0.0
    return t


def by_query(rows):
    q = defaultdict(lambda: {"clicks": 0, "impressions": 0, "pos_w": 0.0})
    for r in rows:
        k = (r["keys"][0], r["keys"][1])
        q[k]["clicks"] += r["clicks"]
        q[k]["impressions"] += r["impressions"]
        q[k]["pos_w"] += r["position"] * r["impressions"]
    return q


def daily(rows):
    d = defaultdict(lambda: defaultdict(lambda: {"clicks": 0, "impressions": 0}))
    for r in rows:
        d[r["keys"][1]][r["keys"][2]]["clicks"] += r["clicks"]
        d[r["keys"][1]][r["keys"][2]]["impressions"] += r["impressions"]
    return d


def in_window(row, win):
    return str(win[0]) <= row["keys"][2] <= str(win[1])


# ── main analysis ─────────────────────────────────────────────────────
def analyze(args):
    W = date_windows(date.fromisoformat(args.end) if args.end else None)
    D = args.date
    M = args.memory
    p = lambda name: os.path.join(M, name)

    trend = load_json(p(f"gsc-trend28-{D}.json"))
    if not trend:
        sys.exit(f"missing gsc-trend28-{D}.json")
    trows = trend["rows"]
    recent_rows = [r for r in trows if in_window(r, W["recent"])]
    prev_rows = [r for r in trows if in_window(r, W["previous"])]

    rec, prv = agg_rows(recent_rows), agg_rows(prev_rows)
    rq, pq = by_query(recent_rows), by_query(prev_rows)
    artifacts = load_artifacts()

    # ── 4-week trend ──
    weeks = []
    for i in range(4):
        ws = W["trend"][0] + timedelta(days=7 * i)
        we = ws + timedelta(days=6)
        wrows = [r for r in trows if str(ws) <= r["keys"][2] <= str(we)]
        weeks.append({"week": f"W{i + 1}", "start": str(ws), "end": str(we), "label": week_label(ws, we),
                      "by_market": {c: {"clicks": v["clicks"], "impressions": v["impressions"]}
                                    for c, v in agg_rows(wrows).items()}})
    trend_out = {c: [{"week": w["week"], "label": w["label"], "start": w["start"], "end": w["end"],
                      "clicks": w["by_market"][c]["clicks"], "impressions": w["by_market"][c]["impressions"]}
                     for w in weeks] for c in COUNTRIES}
    trend_out["_total"] = [{"week": w["week"], "label": w["label"], "start": w["start"], "end": w["end"],
                            "clicks": sum(v["clicks"] for v in w["by_market"].values()),
                            "impressions": sum(v["impressions"] for v in w["by_market"].values())} for w in weeks]

    # ── GA4 ──
    def ga4_map(name):
        d = load_json(p(name), {"rows": []}) or {"rows": []}
        return {r["country"]: r for r in d.get("rows", [])}
    ga_all, ga_org = ga4_map(f"ga4-all-{D}.json"), ga4_map(f"ga4-organic-{D}.json")
    ga_all_p, ga_org_p = ga4_map(f"ga4-all-prev-{D}.json"), ga4_map(f"ga4-organic-prev-{D}.json")

    def ga4_block(a, o):
        a = a or {}; o = o or {}
        os_ = o.get("sessions", 0); as_ = a.get("sessions", 0)
        return {
            "sessions": as_, "organic_sessions": os_,
            "organic_active_users": o.get("active_users", 0),
            "organic_share": os_ / as_ if as_ else 0.0,
            "engagement": 1.0 - o.get("bounce_rate", 1.0) if o else 0.0,
            "avg_duration": o.get("avg_session_duration", 0.0),
            "pages_per_session": (o.get("page_views", 0) / os_) if os_ else 0.0,
            "sessions_per_user": (os_ / o.get("active_users", 1)) if o.get("active_users") else 0.0,
        }
    ga4 = {}
    for c in COUNTRIES:
        r_, p_ = ga4_block(ga_all.get(c), ga_org.get(c)), ga4_block(ga_all_p.get(c), ga_org_p.get(c))
        ga4[c] = {"recent": r_, "previous": p_, "deltas": {
            "organic_sessions_pct": pct(r_["organic_sessions"], p_["organic_sessions"]),
            "sessions_pct": pct(r_["sessions"], p_["sessions"]),
            "engagement_pp": (r_["engagement"] - p_["engagement"]) * 100 if p_["organic_sessions"] else None,
        }}
    ga4_tot = {k: {"sessions": sum(ga4[c][k]["sessions"] for c in COUNTRIES),
                   "organic_sessions": sum(ga4[c][k]["organic_sessions"] for c in COUNTRIES)} for k in ("recent", "previous")}
    for k in ga4_tot:
        t = ga4_tot[k]; t["organic_share"] = t["organic_sessions"] / t["sessions"] if t["sessions"] else 0.0
    ga4_tot["deltas"] = {"organic_sessions_pct": pct(ga4_tot["recent"]["organic_sessions"], ga4_tot["previous"]["organic_sessions"])}

    # ── movers ──
    movers = {}
    for c in COUNTRIES:
        items = []
        for (q, cc) in set(k for k in rq if k[1] == c) | set(k for k in pq if k[1] == c):
            r_, p_ = rq.get((q, cc), {"clicks": 0, "impressions": 0}), pq.get((q, cc), {"clicks": 0, "impressions": 0})
            items.append({"query": q, "brand": is_brand(q), "delta": r_["clicks"] - p_["clicks"],
                          "recent_clicks": r_["clicks"], "prev_clicks": p_["clicks"], "recent_imp": r_["impressions"]})
        up = sorted([i for i in items if i["delta"] > 0], key=lambda i: -i["delta"])[:5]
        down = sorted([i for i in items if i["delta"] < 0], key=lambda i: i["delta"])[:5]
        movers[c] = {"up": up, "down": down}

    # ── zero-click head terms (false position signal) ──
    head_terms = {}
    adjusted = {}
    for c in COUNTRIES:
        qs = [(k[0], v) for k, v in rq.items() if k[1] == c]
        if not qs:
            continue
        top = max(qs, key=lambda kv: kv[1]["impressions"])
        q, v = top
        share = v["impressions"] / rec[c]["impressions"] if rec[c]["impressions"] else 0
        ctr = v["clicks"] / v["impressions"] if v["impressions"] else 0
        pos = v["pos_w"] / v["impressions"] if v["impressions"] else 0
        prev_v = pq.get((q, c), {"impressions": 0, "clicks": 0})
        head_terms[c] = {"query": q, "impressions": v["impressions"], "clicks": v["clicks"], "ctr": ctr,
                         "position": pos, "share_of_impressions": share, "prev_impressions": prev_v["impressions"],
                         "skew": bool(v["impressions"] >= HEAD_TERM_MIN_IMPRESSIONS and ctr < 0.001 and share >= 0.15)}
        # position/impressions excluding zero-click head terms (imp>=5000, ctr<0.1%)
        zc = [(k, vv) for k, vv in rq.items() if k[1] == c and vv["impressions"] >= HEAD_TERM_MIN_IMPRESSIONS
              and (vv["clicks"] / vv["impressions"] if vv["impressions"] else 0) < 0.001]
        zc_imp = sum(vv["impressions"] for _, vv in zc)
        zc_posw = sum(vv["pos_w"] for _, vv in zc)
        rem_imp = rec[c]["impressions"] - zc_imp
        rem_posw = (rec[c]["position"] * rec[c]["impressions"]) - zc_posw
        adjusted[c] = {"zero_click_queries": [k[0] for k, _ in zc], "zero_click_impressions": zc_imp,
                       "impressions": rem_imp, "position": rem_posw / rem_imp if rem_imp else 0.0,
                       "ctr": rec[c]["clicks"] / rem_imp if rem_imp else 0.0}

    # ── pages ──
    pages_r = load_json(p(f"gsc-pages-{D}.json"), {"rows": []}) or {"rows": []}
    pages_p = load_json(p(f"gsc-pages-prev-{D}.json"), {"rows": []}) or {"rows": []}
    prev_pages = {(r["keys"][0], r["keys"][1]): r for r in pages_p.get("rows", [])}
    pages = {c: [] for c in COUNTRIES}
    utm = {"recent": defaultdict(int), "previous": defaultdict(int)}
    for r in pages_r.get("rows", []):
        url, c = r["keys"][0], r["keys"][1]
        if c not in pages:
            continue
        pv = prev_pages.get((url, c), {"impressions": 0, "clicks": 0})
        art = artifact_match(url, artifacts)
        flag = None
        if art:
            flag = "artifact"
        elif "?utm_" in url or "&utm_" in url:
            flag = "utm"
        elif r["impressions"] >= AIO_MIN_IMPRESSIONS and r["ctr"] < AIO_MAX_CTR:
            flag = "aio"
        if "utm_" in url:
            utm["recent"][c] += r["impressions"]
        pages[c].append({"page": url, "path": path_of(url), "impressions": r["impressions"], "clicks": r["clicks"],
                         "ctr": r["ctr"], "position": r["position"], "prev_impressions": pv["impressions"],
                         "prev_clicks": pv["clicks"], "flag": flag, "artifact_label": art["label"] if art else None})
    for r in pages_p.get("rows", []):
        if "utm_" in r["keys"][0] and r["keys"][1] in utm["previous"] or "utm_" in r["keys"][0]:
            utm["previous"][r["keys"][1]] += r["impressions"]
    for c in pages:
        pages[c].sort(key=lambda x: -x["impressions"])
    top_pages = {c: pages[c][:8] for c in COUNTRIES}
    utm_out = {"recent_total": sum(utm["recent"].values()), "previous_total": sum(utm["previous"].values()),
               "by_market": {c: {"recent": utm["recent"].get(c, 0), "previous": utm["previous"].get(c, 0)} for c in COUNTRIES}}

    # ── per-market GSC block + deltas ──
    gsc = {}
    dly = daily(recent_rows)
    for c in COUNTRIES:
        r_, p_ = rec[c], prv[c]
        gsc[c] = {
            "recent": r_, "previous": p_,
            "deltas": {
                "clicks_pct": pct(r_["clicks"], p_["clicks"]),
                "impressions_pct": pct(r_["impressions"], p_["impressions"]),
                "position_delta": r_["position"] - p_["position"],
                "ctr_pp": (r_["ctr"] - p_["ctr"]) * 100,
                "brand_pct": pct(r_["brand_clicks"], p_["brand_clicks"]),
                "nonbrand_pct": pct(r_["nonbrand_clicks"], p_["nonbrand_clicks"]),
            },
            "daily": [{"date": d, **dly[c][d]} for d in sorted(dly[c])],
            "adjusted": adjusted.get(c),
            "head_term": head_terms.get(c),
        }
    totals = {"recent": totals_of(rec), "previous": totals_of(prv)}
    totals["deltas"] = {"clicks_pct": pct(totals["recent"]["clicks"], totals["previous"]["clicks"]),
                        "impressions_pct": pct(totals["recent"]["impressions"], totals["previous"]["impressions"])}

    # ── signals (the analyst rules) ──
    signals = []
    def sig(market, kind, severity, text):
        signals.append({"market": market, "type": kind, "severity": severity, "text": clean_text(text)})

    for c in COUNTRIES:
        code = COUNTRY_CODES[c]
        g, a = gsc[c], ga4[c]
        cd, od = g["deltas"]["clicks_pct"], a["deltas"]["organic_sessions_pct"]
        # GSC vs GA4 divergence
        if cd is not None and od is not None and cd != float("inf") and od != float("inf"):
            if (cd > 10 and od < -10) or (cd < -10 and od > 10):
                sig(c, "divergence", "high",
                    f"{code}: GSC clicks {fmt_pct(cd)} but GA4 organic sessions {fmt_pct(od)} "
                    f"({fmt_int(a['previous']['organic_sessions'])} to {fmt_int(a['recent']['organic_sessions'])}). "
                    f"Trust GA4 for direction; the GSC move is not showing up on site.")
            elif abs(cd) > 10 and abs(od) > 10:
                sig(c, "confirmed", "info",
                    f"{code}: GSC clicks {fmt_pct(cd)} and GA4 organic sessions {fmt_pct(od)} move together - the signal is real.")
        # zero-click head term skew
        ht = g["head_term"]
        if ht and ht["skew"]:
            adj = g["adjusted"]
            sig(c, "head_term_skew", "high",
                f"{code}: '{ht['query']}' is {ht['share_of_impressions'] * 100:.0f}% of impressions "
                f"({fmt_int(ht['impressions'])} imp, {ht['clicks']} clicks, position {ht['position']:.1f}). "
                f"Reported position {g['recent']['position']:.1f} is skewed; excluding zero-click head terms it is "
                f"{adj['position']:.1f}. Report {code} on clicks and sessions, not impressions or position.")
        # impressions down + clicks up = AIO absorbing informational queries
        idp = g["deltas"]["impressions_pct"]
        if idp is not None and idp != float("inf") and idp < -20 and cd is not None and cd != float("inf") and cd >= 0:
            sig(c, "aio_absorb", "info",
                f"{code}: impressions {fmt_pct(idp)} while clicks {fmt_pct(cd)} - zero-click informational queries "
                f"unwinding, remaining traffic is higher intent (CTR {g['recent']['ctr'] * 100:.2f}%).")
        # brand dependency / brand erosion
        if g["previous"]["brand_clicks"] > 10:
            bd = g["deltas"]["brand_pct"]
            if bd is not None and bd != float("inf") and abs(bd) >= 20:
                sig(c, "brand_move", "medium" if bd < 0 else "info",
                    f"{code}: brand clicks {fmt_pct(bd)} ({g['previous']['brand_clicks']} to {g['recent']['brand_clicks']}), "
                    f"brand share {g['recent']['brand_share'] * 100:.0f}% of clicks.")
        # small sample
        if g["recent"]["clicks"] < 120 and cd is not None and cd != float("inf") and abs(cd) >= 20:
            sig(c, "small_sample", "info",
                f"{code}: {fmt_pct(cd)} WoW on {g['recent']['clicks']} clicks - small sample, treat +/-20% as normal volatility.")
        # 3-week consecutive decline / growth
        wk = [w["clicks"] for w in trend_out[c]]
        if len(wk) == 4:
            if wk[0] > wk[1] > wk[2] > wk[3]:
                sig(c, "trend_down", "high", f"{code}: four consecutive weekly declines ({' -> '.join(str(x) for x in wk)}).")
            elif wk[0] < wk[1] < wk[2] < wk[3]:
                sig(c, "trend_up", "info", f"{code}: four consecutive weekly gains ({' -> '.join(str(x) for x in wk)}).")
        # bot / repeat sessions
        spu = a["recent"]["sessions_per_user"]
        if spu and spu > 3:
            sig(c, "bot_ratio", "medium",
                f"{code}: {spu:.1f} organic sessions per active user - suspect bot or repeat sessions; "
                f"treat engagement metrics with caution.")
        # AIO risk pages
        aio = [pg for pg in pages[c] if pg["flag"] == "aio"]
        if aio:
            top = aio[0]
            sig(c, "aio_pages", "medium",
                f"{code}: {len(aio)} page(s) with >{fmt_int(AIO_MIN_IMPRESSIONS)} impressions and CTR <0.5%; largest "
                f"{top['path']} ({fmt_int(top['impressions'])} imp, {top['clicks']} clicks).")
    # broken legacy redirects (WD / UX consolidations)
    live_pre = load_json(p(f"live-check-{D}.json"), {}) or {}
    broken = [r for r in live_pre.get("redirects", []) if not r.get("ok")]
    if broken:
        sig("all", "redirect_broken", "high",
            f"{len(broken)} legacy redirect(s) broken: " + ", ".join(
                f"{r['source'].replace(SITE, '')} -> HTTP {r['status']}" for r in broken[:4]) +
            (" ..." if len(broken) > 4 else "") + ". Fix in new-website-worker redirections before the old URLs re-index.")
    # UTM fragmentation
    if utm_out["recent_total"] or utm_out["previous_total"]:
        sig("all", "utm", "info",
            f"UTM-parameter URL variants: {fmt_int(utm_out['recent_total'])} impressions this week "
            f"(previous {fmt_int(utm_out['previous_total'])}).")
    # totals divergence
    tcd, tod = totals["deltas"]["clicks_pct"], ga4_tot["deltas"]["organic_sessions_pct"]
    if tcd is not None and tod is not None:
        sig("all", "totals", "info",
            f"Total GSC clicks {fmt_pct(tcd)} ({fmt_int(totals['previous']['clicks'])} to {fmt_int(totals['recent']['clicks'])}); "
            f"GA4 organic sessions {fmt_pct(tod)} ({fmt_int(ga4_tot['previous']['organic_sessions'])} to "
            f"{fmt_int(ga4_tot['recent']['organic_sessions'])}).")

    # ── optional inputs ──
    prs = {"merged": load_json(p(f"pr-impact-{D}.json"), []) or [],
           "open_seo": load_json(p(f"pr-open-{D}.json"), []) or []}
    live = load_json(p(f"live-check-{D}.json"), {}) or {}
    news = load_json(p(f"news-{D}.json"), []) or []
    outcomes = load_json(p(f"outcomes-{D}.json"), []) or []

    # ── backlog counts ──
    bl = load_json(BACKLOG_PATH, {"items": []}) or {"items": []}
    items = bl.get("items", [])
    open_items = [i for i in items if i.get("status") == "open"]
    backlog = {"open": len(open_items), "resolved": len([i for i in items if i.get("status") == "resolved"]),
               "high": len([i for i in open_items if i.get("impact") == "High"]),
               "medium": len([i for i in open_items if i.get("impact") == "Medium"]),
               "low": len([i for i in open_items if i.get("impact") == "Low"]),
               "version": bl.get("version"), "last_updated": bl.get("last_updated")}

    best = max(COUNTRIES, key=lambda c: (gsc[c]["deltas"]["clicks_pct"] if gsc[c]["deltas"]["clicks_pct"] not in (None, float("inf")) else -999))
    worst = min(COUNTRIES, key=lambda c: (gsc[c]["deltas"]["clicks_pct"] if gsc[c]["deltas"]["clicks_pct"] not in (None, float("inf")) else 999))

    data = {
        "generated": D,
        "windows": {k: {"start": str(v[0]), "end": str(v[1]), "label": week_label(v[0], v[1])}
                    for k, v in W.items() if k != "end"},
        "markets": COUNTRIES, "codes": COUNTRY_CODES, "names": COUNTRY_NAMES,
        "totals": totals, "best_market": best, "worst_market": worst,
        "gsc": gsc, "trend": trend_out, "ga4": ga4, "ga4_totals": ga4_tot,
        "movers": movers, "pages": top_pages, "utm": utm_out, "signals": signals,
        "prs": prs, "live": live, "news": news, "outcomes": outcomes, "backlog": backlog,
        "artifacts": artifacts,
    }
    save_json(args.out, data)
    with open(args.digest, "w") as f:
        f.write(digest(data))
    print(f"wrote {args.out} and {args.digest}", file=sys.stderr)


# ── digest for the agent ──────────────────────────────────────────────
def digest(d):
    L = []
    W = d["windows"]
    L.append(f"# SEO digest {d['generated']} - {W['recent']['label']} vs {W['previous']['label']}")
    L.append(f"Data file: seo-data-{d['generated']}.json (all numbers below come from it).")
    t, g4 = d["totals"], d["ga4_totals"]
    L.append(f"TOTAL clicks {fmt_int(t['recent']['clicks'])} ({fmt_pct(t['deltas']['clicks_pct'])} from {fmt_int(t['previous']['clicks'])}), "
             f"impressions {fmt_int(t['recent']['impressions'])} ({fmt_pct(t['deltas']['impressions_pct'])}), "
             f"GA4 organic sessions {fmt_int(g4['recent']['organic_sessions'])} ({fmt_pct(g4['deltas']['organic_sessions_pct'])} from {fmt_int(g4['previous']['organic_sessions'])}). "
             f"Best {d['codes'][d['best_market']]}, weakest {d['codes'][d['worst_market']]}.")
    L.append("")
    L.append("## Markets (GSC recent vs previous | GA4 organic)")
    for c in d["markets"]:
        g, a = d["gsc"][c], d["ga4"][c]
        r, p, dl = g["recent"], g["previous"], g["deltas"]
        L.append(f"- {d['codes'][c]}: clicks {r['clicks']} ({fmt_pct(dl['clicks_pct'])} from {p['clicks']}), "
                 f"brand {r['brand_clicks']} ({fmt_pct(dl['brand_pct'])}), non-brand {r['nonbrand_clicks']} ({fmt_pct(dl['nonbrand_pct'])}), "
                 f"imp {fmt_int(r['impressions'])} ({fmt_pct(dl['impressions_pct'])}), CTR {r['ctr'] * 100:.2f}%, "
                 f"pos {r['position']:.1f} ({dl['position_delta']:+.1f})"
                 + (f" [adj. pos excl. zero-click head terms {g['adjusted']['position']:.1f}]" if g.get('adjusted') and g['adjusted']['zero_click_queries'] else "")
                 + f" | GA4 organic {a['recent']['organic_sessions']} ({fmt_pct(a['deltas']['organic_sessions_pct'])}), "
                 f"engaged {a['recent']['engagement'] * 100:.1f}%, organic share {a['recent']['organic_share'] * 100:.1f}%, "
                 f"avg {a['recent']['avg_duration']:.0f}s")
    L.append("")
    L.append("## 4-week clicks (W1 oldest -> W4 recent)")
    for c in d["markets"]:
        wk = d["trend"][c]
        L.append(f"- {d['codes'][c]}: {' -> '.join(str(w['clicks']) for w in wk)}")
    L.append(f"- TOTAL: {' -> '.join(str(w['clicks']) for w in d['trend']['_total'])}")
    L.append("")
    L.append("## Signals (auto-detected, already applied rules)")
    for s in d["signals"]:
        L.append(f"- [{s['severity']}] {s['text']}")
    L.append("")
    L.append("## Top movers by clicks (top 3 each)")
    for c in d["markets"]:
        m = d["movers"][c]
        up = ", ".join(f"\"{i['query']}\"{' [brand]' if i['brand'] else ''} +{i['delta']} ({i['prev_clicks']}->{i['recent_clicks']})" for i in m["up"][:3]) or "none"
        dn = ", ".join(f"\"{i['query']}\"{' [brand]' if i['brand'] else ''} {i['delta']} ({i['prev_clicks']}->{i['recent_clicks']})" for i in m["down"][:3]) or "none"
        L.append(f"- {d['codes'][c]} up: {up}")
        L.append(f"- {d['codes'][c]} down: {dn}")
    L.append("")
    L.append("## Top pages by impressions (flag: aio = AI-Overview risk, artifact = excluded bot page, utm = tracking variant)")
    for c in d["markets"]:
        for pg in d["pages"][c][:4]:
            L.append(f"- {d['codes'][c]} {pg['path'][:70]}: {fmt_int(pg['impressions'])} imp ({fmt_int(pg['prev_impressions'])} prev), "
                     f"{pg['clicks']} clicks, CTR {pg['ctr'] * 100:.2f}%, pos {pg['position']:.1f}{(' [' + pg['flag'] + ']') if pg['flag'] else ''}")
    L.append("")
    if d["outcomes"]:
        L.append("## Fix outcomes (resolved backlog items, measured vs pre-fix baseline and vs market control)")
        for o in d["outcomes"]:
            L.append(f"- {o['id']} (fixed {o.get('fix_date')}): {o.get('summary', '')} -> VERDICT {o.get('verdict', '?').upper()}")
        L.append("")
    if d["prs"]["merged"]:
        L.append("## Merged PRs last 30d (pr-impact.py; template = not attributable)")
        for e in d["prs"]["merged"]:
            if e.get("type") == "template":
                continue
            L.append(f"- #{e['pr']} {e['repo'].split('/')[-1]} {e['merged']} [{e['type']}] {e['title'][:60]} :: {e.get('verdict', '')[:110]}")
        tmpl = [e for e in d["prs"]["merged"] if e.get("type") == "template"]
        if tmpl:
            L.append(f"- + {len(tmpl)} template/refactor PRs (not attributable): " + ", ".join(f"#{e['pr']} {e['title'][:35]}" for e in tmpl[:8]))
        L.append("")
    if d["prs"]["open_seo"]:
        L.append("## Open SEO-relevant PRs (fix written, awaiting merge)")
        for e in d["prs"]["open_seo"]:
            L.append(f"- #{e['number']} {e['repo'].split('/')[-1]}: {e['title'][:80]} (updated {e.get('updated_at', '')[:10]})")
        L.append("")
    if d["live"]:
        L.append("## Live site check (homepages + course pages)")
        for u in d["live"].get("pages", []):
            L.append(f"- {u['market']} {u['path']}: HTTP {u['status']}, title \"{(u.get('title') or 'MISSING')[:60]}\" ({u.get('title_len', 0)}c), "
                     f"desc {u.get('desc_len', 0)}c, OG {u.get('og_count', 0)}, hreflang {u.get('hreflang_count', 0)}"
                     f"{', x-default' if u.get('x_default') else ''}, canonical {'ok' if u.get('canonical_ok') else (u.get('canonical') or 'MISSING')}, "
                     f"schema {','.join(u.get('schema', [])) or 'none'}")
        rds = d["live"].get("redirects", [])
        if rds:
            L.append(f"- Legacy redirects (WD + UX consolidations): {len([r for r in rds if r.get('ok')])}/{len(rds)} OK")
        for iss in d["live"].get("issues", []):
            L.append(f"- ISSUE: {iss}")
        L.append("")
    if d["news"]:
        L.append("## News headlines (Google News RSS, last 10 days) - pick the 2-3 that matter")
        for n in d["news"][:15]:
            L.append(f"- {n.get('date', '')[:10]} {n.get('source', '')}: {n.get('title', '')[:110]}")
        L.append("")
    b = d["backlog"]
    L.append(f"## Backlog: {b['open']} open ({b['high']} High, {b['medium']} Medium, {b['low']} Low), {b['resolved']} resolved (v{b['version']}, updated {b['last_updated']})")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--end", default=None, help="GSC end date (default today-4)")
    ap.add_argument("--memory", default=MEMORY_DIR)
    ap.add_argument("--out", default=None)
    ap.add_argument("--digest", default=None)
    a = ap.parse_args()
    a.out = a.out or os.path.join(a.memory, f"seo-data-{a.date}.json")
    a.digest = a.digest or os.path.join(a.memory, f"seo-digest-{a.date}.md")
    analyze(a)
