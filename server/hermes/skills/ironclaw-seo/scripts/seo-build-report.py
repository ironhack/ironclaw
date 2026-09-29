#!/usr/bin/env python3
"""seo-build-report.py - deterministic HTML report + Slack draft from seo-data-DATE.json.

Usage:
  python3 seo-build-report.py --date YYYY-MM-DD [--narrative /tmp/seo-narrative.json]
                              [--upload] [--preview] [--local /tmp/report.html]

Inputs
  memory/seo-data-DATE.json      from seo-analyze.py (all numbers)
  narrative JSON (optional)      written by the agent; every key optional:
    {
      "tldr": ["...", "...", "..."],                       2-3 bullets, lead with decisions
      "insights": {"snapshot": "...", "trend": "...", "engagement": "...", "movers": "...",
                   "pages": "...", "outcomes": "...", "prs": "...", "live": "..."},
      "market_notes": {"esp": "one line", ...},           engagement table insight column
      "intel": [{"title": "...", "source": "...", "date": "YYYY-MM-DD", "why": "..."}],
      "findings": ["what, where, what to do", ...],       2-4 items
      "pr_notes": {"44": "...", "42": "..."},             per merged PR interpretation
      "in_flight": {"og-tags-missing": 666, ...},         backlog id -> open PR number
      "quick_wins": ["...", "..."],
      "traffic_quality": "1-2 lines",
      "research_line": "1-2 lines for Slack, optional"
    }
  seo-backlog.json               live backlog (never transcribed)

Outputs
  /tmp/seo-report-DATE.html (+ upload to s3://ih-ironclaw/seo/DATE/report.html unless --preview -> seo/preview/report.html)
  /tmp/seo-slack-DATE.txt   Slack post draft with every number pre-filled
  prints: the public URL (first line) then the Slack draft
"""
import argparse
import html
import json
import os
import subprocess
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from seo_common import *  # noqa

BUCKET = "ih-ironclaw"
REGION = "eu-west-1"
PUBLIC = f"https://{BUCKET}.s3.{REGION}.amazonaws.com"


def esc(s):
    return html.escape(clean_text(str(s if s is not None else "")), quote=True)


def pc(v, digits=1):
    """percentage delta span"""
    if v is None:
        return '<span class="delta flat">n/a</span>'
    if v == float("inf"):
        return '<span class="delta up">new</span>'
    cls = "up" if v > 2 else ("down" if v < -2 else "flat")
    return f'<span class="delta {cls}">{fmt_pct(v, digits)}</span>'


def pc_inv(v):
    """for metrics where down is good (nothing here yet, kept for symmetry)"""
    return pc(v)


def pos_delta(v):
    if v is None:
        return ""
    cls = "down" if v > 0.3 else ("up" if v < -0.3 else "flat")
    return f'<span class="delta {cls}">{v:+.1f}</span>'


def secs(v):
    return f"{int(round(v)):,}s"


def arrow(vals):
    if len(vals) < 2:
        return ""
    first, last = vals[0], vals[-1]
    ch = pct(last, first)
    if ch is None:
        return ""
    if last > vals[1] > vals[0] if len(vals) > 2 else last > first:
        pass
    cls = "up" if ch > 5 else ("down" if ch < -5 else "flat")
    sym = "&#8593;" if cls == "up" else ("&#8595;" if cls == "down" else "&#8594;")
    return f'<span class="arrow-{cls}">{sym}</span> {fmt_pct(ch, 0)} vs W1'


# ── sections ──────────────────────────────────────────────────────────
def sec_header(d):
    W = d["windows"]
    mk = "".join(f'<span class="mkt">{d["codes"][c]} {d["names"][c]}</span>' for c in d["markets"])
    return f'''<header><h1>Ironhack SEO Report</h1>
<div class="sub">{esc(W["recent"]["label"])}, {W["recent"]["end"][:4]} vs {esc(W["previous"]["label"])} (WoW) &middot; generated {esc(d["generated"])}</div>
<div class="mkts">{mk}</div></header>'''


def sec_snapshot(d, N):
    t, g4 = d["totals"], d["ga4_totals"]
    best, worst = d["best_market"], d["worst_market"]
    imp_r, imp_p = t["recent"]["impressions"], t["previous"]["impressions"]
    cards = [
        ("Total clicks", fmt_int(t["recent"]["clicks"]), f'{pc(t["deltas"]["clicks_pct"])} ({fmt_int(t["previous"]["clicks"])} to {fmt_int(t["recent"]["clicks"])})'),
        ("Total impressions", f'{imp_r / 1000:.1f}K', f'{pc(t["deltas"]["impressions_pct"])} ({imp_p / 1000:.1f}K to {imp_r / 1000:.1f}K)'),
        ("Overall CTR", f'{t["recent"]["ctr"] * 100:.2f}%', f'from {t["previous"]["ctr"] * 100:.2f}%'),
        ("GA4 organic sessions", fmt_int(g4["recent"]["organic_sessions"]), f'{pc(g4["deltas"]["organic_sessions_pct"])} ({fmt_int(g4["previous"]["organic_sessions"])} to {fmt_int(g4["recent"]["organic_sessions"])})'),
        ("Best market (WoW)", d["codes"][best], f'{pc(d["gsc"][best]["deltas"]["clicks_pct"])} clicks'),
        ("Weakest market (WoW)", d["codes"][worst], f'{pc(d["gsc"][worst]["deltas"]["clicks_pct"])} clicks'),
    ]
    cards_html = "".join(f'<div class="card"><div class="lbl">{esc(l)}</div><div class="val num">{v}</div><div class="note">{n}</div></div>' for l, v, n in cards)
    rows = ""
    for c in d["markets"]:
        g, a = d["gsc"][c], d["ga4"][c]
        r, dl = g["recent"], g["deltas"]
        adj = g.get("adjusted") or {}
        pos_cell = f'{r["position"]:.1f} {pos_delta(dl["position_delta"])}'
        if adj.get("zero_click_queries"):
            pos_cell += f'<div class="tiny">excl. zero-click: {adj["position"]:.1f}</div>'
        rows += (f'<tr><td><b>{d["codes"][c]}</b></td><td class="num">{r["clicks"]}</td><td>{pc(dl["clicks_pct"])}</td>'
                 f'<td class="num">{fmt_int(r["impressions"])} <span class="tiny">{fmt_pct(dl["impressions_pct"], 0)}</span></td>'
                 f'<td class="num">{r["ctr"] * 100:.2f}%</td><td class="num">{pos_cell}</td>'
                 f'<td class="num">{r["brand_clicks"]} / {r["nonbrand_clicks"]}<div class="tiny">{fmt_pct(dl["brand_pct"], 0)} / {fmt_pct(dl["nonbrand_pct"], 0)}</div></td>'
                 f'<td class="num">{a["recent"]["organic_sessions"]} {pc(a["deltas"]["organic_sessions_pct"], 0)}</td>'
                 f'<td class="num">{a["recent"]["engagement"] * 100:.1f}%</td><td class="num">{a["recent"]["organic_share"] * 100:.1f}%</td></tr>')
    insight = N.get("insights", {}).get("snapshot") or auto_snapshot_insight(d)
    return f'''<h2>Performance Snapshot</h2><div class="cards">{cards_html}</div>
<h2>Per-Market Combined View (GSC + GA4)</h2>
<table><thead><tr><th>Mkt</th><th>Clicks</th><th>WoW</th><th>Impr.</th><th>CTR</th><th>Avg pos</th><th>Brand / Non</th><th>Org sessions</th><th>Engage</th><th>Org share</th></tr></thead>
<tbody>{rows}</tbody></table>
<div class="insight">{esc(insight)}</div>'''


def auto_snapshot_insight(d):
    sig = [s["text"] for s in d["signals"] if s["type"] in ("totals", "divergence", "confirmed")]
    return " ".join(sig[:3]) if sig else "No notable divergence between GSC and GA4 this cycle."


def sec_trend(d, N):
    weeks = d["trend"]["_total"]
    head = "".join(f'<th>{w["week"]} ({esc(w["label"])})</th>' for w in weeks)
    rows = ""
    for c in d["markets"] + ["_total"]:
        wk = d["trend"][c]
        vals = [w["clicks"] for w in wk]
        cells = "".join(f'<td class="num">{v}</td>' for v in vals)
        label = "<b>Total</b>" if c == "_total" else f'<b>{d["codes"][c]}</b>'
        rows += f'<tr{" class=total" if c == "_total" else ""}><td>{label}</td>{cells}<td>{arrow(vals)}</td></tr>'
    insight = N.get("insights", {}).get("trend") or auto_trend_insight(d)
    return f'''<h2>4-Week Click Trend</h2>
<table><thead><tr><th>Mkt</th>{head}<th>Trend</th></tr></thead><tbody>{rows}</tbody></table>
<div class="insight">{esc(insight)}</div>'''


def auto_trend_insight(d):
    parts = []
    for c in d["markets"]:
        vals = [w["clicks"] for w in d["trend"][c]]
        ch = pct(vals[-1], vals[0])
        if ch is not None and ch != float("inf") and abs(ch) >= 25:
            parts.append(f"{d['codes'][c]} {fmt_pct(ch, 0)} over four weeks ({vals[0]} to {vals[-1]})")
    return ("; ".join(parts) + ".") if parts else "No market moved more than 25% over the four-week window."


def sec_engagement(d, N):
    rows = ""
    notes = N.get("market_notes", {})
    for c in d["markets"]:
        a = d["ga4"][c]["recent"]; dl = d["ga4"][c]["deltas"]
        note = notes.get(c) or auto_market_note(d, c)
        rows += (f'<tr><td><b>{d["codes"][c]}</b></td><td class="num">{a["organic_sessions"]} {pc(dl["organic_sessions_pct"], 0)}</td>'
                 f'<td class="num">{a["engagement"] * 100:.1f}%' + (f' <span class="tiny">{dl["engagement_pp"]:+.1f}pp</span>' if dl.get("engagement_pp") is not None else "") + '</td>'
                 f'<td class="num">{a["organic_share"] * 100:.1f}%</td><td class="num">{secs(a["avg_duration"])}</td>'
                 f'<td class="num">{a["pages_per_session"]:.2f}</td><td class="num">{a["sessions_per_user"]:.1f}</td><td>{esc(note)}</td></tr>')
    insight = N.get("insights", {}).get("engagement") or N.get("traffic_quality") or auto_engagement_insight(d)
    return f'''<h2>Engagement &amp; Traffic Quality (GA4 organic)</h2>
<table><thead><tr><th>Mkt</th><th>Org sessions</th><th>Engagement</th><th>Org share</th><th>Avg duration</th><th>Pages/session</th><th>Sessions/user</th><th>Insight</th></tr></thead>
<tbody>{rows}</tbody></table><div class="insight">{esc(insight)}</div>'''


def auto_market_note(d, c):
    a = d["ga4"][c]["recent"]
    g = d["gsc"][c]
    bits = []
    if a["engagement"] >= 0.5:
        bits.append(f"engaged {a['engagement'] * 100:.0f}%")
    else:
        bits.append(f"low engagement {a['engagement'] * 100:.0f}%")
    if g["recent"]["brand_share"] >= 0.6:
        bits.append(f"brand-dependent ({g['recent']['brand_share'] * 100:.0f}% brand clicks)")
    if g["recent"]["position"] >= 15:
        bits.append(f"discovery bottleneck (avg pos {g['recent']['position']:.1f})")
    return ", ".join(bits).capitalize() + "."


def auto_engagement_insight(d):
    best = max(d["markets"], key=lambda c: d["ga4"][c]["recent"]["engagement"])
    worst = min(d["markets"], key=lambda c: d["ga4"][c]["recent"]["engagement"])
    bots = [s["text"] for s in d["signals"] if s["type"] == "bot_ratio"]
    txt = (f"{d['codes'][best]} has the most engaged organic visitors ({d['ga4'][best]['recent']['engagement'] * 100:.1f}%), "
           f"{d['codes'][worst]} the least ({d['ga4'][worst]['recent']['engagement'] * 100:.1f}%).")
    return txt + (" " + " ".join(bots) if bots else " Sessions-per-user ratios are healthy (no bot signal).")


def sec_movers(d, N):
    boxes = ""
    for c in d["markets"]:
        m = d["movers"][c]
        def li(i, cls):
            tag = " [brand]" if i["brand"] else ""
            sign = "+" if i["delta"] > 0 else ""
            return f'<li><span class="{cls}">{sign}{i["delta"]}</span> {esc(i["query"][:60])}{tag} ({i["prev_clicks"]} to {i["recent_clicks"]})</li>'
        ups = "".join(li(i, "gain") for i in m["up"][:3]) or "<li class=tiny>no gainers</li>"
        dns = "".join(li(i, "loss") for i in m["down"][:3]) or "<li class=tiny>no losers</li>"
        boxes += f'<div class="mover"><h3>{d["codes"][c]} - Gainers</h3><ul>{ups}</ul><h3>Losers</h3><ul>{dns}</ul></div>'
    insight = N.get("insights", {}).get("movers") or ""
    return f'<h2>Top Movers (by clicks, top 3 each)</h2><div class="movers">{boxes}</div>' + (f'<div class="insight">{esc(insight)}</div>' if insight else "")


def sec_pages(d, N):
    rows = ""
    allp = [(c, p) for c in d["markets"] for p in d["pages"][c]]
    allp.sort(key=lambda x: -x[1]["impressions"])
    for c, p in allp[:14]:
        flag = {"aio": "AIO absorb", "artifact": f"bot artifact ({p['artifact_label']})", "utm": "UTM variant"}.get(p["flag"], "")
        cls = ' class="aio-warn"' if p["flag"] == "aio" else (' class="muted"' if p["flag"] == "artifact" else "")
        rows += (f'<tr{cls}><td>{d["codes"][c]}</td><td class="url">{esc(p["path"][:80])}</td><td class="num">{fmt_int(p["impressions"])}'
                 f' <span class="tiny">{fmt_pct(pct(p["impressions"], p["prev_impressions"]), 0)}</span></td>'
                 f'<td class="num">{p["clicks"]}</td><td class="num">{p["ctr"] * 100:.2f}%</td><td class="num">{p["position"]:.1f}</td><td>{esc(flag)}</td></tr>')
    insight = N.get("insights", {}).get("pages") or auto_pages_insight(d)
    return f'''<h2>Top Pages &amp; AI Overviews Risk</h2>
<table><thead><tr><th>Mkt</th><th>Page</th><th>Impr. (WoW)</th><th>Clicks</th><th>CTR</th><th>Pos</th><th>Flag</th></tr></thead><tbody>{rows}</tbody></table>
<div class="insight">{esc(insight)}</div>'''


def auto_pages_insight(d):
    sig = [s["text"] for s in d["signals"] if s["type"] in ("head_term_skew", "aio_pages", "utm")]
    return " ".join(sig[:3]) if sig else "No page crosses the AI-Overview risk threshold (>5,000 impressions at <0.5% CTR)."


VERDICT_STYLE = {
    "confirmed": ("v-ok", "Confirmed"), "beat_market": ("v-ok", "Beat market"), "market_wide": ("v-warn", "Market-wide move"), "measuring": ("v-wait", "Measuring"),
    "no_effect": ("v-bad", "No effect"), "regressed": ("v-bad", "Regressed"), "new": ("v-ok", "New traffic"),
    "no_data": ("v-mute", "No data"), "low_volume": ("v-mute", "Low volume"), "not_measurable": ("v-mute", "Not measurable"), "error": ("v-mute", "Error"),
    "unsupported": ("v-mute", "Unsupported"),
}


def scope_summary(regex):
    """Human-readable version of a pages regex: single path, or 'N URLs, e.g. /a, /b'."""
    import re as _re
    r = (regex or "").strip()
    inner = r
    m = _re.fullmatch(r"\^\((.*)\)/\?\$", r) or _re.fullmatch(r"\^\((.*)\)\$", r)
    if m:
        inner = m.group(1)
    parts = [p for p in inner.split("|") if p]
    paths = [_re.sub(r"\\(.)", r"\1", p).replace(SITE, "") for p in parts]
    if len(paths) <= 3:
        return ", ".join(paths) if paths else r
    return f"{len(paths)} URLs, e.g. {', '.join(paths[:3])}"


def sec_outcomes(d, N):
    oc_all = d.get("outcomes") or []
    oc = [o for o in oc_all if o["verdict"] != "not_measurable"]
    nm = [o for o in oc_all if o["verdict"] == "not_measurable"]
    if not oc:
        body = '<div class="notice">No resolved backlog item has a measurable outcome definition yet. Use <code>seo-backlog.py set-outcome</code> when resolving an item so the fix can be measured here.</div>'
    else:
        rows = ""
        for o in oc:
            cls, label = VERDICT_STYLE.get(o["verdict"], ("v-mute", o["verdict"]))
            scope = o.get("scope") or {}
            what = f'{o.get("metric", "")} {o.get("direction", "")} on <span class="url">{esc(scope_summary(scope.get("pages_regex", "")))}</span>'
            if scope.get("markets"):
                what += f' ({", ".join(d["codes"].get(m, m) for m in scope["markets"])})'
            if scope.get("queries_regex"):
                what += f' queries <span class="url">{esc(scope["queries_regex"])}</span>'
            weeks = o.get("post_weeks") or []
            spark = " &middot; ".join(f'{esc(w["label"])}: {fmt_pct(w["effect_pct"], 0)}' for w in weeks[-4:]) if weeks else ""
            base = o.get("baseline", {}); post = o.get("post", {})
            if o.get("metric") == "ctr":
                bp = f'{base.get("daily_avg", 0) * 100:.2f}% to {post.get("daily_avg", 0) * 100:.2f}%' if post else ""
            elif o.get("metric") == "position":
                bp = f'{base.get("daily_avg", 0):.1f} to {post.get("daily_avg", 0):.1f}' if post else ""
            else:
                bp = f'{base.get("daily_avg", 0):.1f}/day to {post.get("daily_avg", 0):.1f}/day' if post else ""
            raw, rctrl = o.get("raw_pct"), o.get("raw_control_pct")
            rows += (f'<tr><td><b>{esc(o["id"])}</b><div class="tiny">fixed {esc(o.get("fix_date", ""))}</div></td>'
                     f'<td>{esc(o.get("hypothesis") or o.get("issue", ""))[:200]}<div class="tiny">{what if o["verdict"] != "not_measurable" else ""}</div></td>'
                     f'<td class="num">{bp}<div class="tiny">{"market " + fmt_pct(rctrl, 0) if rctrl not in (None, float("inf")) else ""}</div></td>'
                     f'<td class="num">{pc(raw, 0) if raw is not None else ""}<div class="tiny">{o.get("weeks_measured", 0)} wk, expected {esc(o.get("direction", ""))}</div></td>'
                     f'<td><span class="verdict {cls}">{label}{" (final)" if o.get("final") else ""}</span><div class="tiny">{esc(o.get("summary", ""))[:220]}</div>{("<div class=tiny>" + spark + "</div>") if spark else ""}</td></tr>')
        body = f'<table class="oc"><thead><tr><th>Item</th><th>Expected change</th><th>Baseline to post</th><th>Effect</th><th>Verdict</th></tr></thead><tbody>{rows}</tbody></table>'
    if nm:
        body += ('<div class="notice">Not measurable (' + str(len(nm)) + '): ' +
                 esc(", ".join(f"{o['id']} ({o.get('fix_date', '')})" for o in nm)) +
                 '. Monitoring items closed when a trend reverted, or technical hygiene fixes with no isolated metric.</div>')
    insight = N.get("insights", {}).get("outcomes") or auto_outcomes_insight(d)
    return f'<h2>Fix Outcomes - did the change happen?</h2>{body}<div class="insight">{esc(insight)}</div>'


def auto_outcomes_insight(d):
    oc = [o for o in (d.get("outcomes") or []) if o["verdict"] != "not_measurable"]
    if not oc:
        return "Outcome tracking starts with the next resolved item."
    counts = {}
    for o in oc:
        counts[o["verdict"]] = counts.get(o["verdict"], 0) + 1
    parts = [f"{n} {VERDICT_STYLE.get(v, ('', v))[1].lower()}" for v, n in counts.items()]
    bad = [o["id"] for o in oc if o["verdict"] in ("regressed", "no_effect")]
    txt = f"{len(oc)} tracked fixes: " + ", ".join(parts) + "."
    if bad:
        txt += " Needs a look: " + ", ".join(bad) + "."
    return txt


def sec_live(d, N):
    live = d.get("live") or {}
    if not live:
        return ""
    pages = live.get("pages", [])
    rows = ""
    for p in pages:
        ok = p.get("status") == 200
        rows += (f'<tr{"" if ok else " class=aio-warn"}><td>{esc(p["market"])}</td><td class="url">{esc(p["path"])}</td><td class="num">{p.get("status")}</td>'
                 f'<td>{esc((p.get("title") or "MISSING")[:70])} <span class="tiny">{p.get("title_len", 0)}c</span></td>'
                 f'<td class="num">{p.get("desc_len", 0)}c</td><td class="num">{p.get("og_count", 0)}</td>'
                 f'<td class="num">{p.get("hreflang_count", 0)}{" +xd" if p.get("x_default") else ""}</td>'
                 f'<td>{"ok" if p.get("canonical_ok") else "check"}</td><td class="tiny">{esc(", ".join(p.get("schema", [])[:4]))}</td></tr>')
    issues = live.get("issues", [])
    iss = ("<ul class=issues>" + "".join(f"<li>{esc(i)}</li>" for i in issues[:25]) + "</ul>") if issues else '<div class="notice">No metadata issues detected on the checked pages.</div>'
    rds = live.get("redirects", [])
    rd_html = ""
    if rds:
        ok_n = len([r for r in rds if r.get("ok")])
        broken = [r for r in rds if not r.get("ok")]
        by_track = {}
        for r in rds:
            by_track.setdefault(r["track"], [0, 0])
            by_track[r["track"]][1] += 1
            by_track[r["track"]][0] += 1 if r.get("ok") else 0
        tracks = ", ".join(f"{t.upper()} {v[0]}/{v[1]}" for t, v in by_track.items())
        cls = "notice" if not broken else "quick-win"
        rd_html = (f'<h3 class="sub-h">Legacy redirects (course page consolidations)</h3>'
                   f'<div class="{cls}" style="{"background:#fde8e8;border-color:#ff3b30" if broken else ""}">{ok_n}/{len(rds)} legacy URLs still 301 to the right course page ({esc(tracks)}).'
                   + ("".join(f'<br>BROKEN: <span class="url">{esc(r["source"].replace(SITE, ""))}</span> -> HTTP {r["status"]} {esc((r.get("location") or "no Location").replace(SITE, ""))}' for r in broken[:10]) if broken else " Old URLs carry no impressions any more; see Fix Outcomes for the consolidation verdicts.")
                   + '</div>')
    insight = N.get("insights", {}).get("live") or ""
    return (f'<h2>Live Site Health ({len(pages)} pages checked)</h2>'
            f'<table><thead><tr><th>Mkt</th><th>Page</th><th>HTTP</th><th>Title</th><th>Desc</th><th>OG</th><th>Hreflang</th><th>Canonical</th><th>Schema</th></tr></thead><tbody>{rows}</tbody></table>'
            f'{rd_html}<h3 class="sub-h">Issues ({len(issues)})</h3>{iss}' + (f'<div class="insight">{esc(insight)}</div>' if insight else ""))


def sec_intel(d, N):
    intel = N.get("intel") or []
    if intel:
        items = "".join(f'<div class="pr"><span class="t">{esc(i.get("title", ""))}</span> <span class="tiny">{esc(i.get("source", ""))} {esc((i.get("date") or "")[:10])}</span><br>{esc(i.get("why", ""))}</div>' for i in intel[:5])
    else:
        news = (d.get("news") or [])[:5]
        if news:
            items = "".join(f'<div class="pr"><span class="t">{esc(n["title"])}</span> <span class="tiny">{esc(n.get("source", ""))} {esc((n.get("date") or "")[:10])}</span></div>' for n in news)
            items += '<div class="notice">Headlines only (no analyst interpretation this run).</div>'
        else:
            items = '<div class="notice">Nothing notable this cycle.</div>'
    return f'<h2>SEO Intelligence</h2>{items}'


def sec_prs(d, N):
    merged = [e for e in (d["prs"].get("merged") or []) if e.get("type") != "template"]
    tmpl = [e for e in (d["prs"].get("merged") or []) if e.get("type") == "template"]
    notes = N.get("pr_notes", {})
    out = ""
    for e in merged:
        conf = "high" if e.get("after") else ("med" if e.get("type") in ("new-page",) else "low")
        note = notes.get(str(e["pr"])) or e.get("verdict", "")
        out += (f'<div class="pr"><span class="t">{esc(e["repo"].split("/")[-1])} #{e["pr"]}</span> - {esc(e["title"][:90])} '
                f'<span class="conf {conf}">{e["type"]}</span><br><span class="tiny">merged {esc(e["merged"])}</span> {esc(note)}</div>')
    if tmpl:
        out += f'<div class="notice">{len(tmpl)} template/refactor PR(s) not attributable at URL level: ' + esc(", ".join(f"#{e['pr']} {e['title'][:40]}" for e in tmpl[:10])) + '</div>'
    open_ = d["prs"].get("open_seo") or []
    if open_:
        out += '<div class="pr"><span class="t">Open SEO-relevant PRs (fix written, awaiting merge)</span><br>' + esc("; ".join(f"#{p['number']} {p['title'][:70]}" for p in open_)) + '</div>'
    if not out:
        out = '<div class="notice">No merged PRs in the last 30 days, or GitHub not reachable this run.</div>'
    insight = N.get("insights", {}).get("prs") or ""
    return f'<h2>PR Correlations (last 30 days)</h2>{out}' + (f'<div class="insight">{esc(insight)}</div>' if insight else "")


def sec_backlog(d, N):
    bl = load_json(BACKLOG_PATH, {"items": []}) or {"items": []}
    items = bl.get("items", [])
    open_items = [i for i in items if i.get("status") == "open"]
    resolved = [i for i in items if i.get("status") == "resolved"]
    order = {"High": 0, "Medium": 1, "Low": 2}
    open_items.sort(key=lambda i: (order.get(i.get("impact"), 9), i.get("added_date", "")))
    counts = {k: len([i for i in open_items if i.get("impact") == k]) for k in ("High", "Medium", "Low")}
    inflight = {k: v for k, v in (N.get("in_flight") or {}).items()}
    today = date.fromisoformat(d["generated"])
    rows, cur = "", None
    for i in open_items:
        imp = i.get("impact") if i.get("impact") in order else "Low"
        if imp != cur:
            if cur is not None:
                rows += "</tbody></table>"
            rows += f'<h4 class="tier {imp.lower()}">{imp.upper()} IMPACT ({counts.get(imp, 0)})</h4><table class="bl"><thead><tr><th>ID</th><th>Issue</th><th>Recommendation</th><th>Mkt</th><th>Days</th></tr></thead><tbody>'
            cur = imp
        days = (today - date.fromisoformat(i["added_date"])).days if i.get("added_date") else "?"
        fl = f'<div class="inflight">PR #{inflight[i["id"]]} in flight</div>' if i["id"] in inflight else ""
        rows += (f'<tr><td class="bid"><span class="badge {imp.lower()}">{imp}</span><br>{esc(i["id"])}{fl}</td><td>{esc(i.get("issue", ""))}</td>'
                 f'<td>{esc(i.get("recommendation", ""))}</td><td>{esc(i.get("market", ""))}</td><td class="num">{days}</td></tr>')
    if cur is not None:
        rows += "</tbody></table>"
    recent_res = sorted([i for i in resolved if i.get("resolved_date")], key=lambda i: i["resolved_date"], reverse=True)[:5]
    res_html = "".join(f'<li><b>{esc(i["id"])}</b> ({esc(i["resolved_date"])}): {esc((i.get("verification_note") or "")[:140])}</li>' for i in recent_res)
    qw = N.get("quick_wins") or []
    qw_html = ("<div class=\"quick-win\"><b>Quick wins:</b><ol>" + "".join(f"<li>{esc(q)}</li>" for q in qw) + "</ol></div>") if qw else ""
    return (f'<h2>Backlog</h2><div class="card" style="margin-bottom:14px"><div class="lbl">Status</div><div class="val num">{len(open_items)} open</div>'
            f'<div class="note">{counts["High"]} High, {counts["Medium"]} Medium, {counts["Low"]} Low - {len(resolved)} resolved</div></div>'
            f'{rows}<h3 class="sub-h">Recently resolved</h3><ul class="issues">{res_html or "<li>none</li>"}</ul>{qw_html}')


def auto_headlines(d, n=4, severities=("high", "medium")):
    """One signal per type, most severe first - avoids three near-identical lines."""
    rank = {"high": 0, "medium": 1, "info": 2}
    seen, out = set(), []
    for s in sorted(d["signals"], key=lambda s: rank.get(s["severity"], 9)):
        if s["severity"] not in severities or s["type"] in seen:
            continue
        seen.add(s["type"])
        out.append(s["text"])
    return out[:n]


def sec_tldr(d, N):
    tl = N.get("tldr") or []
    fd = N.get("findings") or []
    if not tl and not fd:
        auto = auto_headlines(d)
        if not auto:
            return ""
        return '<div class="tldr"><h3>Auto-detected signals</h3><ul>' + "".join(f"<li>{esc(a)}</li>" for a in auto) + "</ul></div>"
    out = '<div class="tldr">'
    if tl:
        out += "<h3>TL;DR</h3><ul>" + "".join(f"<li>{esc(t)}</li>" for t in tl) + "</ul>"
    if fd:
        out += "<h3>Findings</h3><ul>" + "".join(f"<li>{esc(t)}</li>" for t in fd) + "</ul>"
    return out + "</div>"


CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background: #f5f5f7; color: #1d1d1f; line-height: 1.5; -webkit-font-smoothing: antialiased; }
.wrap { max-width: 1200px; margin: 0 auto; padding: 24px 20px 60px; }
header { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%); color: #fff; border-radius: 16px; padding: 36px 32px; margin-bottom: 24px; }
header h1 { font-size: 30px; font-weight: 700; letter-spacing: -0.02em; }
header .sub { color: #b8c4d9; margin-top: 6px; font-size: 14px; }
header .mkts { margin-top: 14px; display: flex; gap: 8px; flex-wrap: wrap; }
header .mkt { background: rgba(255,255,255,0.12); padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; }
h2 { font-size: 20px; font-weight: 700; margin: 32px 0 14px; letter-spacing: -0.01em; }
h3.sub-h { font-size: 14px; margin: 16px 0 8px; color: #6e6e73; text-transform: uppercase; letter-spacing: 0.04em; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin-bottom: 8px; }
.card { background: #fff; border-radius: 14px; padding: 18px; box-shadow: 0 1px 3px rgba(0,0,0,0.07); }
.card .lbl { font-size: 12px; color: #86868b; text-transform: uppercase; font-weight: 600; letter-spacing: 0.04em; }
.card .val { font-size: 28px; font-weight: 700; margin-top: 4px; }
.card .note { font-size: 13px; color: #6e6e73; margin-top: 2px; }
table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.07); font-size: 13px; }
th { background: #f5f5f7; color: #86868b; font-weight: 600; text-transform: uppercase; font-size: 11px; letter-spacing: 0.03em; padding: 10px 12px; text-align: left; }
td { padding: 10px 12px; border-top: 1px solid #f0f0f2; vertical-align: top; }
tr:hover td { background: #fafafc; }
tr.total td { font-weight: 600; background: #fafafc; }
tr.muted td { color: #9a9aa0; }
.delta.up { color: #34c759; font-weight: 600; } .delta.down { color: #ff3b30; font-weight: 600; } .delta.flat { color: #86868b; }
.num { font-variant-numeric: tabular-nums; } .tiny { font-size: 11px; color: #86868b; }
.arrow-up { color: #34c759; } .arrow-down { color: #ff3b30; } .arrow-flat { color: #86868b; }
.aio-warn td { background: #fff8e1; } .aio-warn td:first-child { border-left: 3px solid #ffc107; }
.insight { background: #f0f4ff; border-left: 3px solid #0f3460; padding: 12px 14px; border-radius: 8px; margin-top: 10px; font-size: 13px; }
.notice { background: #f5f5f7; border-left: 3px solid #c7c7cc; padding: 12px 14px; border-radius: 8px; color: #6e6e73; font-size: 13px; margin-top: 8px; }
.quick-win { background: #e8f5e9; border-left: 3px solid #34c759; padding: 12px 14px; border-radius: 8px; margin-top: 12px; font-size: 13px; }
.quick-win ol { margin: 6px 0 0 18px; }
.tldr { background: #fff; border-radius: 14px; padding: 18px 22px; box-shadow: 0 1px 3px rgba(0,0,0,0.07); margin-bottom: 8px; }
.tldr h3 { font-size: 13px; text-transform: uppercase; letter-spacing: 0.04em; color: #0f3460; margin: 6px 0 6px; }
.tldr ul { margin: 0 0 8px 18px; font-size: 14px; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 6px; font-size: 11px; font-weight: 700; color: #fff; }
.badge.high { background: #cc0000; } .badge.medium { background: #e65100; } .badge.low { background: #6e6e73; }
h4.tier { margin: 18px 0 8px; font-size: 14px; text-transform: uppercase; letter-spacing: 0.04em; }
h4.tier.high { color: #cc0000; } h4.tier.medium { color: #e65100; } h4.tier.low { color: #6e6e73; }
table.bl .bid { font-size: 11px; color: #6e6e73; width: 150px; }
.inflight { margin-top: 4px; color: #0f3460; font-weight: 600; }
.movers { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 14px; }
.mover { background: #fff; border-radius: 12px; padding: 14px; box-shadow: 0 1px 3px rgba(0,0,0,0.07); }
.mover h3 { font-size: 14px; margin: 6px 0 8px; } .mover ul { list-style: none; font-size: 13px; }
.mover li { padding: 4px 0; border-bottom: 1px solid #f5f5f7; } .mover li:last-child { border-bottom: none; }
.gain { color: #34c759; font-weight: 600; } .loss { color: #ff3b30; font-weight: 600; }
.pr { background: #fff; border-radius: 12px; padding: 14px; margin-bottom: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.07); font-size: 13px; }
.pr .t { font-weight: 600; }
.conf { font-size: 11px; padding: 2px 7px; border-radius: 6px; color: #fff; font-weight: 700; margin-left: 6px; }
.conf.high { background: #34c759; } .conf.med { background: #e65100; } .conf.low { background: #6e6e73; }
.url { font-family: 'SF Mono', Menlo, Consolas, monospace; font-size: 12px; word-break: break-all; }
ul.issues { margin: 6px 0 0 18px; font-size: 13px; background: #fff; padding: 10px 10px 10px 28px; border-radius: 12px; }
.verdict { display: inline-block; padding: 3px 9px; border-radius: 6px; font-size: 12px; font-weight: 700; }
.v-ok { background: #e8f5e9; color: #1a7f37; } .v-warn { background: #fff3e0; color: #e65100; } .v-wait { background: #e8f0fe; color: #1a56db; }
.v-bad { background: #fde8e8; color: #cf222e; } .v-mute { background: #f0f0f0; color: #6e6e73; }
footer { margin-top: 40px; padding-top: 20px; border-top: 1px solid #e5e5ea; color: #86868b; font-size: 12px; }
@media print { body { background: #fff; } .card, table, .mover, .pr, .tldr { box-shadow: none; } header { -webkit-print-color-adjust: exact; print-color-adjust: exact; } }
@media (max-width: 640px) { header h1 { font-size: 24px; } .cards { grid-template-columns: 1fr 1fr; } table { font-size: 12px; } th, td { padding: 8px; } }
"""


def build_html(d, N):
    W = d["windows"]
    parts = [sec_header(d), sec_tldr(d, N), sec_snapshot(d, N), sec_trend(d, N), sec_engagement(d, N),
             sec_movers(d, N), sec_pages(d, N), sec_outcomes(d, N), sec_live(d, N), sec_intel(d, N),
             sec_prs(d, N), sec_backlog(d, N)]
    footer = (f'<footer>Generated {esc(d["generated"])}. Data: Google Search Console (query/country/date, page/country) and Google Analytics 4 '
              f'(property 256164398). Windows: recent {esc(W["recent"]["start"])} to {esc(W["recent"]["end"])}, previous {esc(W["previous"]["start"])} to '
              f'{esc(W["previous"]["end"])}, trend {esc(W["trend"]["start"])} to {esc(W["trend"]["end"])}. Fix outcomes: baseline = 14 days before the fix, '
              f'post = complete weeks from fix + 3 days, control = whole market. Internal use only - do not share GSC/GA4 data outside #ironclaw-seo.</footer>')
    out = (f'<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">'
           f'<title>Ironhack SEO Report - {esc(d["generated"])}</title><style>{CSS}</style></head><body><div class="wrap">'
           + "\n".join(p for p in parts if p) + footer + '</div></body></html>')
    out = out.replace("—", " - ").replace("–", "-")
    # anchor ids on section headings (deep links like report.html#fix-outcomes)
    import re as _re
    def _slug(m):
        text = _re.sub(r"<[^>]+>", "", m.group(1))
        sid = _re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]
        return f'<h2 id="{sid}">{m.group(1)}</h2>'
    out = _re.sub(r"<h2>(.*?)</h2>", _slug, out)
    return out


# ── Slack draft ───────────────────────────────────────────────────────
def slack_draft(d, N, url):
    W, t, g4 = d["windows"], d["totals"], d["ga4_totals"]
    L = [f"Optimizer · {W['recent']['label']} vs {W['previous']['label']}", ""]
    tl = N.get("tldr") or auto_headlines(d, 3, ("high",)) or [d["signals"][-1]["text"] if d["signals"] else "Quiet week."]
    L.append("TL;DR")
    L += [f"- {x}" for x in tl[:3]]
    L.append("")
    L.append("WHAT MOVED")
    for c in d["markets"]:
        g, a = d["gsc"][c], d["ga4"][c]
        extra = []
        bp = g["deltas"]["brand_pct"]
        if bp not in (None, float("inf")) and abs(bp) >= 20 and g["previous"]["brand_clicks"] > 10:
            extra.append(f"brand {fmt_pct(bp, 0)}")
        nb = g["deltas"]["nonbrand_pct"]
        if nb not in (None, float("inf")) and abs(nb) >= 20 and g["previous"]["nonbrand_clicks"] > 10:
            extra.append(f"non-brand {fmt_pct(nb, 0)}")
        od = a["deltas"]["organic_sessions_pct"]
        extra.append(f"GA4 organic {fmt_pct(od, 0)} ({a['previous']['organic_sessions']} to {a['recent']['organic_sessions']})")
        L.append(f"- {d['codes'][c]} {fmt_pct(g['deltas']['clicks_pct'])} ({g['previous']['clicks']} to {g['recent']['clicks']}): " + ", ".join(extra))
    L.append(f"- Total {fmt_pct(t['deltas']['clicks_pct'])} ({fmt_int(t['previous']['clicks'])} to {fmt_int(t['recent']['clicks'])}); "
             f"GA4 organic {fmt_pct(g4['deltas']['organic_sessions_pct'])} ({fmt_int(g4['previous']['organic_sessions'])} to {fmt_int(g4['recent']['organic_sessions'])})")
    L.append("")
    tq = N.get("traffic_quality") or auto_engagement_insight(d)
    L += ["TRAFFIC QUALITY", tq, ""]
    fd = N.get("findings") or auto_headlines(d, 4)
    if fd:
        L.append("FINDINGS")
        L += [f"- {x}" for x in fd[:4]]
        L.append("")
    oc = d.get("outcomes") or []
    if oc:
        L.append("FIX OUTCOMES")
        for o in oc[:5]:
            if o["verdict"] == "not_measurable":
                continue
            L.append(f"- {o['id']}: {VERDICT_STYLE.get(o['verdict'], ('', o['verdict']))[1]}. {o.get('summary', '')[:300]}")
        L.append("")
    merged = [e for e in (d["prs"].get("merged") or []) if e.get("type") != "template"]
    open_ = d["prs"].get("open_seo") or []
    if merged or open_:
        L.append("PR SIGNALS")
        if merged:
            L.append("- Merged: " + "; ".join(f"#{e['pr']} {e['title'][:45]} ({(e.get('verdict') or '')[:60]})" for e in merged[:3]))
        if open_:
            L.append("- Open: " + ", ".join(f"#{p['number']} {p['title'][:40]}" for p in open_[:5]))
        L.append("")
    if N.get("research_line"):
        L += ["RESEARCH", N["research_line"], ""]
    b = d["backlog"]
    bl = load_json(BACKLOG_PATH, {"items": []}) or {"items": []}
    open_items = [i for i in bl["items"] if i.get("status") == "open"]
    counts = {k: len([i for i in open_items if i.get("impact") == k]) for k in ("High", "Medium", "Low")}
    L.append(f"BACKLOG: {len(open_items)} open ({counts['High']} High, {counts['Medium']} Medium, {counts['Low']} Low), "
             f"{len([i for i in bl['items'] if i.get('status') == 'resolved'])} resolved.")
    if N.get("quick_wins"):
        L.append("Quick wins: " + " ".join(f"({i + 1}) {q}" for i, q in enumerate(N["quick_wins"][:3])))
    L += ["", f"Report: {url}"]
    return clean_text("\n".join(L))


# ── Slack Block Kit post ──────────────────────────────────────────────
SLACK_CHANNEL = "C0B1MLM0L3X"
OUTCOME_ICON = {"confirmed": ":white_check_mark:", "beat_market": ":white_check_mark:", "regressed": ":x:", "no_effect": ":heavy_minus_sign:",
                "market_wide": ":large_orange_diamond:", "measuring": ":hourglass_flowing_sand:", "new": ":sparkles:",
                "low_volume": ":white_circle:", "no_data": ":white_circle:", "error": ":warning:", "unsupported": ":white_circle:"}


def market_status(d, c):
    g, a = d["gsc"][c], d["ga4"][c]
    cd, od = g["deltas"]["clicks_pct"], a["deltas"]["organic_sessions_pct"]
    cd = None if cd == float("inf") else cd
    od = None if od == float("inf") else od
    diverging = any(s["market"] == c and s["type"] == "divergence" for s in d["signals"])
    if diverging:
        return ":large_yellow_circle:"
    if cd is not None and cd <= -10 and (od is None or od <= 0):
        return ":red_circle:"
    if cd is not None and cd >= 5 and (od is None or od >= -5):
        return ":large_green_circle:"
    return ":large_yellow_circle:"


def auto_headline(d):
    t, g4 = d["totals"], d["ga4_totals"]
    cd, od = t["deltas"]["clicks_pct"], g4["deltas"]["organic_sessions_pct"]
    best, worst = d["best_market"], d["worst_market"]
    bd = d["gsc"][best]["deltas"]["clicks_pct"]; wd = d["gsc"][worst]["deltas"]["clicks_pct"]
    if cd is not None and od is not None and cd != float("inf") and od != float("inf"):
        if (cd > 5 and od > 0) or (cd < -5 and od < 0):
            core = (f"Organic clicks {fmt_pct(cd, 0)} ({fmt_int(t['previous']['clicks'])} to {fmt_int(t['recent']['clicks'])}) "
                    f"and GA4 organic sessions {fmt_pct(od, 0)} agree: this is real.")
        elif abs(cd) > 5 and abs(od) > 5:
            core = (f"GSC says {fmt_pct(cd, 0)} but GA4 organic sessions say {fmt_pct(od, 0)}: treat the GSC move as noise "
                    f"and read the markets on sessions.")
        else:
            core = f"Flat week: clicks {fmt_pct(cd, 0)}, GA4 organic {fmt_pct(od, 0)}."
    else:
        core = f"Organic clicks {fmt_pct(cd, 0)}."
    tail = f" Driver: {d['codes'][best]} ({fmt_pct(bd, 0)}); drag: {d['codes'][worst]} ({fmt_pct(wd, 0)})."
    return clean_text(core + tail)


def backlog_changes(d):
    bl = load_json(BACKLOG_PATH, {"items": []}) or {"items": []}
    today = d["generated"]
    items = bl["items"]
    open_items = [i for i in items if i.get("status") == "open"]
    counts = {k: len([i for i in open_items if i.get("impact") == k]) for k in ("High", "Medium", "Low")}
    resolved_today = [i["id"] for i in items if i.get("resolved_date") == today]
    added_today = [i["id"] for i in items if i.get("added_date") == today and i.get("status") == "open"]
    return open_items, counts, len([i for i in items if i.get("status") == "resolved"]), resolved_today, added_today


def slack_blocks(d, N, url):
    """Returns (main_blocks, thread_blocks, fallback_text)."""
    W, t, g4 = d["windows"], d["totals"], d["ga4_totals"]
    headline = clean_text(N.get("headline") or auto_headline(d))
    score = "  ".join(f"{market_status(d, c)} {d['codes'][c]} {fmt_pct(d['gsc'][c]['deltas']['clicks_pct'], 0)}" for c in d["markets"])
    main = [
        {"type": "header", "text": {"type": "plain_text", "text": f"SEO weekly · {W['recent']['label']}", "emoji": True}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*{headline}*\n{score}"}},
    ]
    # fixes
    oc = [o for o in (d.get("outcomes") or []) if o["verdict"] != "not_measurable"]
    if oc:
        lines = []
        for o in oc[:6]:
            icon = OUTCOME_ICON.get(o["verdict"], ":white_circle:")
            label = VERDICT_STYLE.get(o["verdict"], ("", o["verdict"]))[1]
            base, post = o.get("baseline", {}), o.get("post")
            if o["verdict"] in ("measuring",) and not post:
                detail = f"{o.get('days_post', 0)} days of post-fix data, first full week not reached"
            elif post:
                if o.get("metric") == "ctr":
                    detail = f"CTR {base.get('daily_avg', 0) * 100:.2f}% to {post.get('daily_avg', 0) * 100:.2f}% ({fmt_pct(o.get('raw_pct'), 0)}) over {o.get('weeks_measured', 0)} wk, market {fmt_pct(o.get('raw_control_pct'), 0)}"
                elif o.get("metric") == "position":
                    detail = f"position {base.get('daily_avg', 0):.1f} to {post.get('daily_avg', 0):.1f} over {o.get('weeks_measured', 0)} wk"
                else:
                    detail = f"{o['metric']}/day {base.get('daily_avg', 0):.1f} to {post.get('daily_avg', 0):.1f} ({fmt_pct(o.get('raw_pct'), 0)}) over {o.get('weeks_measured', 0)} wk, market {fmt_pct(o.get('raw_control_pct'), 0)}"
                if o["verdict"] == "low_volume":
                    detail = "too little traffic to judge: " + detail
            else:
                detail = (o.get("summary") or "")[:120]
            lines.append(f"{icon} *{o['id']}* ({label.lower()}): {detail}")
        main += [{"type": "divider"}, {"type": "section", "text": {"type": "mrkdwn", "text": "*Did our fixes work?*\n" + "\n".join(lines)}}]
    # watch-outs
    fd = N.get("findings") or auto_headlines(d, 3)
    if fd:
        main.append({"type": "section", "text": {"type": "mrkdwn", "text": "*Watch-outs*\n" + "\n".join(f"• {clean_text(x)}" for x in fd[:4])}})
    # ship next
    def trim(s, n=58):
        s = clean_text(s or "")
        return s if len(s) <= n else s[:n].rsplit(" ", 1)[0] + "..."
    ship = list(N.get("quick_wins") or [])
    open_ = d["prs"].get("open_seo") or []
    if not ship and open_:
        ship = [f"Merge #{p['number']} {trim(p['title'])}" for p in open_[:3]]
    if ship:
        main.append({"type": "section", "text": {"type": "mrkdwn", "text": "*Ship next*\n" + "\n".join(f"• {clean_text(x)}" for x in ship[:3])}})
    if N.get("research_line"):
        main.append({"type": "section", "text": {"type": "mrkdwn", "text": "*Worth knowing*\n" + clean_text(N["research_line"])}})
    open_items, counts, n_res, res_today, add_today = backlog_changes(d)
    bl_line = f"Backlog {len(open_items)} open ({counts['High']} High · {counts['Medium']} Medium · {counts['Low']} Low)"
    if res_today:
        bl_line += f" · resolved: {', '.join(res_today)}"
    if add_today:
        bl_line += f" · new: {', '.join(add_today)}"
    bl_line += f" · GA4 organic {fmt_int(g4['recent']['organic_sessions'])} ({fmt_pct(g4['deltas']['organic_sessions_pct'], 0)})"
    main.append({"type": "context", "elements": [{"type": "mrkdwn", "text": bl_line}]})
    main.append({"type": "actions", "elements": [
        {"type": "button", "text": {"type": "plain_text", "text": "Open full report"}, "url": url, "style": "primary"},
        {"type": "button", "text": {"type": "plain_text", "text": "Fix outcomes"}, "url": url + "#fix-outcomes-did-the-change-happen"},
        {"type": "button", "text": {"type": "plain_text", "text": "Backlog"}, "url": url + "#backlog"},
    ]})

    # thread: the numbers
    mk = []
    for c in d["markets"]:
        g, a = d["gsc"][c], d["ga4"][c]
        adj = g.get("adjusted") or {}
        pos = f"pos {g['recent']['position']:.1f}" + (f" (adj. {adj['position']:.1f})" if adj.get("zero_click_queries") else "")
        mk.append(f"{market_status(d, c)} *{d['codes'][c]}* clicks {g['recent']['clicks']} ({fmt_pct(g['deltas']['clicks_pct'], 0)} from {g['previous']['clicks']}), "
                  f"brand {g['recent']['brand_clicks']} ({fmt_pct(g['deltas']['brand_pct'], 0)}), non-brand {g['recent']['nonbrand_clicks']} ({fmt_pct(g['deltas']['nonbrand_pct'], 0)}), "
                  f"CTR {g['recent']['ctr'] * 100:.2f}%, {pos} · GA4 organic {a['recent']['organic_sessions']} ({fmt_pct(a['deltas']['organic_sessions_pct'], 0)}), "
                  f"engaged {a['recent']['engagement'] * 100:.0f}%, organic share {a['recent']['organic_share'] * 100:.0f}%")
    trend = " · ".join(f"{d['codes'][c]} {' > '.join(str(w['clicks']) for w in d['trend'][c])}" for c in d["markets"])
    movers = []
    for c in d["markets"]:
        m = d["movers"][c]
        up = ", ".join(f"\"{i['query'][:30]}\" +{i['delta']}" for i in m["up"][:2]) or "none"
        dn = ", ".join(f"\"{i['query'][:30]}\" {i['delta']}" for i in m["down"][:2]) or "none"
        movers.append(f"*{d['codes'][c]}* up: {up} · down: {dn}")
    thread = [
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Markets, {W['recent']['label']} vs {W['previous']['label']}*\n" + "\n".join(mk)}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*4-week clicks (oldest to newest)*\n{trend} · Total {' > '.join(str(w['clicks']) for w in d['trend']['_total'])}"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": "*Top movers*\n" + "\n".join(movers)}},
    ]
    merged = [e for e in (d["prs"].get("merged") or []) if e.get("type") != "template"]
    if merged or open_:
        pr_txt = ""
        def verdict_short(e):
            note = N.get("pr_notes", {}).get(str(e["pr"]))
            if note:
                return trim(note, 90)
            v = e.get("verdict") or ""
            if "INSUFFICIENT" in v:
                return "too recent to measure"
            if "not attributable" in v:
                return "not attributable"
            return trim(v.split(";")[0], 70)
        if merged:
            pr_txt += "Merged: " + "; ".join(f"#{e['pr']} {trim(e['title'], 45)} ({verdict_short(e)})" for e in merged[:4])
        if open_:
            pr_txt += ("\n" if pr_txt else "") + "Open: " + ", ".join(f"#{p['number']} {trim(p['title'], 45)}" for p in open_[:5])
        thread.append({"type": "section", "text": {"type": "mrkdwn", "text": "*PR signals (30d)*\n" + clean_text(pr_txt)}})
    sig = [s["text"] for s in d["signals"] if s["severity"] in ("high", "medium")]
    if sig:
        thread.append({"type": "section", "text": {"type": "mrkdwn", "text": "*All auto-detected signals*\n" + "\n".join(f"• {x}" for x in sig[:8])}})
    for b in main + thread:  # Slack section text limit is 3000 chars
        if b.get("type") == "section":
            b["text"]["text"] = b["text"]["text"][:2990]
    return main, thread, f"SEO weekly {W['recent']['label']}: {headline}"


def read_slack_token():
    for p in ("/home/openclaw/.hermes/.env", os.path.expanduser("~/.hermes/.env")):
        try:
            with open(p) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("SLACK_BOT_TOKEN="):
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
        except OSError:
            continue
    return None


def slack_post(blocks, text, channel, thread_ts=None):
    import urllib.request
    token = read_slack_token()
    if not token:
        raise RuntimeError("SLACK_BOT_TOKEN not found in ~/.hermes/.env")
    payload = {"channel": channel, "blocks": blocks, "text": text, "unfurl_links": False}
    if thread_ts:
        payload["thread_ts"] = thread_ts
    req = urllib.request.Request("https://slack.com/api/chat.postMessage", data=json.dumps(payload).encode(),
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"})
    resp = json.loads(urllib.request.urlopen(req, timeout=30).read())
    if not resp.get("ok"):
        raise RuntimeError(f"Slack error: {resp.get('error')} {resp.get('response_metadata', '')}")
    return resp["ts"]


def upload(path, key):
    r = subprocess.run(["aws", "s3", "cp", path, f"s3://{BUCKET}/{key}", "--region", REGION, "--content-type", "text/html"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"S3 upload failed: {r.stderr.strip()[:300]}")
    return f"{PUBLIC}/{key}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--data", default=None)
    ap.add_argument("--narrative", default=None)
    ap.add_argument("--upload", action="store_true", help="upload to S3 (default: only if --preview or --upload)")
    ap.add_argument("--preview", action="store_true", help="upload to seo/preview/report.html instead of the dated path")
    ap.add_argument("--local", default=None, help="write HTML here and skip upload")
    ap.add_argument("--post", action="store_true", help="post the Block Kit message (+ details thread) to Slack")
    ap.add_argument("--to", default=SLACK_CHANNEL, help="Slack channel or user id for --post (default #ironclaw-seo)")
    ap.add_argument("--blocks-out", default=None, help="write the Block Kit JSON here (for inspection)")
    a = ap.parse_args()
    data_path = a.data or os.path.join(MEMORY_DIR, f"seo-data-{a.date}.json")
    d = load_json(data_path)
    if not d:
        sys.exit(f"cannot read {data_path}")
    N = load_json(a.narrative, {}) if a.narrative else {}
    N = N or {}
    html_out = build_html(d, N)
    out_path = a.local or f"/tmp/seo-report-{a.date}.html"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_out)
    print(f"wrote {out_path} ({len(html_out):,} bytes)", file=sys.stderr)
    url = f"{PUBLIC}/seo/{a.date}/report.html"
    if a.local and not (a.upload or a.preview):
        url = out_path
    elif a.preview:
        url = upload(out_path, "seo/preview/report.html")
    elif a.upload or not a.local:
        url = upload(out_path, f"seo/{a.date}/report.html")
    draft = slack_draft(d, N, url)
    with open(f"/tmp/seo-slack-{a.date}.txt", "w", encoding="utf-8") as f:
        f.write(draft)
    main_blocks, thread_blocks, fallback = slack_blocks(d, N, url)
    blocks_path = a.blocks_out or f"/tmp/seo-slack-{a.date}.blocks.json"
    with open(blocks_path, "w", encoding="utf-8") as f:
        json.dump({"main": main_blocks, "thread": thread_blocks, "text": fallback}, f, indent=1, ensure_ascii=False)
    print(url)
    if a.post:
        ts = slack_post(main_blocks, fallback, a.to)
        slack_post(thread_blocks, "Details", a.to, thread_ts=ts)
        print(f"SLACK_POSTED channel={a.to} ts={ts}")
    print()
    print(draft)


if __name__ == "__main__":
    main()
