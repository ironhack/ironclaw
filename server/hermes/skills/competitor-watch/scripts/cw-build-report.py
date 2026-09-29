#!/usr/bin/env python3
"""cw-build-report.py - cumulative competitor watch report (HTML) + Slack post, from state + change log.

Usage: python3 cw-build-report.py --date D [--narrative /tmp/cw-narrative.json] [--post] [--to <channel>]
                                  [--preview] [--local out.html]
Narrative JSON (all optional): {"headline": "...", "actions": ["..."], "change_notes": {"<change id>": "why it matters"},
                                "competitor_notes": {"spiced": "..."}, "watch_next": ["..."]}
Uploads to s3://ih-ironclaw/watch/D/competitor-watch-report.html and watch/latest/report.html (--preview: watch/preview/report.html).
"""
import argparse
import html
import json
import os
import subprocess
import sys
import urllib.request
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cw_common import *  # noqa

SLACK_CHANNEL = "C0B1MM39P8D"
BUCKET, REGION = "ih-ironclaw", "eu-west-1"
TYPE_LABEL = {"program_added": "New program", "program_removed": "Program removed", "program_renamed": "Renamed",
              "price_changed": "Price change", "duration_changed": "Duration change", "format_changed": "Format change",
              "cohort_moved": "Cohort date moved", "promo_started": "Promotion started", "promo_ended": "Promotion ended",
              "claim_added": "New claim", "claim_changed": "Claim changed", "claim_removed": "Claim dropped",
              "positioning_changed": "Positioning changed"}
SEV_CLS = {"high": "sev-high", "medium": "sev-med", "low": "sev-low"}


def esc(s):
    return html.escape(str(s if s is not None else ""), quote=True)


def clean(s):
    return (s or "").replace("—", " - ").replace("–", "-")


def load_all(date_str):
    states = {k: load_json(os.path.join(STATE_DIR, f"{k}.json")) for k in COMPETITORS}
    changes = read_jsonl(CHANGES_PATH)
    week = [c for c in changes if c["date"] == date_str and not c.get("baseline") and not c.get("backfilled")]
    index = load_json(os.path.join(PREPARED_DIR, date_str, "index.json"), {}) or {}
    sm_dates = sorted(d for d in os.listdir(SITEMAP_DIR) if d <= date_str) if os.path.isdir(SITEMAP_DIR) else []
    sitemaps = load_json(os.path.join(SITEMAP_DIR, sm_dates[-1], "new-urls.json"), {}) if sm_dates else {}
    return states, changes, week, index, sitemaps or {}


def fmt_change(c, with_comp=True):
    lab = TYPE_LABEL.get(c["type"], c["type"])
    what = esc(c["item"])
    if c.get("before") and c.get("after") and c["before"] != c["after"] and c["type"] not in ("program_added", "program_removed"):
        what = f'{esc(c["item"])}: <span class="before">{esc(str(c["before"]))}</span> → <b>{esc(str(c["after"]))}</b>'
    comp = f'<b>{esc(c["competitor_name"])}</b> · ' if with_comp else ""
    link = f' <a href="{esc(c["url"])}" target="_blank" rel="noopener">page</a>' if c.get("url") else ""
    return f'{comp}<span class="badge {SEV_CLS.get(c["severity"], "sev-low")}">{esc(lab)}</span> {what}{link}'


def auto_headline(week, states, index, date_str):
    n = len(week)
    comps = sorted(set(c["competitor_name"] for c in week))
    quiet = [COMPETITORS[k]["name"] for k in COMPETITORS if k not in set(c["competitor"] for c in week)]
    bad = [COMPETITORS[k]["name"] for k, v in (index.get("competitors") or {}).items() if v.get("quality") == "bad"]
    if n == 0:
        h = f"Quiet week: no verified changes across {len(COMPETITORS)} competitors."
        unconf = sum(len([p for p in (s or {}).get("programs", {}).values() if p.get("status") == "unconfirmed"]) for s in states.values())
        recent = [(COMPETITORS[k]["name"].split(" (")[0], p.get("name")) for k, s in states.items()
                  for p in (s or {}).get("programs", {}).values()
                  if p.get("first_seen") and p["first_seen"] > (date.fromisoformat(date_str) - timedelta(weeks=4)).isoformat() and p["first_seen"] != date_str]
        if recent:
            h += f" Still recent: {', '.join(f'{c} {n}' for c, n in recent[:3])}."
        if unconf:
            h += f" {unconf} program{'s' if unconf != 1 else ''} unconfirmed this week (one miss is capture noise, two is a removal)."
    else:
        high = [c for c in week if c["severity"] == "high"]
        lead = high[0] if high else week[0]
        h = f"{n} verified change{'s' if n != 1 else ''} at {', '.join(comps)}; the one to note is {lead['competitor_name']}: {TYPE_LABEL.get(lead['type'], lead['type']).lower()} {lead['item']}."
    if bad:
        h += f" Capture incomplete for {', '.join(bad)}."
    return clean(h)


def quiet_since(st, date_str):
    lc = st.get("last_change")
    if not lc:
        return "no changes recorded yet"
    weeks = (date.fromisoformat(date_str) - date.fromisoformat(lc)).days // 7
    return f"quiet {weeks} wk" if weeks else "changed this week"


# ── HTML ──────────────────────────────────────────────────────────────
CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background: #f5f5f7; color: #1d1d1f; line-height: 1.5; }
.wrap { max-width: 1200px; margin: 0 auto; padding: 24px 20px 60px; }
header { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%); color: #fff; border-radius: 16px; padding: 32px; margin-bottom: 20px; }
header h1 { font-size: 28px; font-weight: 700; } header .sub { color: #b8c4d9; margin-top: 6px; font-size: 14px; }
h2 { font-size: 20px; font-weight: 700; margin: 30px 0 12px; } h3 { font-size: 16px; margin: 18px 0 8px; }
.box { background: #fff; border-radius: 14px; padding: 16px 20px; box-shadow: 0 1px 3px rgba(0,0,0,.07); margin-bottom: 12px; }
.headline { font-size: 17px; font-weight: 600; }
.status { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
.pill { background: #f5f5f7; border-radius: 20px; padding: 4px 12px; font-size: 12px; }
.pill.changed { background: #fff3e0; color: #e65100; font-weight: 600; } .pill.bad { background: #fde8e8; color: #cf222e; }
table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,.07); font-size: 13px; }
th { background: #f5f5f7; color: #86868b; font-weight: 600; text-transform: uppercase; font-size: 11px; letter-spacing: .03em; padding: 9px 10px; text-align: left; }
td { padding: 9px 10px; border-top: 1px solid #f0f0f2; vertical-align: top; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 6px; font-size: 11px; font-weight: 700; color: #fff; }
.sev-high { background: #cc0000; } .sev-med { background: #e65100; } .sev-low { background: #6e6e73; }
.before { color: #86868b; text-decoration: line-through; }
.ev { color: #6e6e73; font-size: 12px; font-style: italic; }
.card { background: #fff; border-radius: 14px; padding: 18px 20px; box-shadow: 0 1px 3px rgba(0,0,0,.07); margin-bottom: 16px; }
.card h3 { margin-top: 0; } .meta { color: #6e6e73; font-size: 12px; }
.tiny { font-size: 11px; color: #86868b; } .muted td { color: #9a9aa0; }
.note { background: #f0f4ff; border-left: 3px solid #0f3460; padding: 10px 14px; border-radius: 8px; margin-top: 10px; font-size: 13px; }
.actions { background: #e8f5e9; border-left: 3px solid #34c759; padding: 12px 14px; border-radius: 8px; margin-top: 10px; font-size: 13px; }
.actions ol { margin-left: 18px; }
.timeline .week { margin-bottom: 10px; } .timeline .wk { font-weight: 700; color: #0f3460; }
.url { font-family: Menlo, Consolas, monospace; font-size: 12px; word-break: break-all; }
footer { margin-top: 40px; padding-top: 20px; border-top: 1px solid #e5e5ea; color: #86868b; font-size: 12px; }
@media (max-width: 640px) { header h1 { font-size: 22px; } table { font-size: 12px; } th, td { padding: 7px; } }
"""


def build_html(date_str, states, changes, week, index, sitemaps, N):
    headline = clean(N.get("headline") or auto_headline(week, states, index, date_str))
    pills = ""
    week_by = {}
    for c in week:
        week_by.setdefault(c["competitor"], []).append(c)
    for k, comp in COMPETITORS.items():
        st = states.get(k) or {}
        q = (index.get("competitors", {}).get(k) or {}).get("quality", "")
        n = len(week_by.get(k, []))
        cls = "changed" if n else ("bad" if q == "bad" else "")
        pills += f'<span class="pill {cls}">{esc(comp["name"])}: {n} change{"s" if n != 1 else ""}' + (f", {esc(quiet_since(st, date_str))}" if not n else "") + (f", capture {esc(q)}" if q and q != "ok" else "") + "</span>"
    actions = N.get("actions") or []
    parts = [f'<header><h1>Competitor Watch</h1><div class="sub">Week of {esc(date_str)} · 7 competitors · ES, PT, FR, NL, DE · cumulative state since {esc(min((s or {}).get("first_extraction") or date_str for s in states.values()))}</div></header>',
             f'<div class="box"><div class="headline">{esc(headline)}</div><div class="status">{pills}</div>'
             + (('<div class="actions"><b>Worth acting on</b><ol>' + "".join(f"<li>{esc(a)}</li>" for a in actions) + "</ol></div>") if actions else "")
             + (('<div class="note"><b>Watch next week:</b> ' + esc("; ".join(N["watch_next"])) + "</div>") if N.get("watch_next") else "")
             + "</div>"]
    # changes this week
    parts.append("<h2>Verified changes this week</h2>")
    if week:
        rows = ""
        for c in sorted(week, key=lambda c: ({"high": 0, "medium": 1, "low": 2}[c["severity"]], c["competitor_name"])):
            note = (N.get("change_notes") or {}).get(c["id"])
            rows += f'<tr><td>{fmt_change(c)}' + (f'<div class="note">{esc(note)}</div>' if note else "") + f'</td><td class="ev">“{esc(c.get("evidence", ""))[:220]}”<div class="tiny">{esc(c.get("page", ""))}</div></td></tr>'
        parts.append(f'<table><thead><tr><th>Change</th><th>Evidence (verbatim from the page)</th></tr></thead><tbody>{rows}</tbody></table>')
    else:
        parts.append('<div class="box">No verified changes. Every program, claim and promotion tracked last week is still on the sites, with the same price, duration and format.</div>')
    # site activity
    sc = sitemaps.get("competitors") or {}
    if sc and sitemaps.get("previous"):
        rows = ""
        for k, v in sc.items():
            if v.get("error"):
                rows += f'<tr class="muted"><td>{esc(COMPETITORS[k]["name"])}</td><td colspan="3">{esc(v["error"])}</td></tr>'
                continue
            g = v.get("new_by_type") or {}
            ex = ", ".join(f'<a href="{esc(u)}" target="_blank" rel="noopener" class="url">{esc(u.split("//", 1)[-1].split("/", 1)[-1][:60])}</a>' for u in (g.get("program", []) + g.get("top", []))[:4])
            rows += f'<tr><td>{esc(COMPETITORS[k]["name"])}</td><td class="num">{v.get("url_count", 0):,}</td><td>{len(v.get("new", []))} new / {len(v.get("gone", []))} gone</td><td>{"program/top: " + str(len(g.get("program", [])) + len(g.get("top", []))) + ", content: " + str(len(g.get("content", []))) + (" · " + ex if ex else "")}</td></tr>'
        parts.append(f'<h2>Site activity (sitemaps, vs {esc(sitemaps.get("previous"))})</h2><table><thead><tr><th>Competitor</th><th>URLs</th><th>Δ</th><th>New pages</th></tr></thead><tbody>{rows}</tbody></table>'
                     '<div class="tiny" style="margin-top:6px">New program-type URLs are the earliest public signal of a launch; content URLs show marketing activity.</div>')
    # competitor cards
    parts.append("<h2>Competitors</h2>")
    for k, comp in COMPETITORS.items():
        st = states.get(k)
        if not st:
            parts.append(f'<div class="card"><h3>{esc(comp["name"])}</h3><div class="meta">no state yet</div></div>')
            continue
        progs = sorted([p for p in st["programs"].values() if p.get("status") != "removed"], key=lambda p: (p.get("status") != "active", p.get("name") or ""))
        rows = ""
        for p in progs:
            new = date.fromisoformat(p["first_seen"]) >= date.fromisoformat(date_str) - timedelta(days=28) if p.get("first_seen") else False
            cls = ' class="muted"' if p.get("status") == "unconfirmed" else ""
            name = f'<a href="{esc(p.get("url") or comp["site"])}" target="_blank" rel="noopener">{esc(p.get("name"))}</a>' + (' <span class="badge sev-high">new</span>' if new else "") + (' <span class="tiny">(unconfirmed this week)</span>' if p.get("status") == "unconfirmed" else "")
            rows += (f'<tr{cls}><td>{name}</td><td>{esc(p.get("type") or "")}</td><td>{esc(p.get("duration") or "-")}</td><td>{esc(p.get("format") or "-")}</td>'
                     f'<td>{esc(p.get("price") or "-")}</td><td>{esc(", ".join(p.get("financing") or []) or "-")}</td><td>{esc(", ".join(p.get("markets") or []) or "-")}</td>'
                     f'<td>{esc(p.get("next_start") or "-")}</td><td class="tiny">{esc(p.get("first_seen") or "")}</td></tr>')
        claims = [c for c in st["claims"].values() if c.get("status") != "removed"]
        promos = [c for c in st["promotions"].values() if c.get("status") != "removed"]
        cap = st.get("captures", {}).get(date_str, {})
        cnote = (N.get("competitor_notes") or {}).get(k)
        parts.append(f'''<div class="card"><h3>{esc(comp["name"])} <span class="meta">{esc(comp["site"])} · {esc(", ".join(comp["markets"]))} · {len(progs)} programs · {esc(quiet_since(st, date_str))} · capture {esc(cap.get("quality", "?"))} ({cap.get("pages_ok", "?")}/{cap.get("pages_total", "?")} pages)</span></h3>
<div class="meta"><b>Positioning:</b> {esc(st.get("positioning", {}).get("text") or "-")}</div>
{('<div class="note">' + esc(cnote) + '</div>') if cnote else ''}
<table style="margin-top:10px"><thead><tr><th>Program</th><th>Type</th><th>Duration</th><th>Format</th><th>Price</th><th>Financing</th><th>Mkts</th><th>Next start</th><th>First seen</th></tr></thead><tbody>{rows or '<tr><td colspan="9">no programs extracted</td></tr>'}</tbody></table>
<div class="meta" style="margin-top:8px"><b>Claims:</b> {esc("; ".join(c.get("text", "") for c in claims) or "-")}</div>
<div class="meta"><b>Promotions:</b> {esc("; ".join(c.get("text", "") for c in promos) or "-")}</div></div>''')
    # timeline
    real = [c for c in changes if not c.get("baseline")]
    since = (date.fromisoformat(date_str) - timedelta(weeks=12)).isoformat()
    recent = [c for c in real if c["date"] >= since]
    weeks = {}
    for c in recent:
        weeks.setdefault(c["date"], []).append(c)
    tl = ""
    for d in sorted(weeks, reverse=True):
        tl += f'<div class="week"><span class="wk">{esc(d)}</span><ul>' + "".join(f"<li>{fmt_change(c)}" + (" <span class='tiny'>(from capture history)</span>" if c.get("backfilled") else "") + "</li>" for c in weeks[d]) + "</ul></div>"
    parts.append(f'<h2>Timeline (last 12 weeks)</h2><div class="box timeline">{tl or "No changes in the last 12 weeks."}</div>')
    # data quality
    rows = ""
    for k, v in (index.get("competitors") or {}).items():
        bad = [f"{l} ({p['quality']})" for l, p in (v.get("pages") or {}).items() if p.get("quality") in ("empty", "degraded")]
        rows += f'<tr><td>{esc(v.get("name"))}</td><td>{v.get("pages_ok")}/{len(v.get("pages") or {})}</td><td>{esc(v.get("quality"))}</td><td class="tiny">{esc(", ".join(bad) or "-")}</td></tr>'
    parts.append(f'<h2>Capture quality</h2><table><thead><tr><th>Competitor</th><th>Pages ok</th><th>Quality</th><th>Empty / degraded pages</th></tr></thead><tbody>{rows}</tbody></table>')
    footer = f'<footer>Generated {esc(date_str)}. State: programs, claims and promotions extracted weekly from competitor pages with verbatim evidence, reconciled against the stored state; a program is marked removed only after two consecutive weeks missing on a usable capture. Change log since {esc(min(c["date"] for c in real) if real else date_str)}. Internal use only.</footer>'
    out = f'<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Competitor Watch - {esc(date_str)}</title><style>{CSS}</style></head><body><div class="wrap">' + "\n".join(parts) + footer + "</div></body></html>"
    import re as _re
    def _slug(m):
        text = _re.sub(r"<[^>]+>", "", m.group(1))
        return f'<h2 id="{_re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]}">{m.group(1)}</h2>'
    out = _re.sub(r"<h2>(.*?)</h2>", _slug, out)
    return out.replace("—", " - ")


# ── Slack ─────────────────────────────────────────────────────────────
def slack_blocks(date_str, states, changes, week, index, sitemaps, N, url):
    headline = clean(N.get("headline") or auto_headline(week, states, index, date_str))
    week_by = {}
    for c in week:
        week_by.setdefault(c["competitor"], []).append(c)
    pills, quiet = [], []
    for k in COMPETITORS:
        short = COMPETITORS[k]["name"].split(" (")[0]
        q = (index.get("competitors", {}).get(k) or {}).get("quality")
        st = states.get(k) or {}
        unconfirmed = len([p for p in st.get("programs", {}).values() if p.get("status") == "unconfirmed"])
        if week_by.get(k):
            pills.append(f":large_orange_circle: {short} {len(week_by[k])} change{'s' if len(week_by[k]) != 1 else ''}")
        elif q == "bad":
            pills.append(f":red_circle: {short} capture failed")
        elif unconfirmed:
            pills.append(f":large_yellow_circle: {short} {unconfirmed} program{'s' if unconfirmed != 1 else ''} unconfirmed")
        else:
            qs = quiet_since(st, date_str)
            pills.append(f":white_circle: {short} " + ("quiet" if qs == "no changes recorded yet" else qs))
    status_line = "  ".join(pills)
    main = [{"type": "header", "text": {"type": "plain_text", "text": f"Competitor watch · week of {week_label(date_str)}", "emoji": True}},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*{headline}*\n{status_line}"}}]
    if week:
        lines = []
        for c in sorted(week, key=lambda c: ({"high": 0, "medium": 1, "low": 2}[c["severity"]], c["competitor_name"]))[:8]:
            icon = CHANGE_TYPES.get(c["type"], ("", ":small_blue_diamond:"))[1]
            what = clean(c["item"])
            if c.get("before") and c.get("after") and c["before"] != c["after"] and c["type"] not in ("program_added", "program_removed"):
                what = f"{clean(c['item'])}: {clean(str(c['before']))} → {clean(str(c['after']))}"
            note = (N.get("change_notes") or {}).get(c["id"])
            link = f" <{c['url']}|page>" if c.get("url") else ""
            lines.append(f"{icon} *{c['competitor_name']}* · {TYPE_LABEL.get(c['type'], c['type'])}: {what}{link}" + (f"\n    _{clean(note)}_" if note else ""))
        main += [{"type": "divider"}, {"type": "section", "text": {"type": "mrkdwn", "text": "*What changed (verified against the pages)*\n" + "\n".join(lines)}}]
    if N.get("actions"):
        main.append({"type": "section", "text": {"type": "mrkdwn", "text": "*Worth acting on*\n" + "\n".join(f"• {clean(a)}" for a in N["actions"][:4])}})
    sc = sitemaps.get("competitors") or {}
    if sc and sitemaps.get("previous"):
        bits = []
        for k, v in sc.items():
            g = v.get("new_by_type") or {}
            np_ = len(g.get("program", [])) + len(g.get("top", []))
            if np_ or len(g.get("content", [])) >= 3:
                bits.append(f"{COMPETITORS[k]['name'].split(' (')[0]} +{np_} pages/{len(g.get('content', []))} posts")
        if bits:
            main.append({"type": "section", "text": {"type": "mrkdwn", "text": "*Site activity (new URLs)*\n" + " · ".join(bits)}})
    if N.get("watch_next"):
        main.append({"type": "section", "text": {"type": "mrkdwn", "text": "*Watch next week*\n" + "\n".join(f"• {clean(x)}" for x in N["watch_next"][:3])}})
    n_prog = sum(len([p for p in (s or {}).get("programs", {}).values() if p.get("status") != "removed"]) for s in states.values())
    pages_ok = sum((v.get("pages_ok") or 0) for v in (index.get("competitors") or {}).values())
    pages_all = sum(len(v.get("pages") or {}) for v in (index.get("competitors") or {}).values())
    main.append({"type": "context", "elements": [{"type": "mrkdwn", "text": f"{n_prog} programs tracked across 7 competitors · {pages_ok}/{pages_all} pages captured · verified changes only, evidence in the report"}]})
    main.append({"type": "actions", "elements": [
        {"type": "button", "text": {"type": "plain_text", "text": "Open report"}, "url": url, "style": "primary"},
        {"type": "button", "text": {"type": "plain_text", "text": "Timeline"}, "url": url + "#timeline-last-12-weeks"},
    ]})
    # thread
    comp_lines = []
    for k, comp in COMPETITORS.items():
        st = states.get(k) or {}
        progs = [p for p in st.get("programs", {}).values() if p.get("status") != "removed"]
        priced = len([p for p in progs if p.get("price")])
        claims = [clean(c.get("text") or "") for c in st.get("claims", {}).values() if c.get("status") != "removed"]
        claims = [c if len(c) <= 70 else c[:67] + "..." for c in claims if c][:2]
        recent = [p for p in progs if p.get("first_seen") and p["first_seen"] >= (date.fromisoformat(date_str) - timedelta(weeks=8)).isoformat()]
        cn = (N.get("competitor_notes") or {}).get(k)
        comp_lines.append(f"*{comp['name'].split(' (')[0]}* {len(progs)} programs" + (f", {priced} priced" if priced else ", no public prices")
                          + (f", {len(recent)} added in last 8 wk" if recent else "") + f" · {quiet_since(st, date_str)}"
                          + (f" · {' · '.join(claims)}" if claims else "") + (f"\n    _{clean(cn)}_" if cn else ""))
    real = [c for c in changes if not c.get("baseline") and c["date"] > (date.fromisoformat(date_str) - timedelta(weeks=4)).isoformat() and c["date"] != date_str]
    tl = [f"{c['date']} {c['competitor_name']}: {TYPE_LABEL.get(c['type'], c['type'])} {clean(c['item'])}" for c in sorted(real, key=lambda c: c["date"], reverse=True)[:12]]
    thread = [{"type": "section", "text": {"type": "mrkdwn", "text": "*Competitor status*\n" + "\n".join(comp_lines)}}]
    if tl:
        thread.append({"type": "section", "text": {"type": "mrkdwn", "text": "*Previous 4 weeks*\n" + "\n".join(f"• {x}" for x in tl)}})
    cap = [f"{v.get('name')}: {v.get('pages_ok')}/{len(v.get('pages') or {})} ok" + (" · " + ", ".join(l for l, p in (v.get("pages") or {}).items() if p.get("quality") in ("empty", "degraded")) if any(p.get("quality") in ("empty", "degraded") for p in (v.get("pages") or {}).values()) else "") for v in (index.get("competitors") or {}).values()]
    if cap:
        thread.append({"type": "section", "text": {"type": "mrkdwn", "text": "*Capture*\n" + "\n".join(f"• {x}" for x in cap)}})
    for b in main + thread:
        if b.get("type") == "section":
            b["text"]["text"] = b["text"]["text"][:2990]
    return main, thread, f"Competitor watch {week_label(date_str)}: {headline}"


def read_token():
    for p in ("/home/openclaw/.hermes/.env",):
        try:
            for line in open(p):
                line = line.strip()
                if line.startswith("SLACK_BOT_TOKEN="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
        except OSError:
            pass
    return None


def post(blocks, text, channel, thread_ts=None):
    token = read_token()
    if not token:
        raise RuntimeError("SLACK_BOT_TOKEN not found in ~/.hermes/.env")
    payload = {"channel": channel, "blocks": blocks, "text": text, "unfurl_links": False}
    if thread_ts:
        payload["thread_ts"] = thread_ts
    req = urllib.request.Request("https://slack.com/api/chat.postMessage", data=json.dumps(payload).encode(),
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"})
    resp = json.loads(urllib.request.urlopen(req, timeout=30).read())
    if not resp.get("ok"):
        raise RuntimeError(f"Slack error: {resp.get('error')}")
    return resp["ts"]


def upload(path, key):
    env = dict(os.environ)
    for line in open("/home/openclaw/.hermes/.env"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env.setdefault(k.strip(), v.strip().strip("'\""))
    r = subprocess.run(["aws", "s3", "cp", path, f"s3://{BUCKET}/{key}", "--region", REGION, "--content-type", "text/html"],
                       capture_output=True, text=True, env=env)
    if r.returncode != 0:
        raise RuntimeError(f"S3 upload failed: {r.stderr.strip()[:300]}")
    return f"{PUBLIC}/{key}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=today())
    ap.add_argument("--narrative", default=None)
    ap.add_argument("--post", action="store_true")
    ap.add_argument("--to", default=SLACK_CHANNEL)
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--local", default=None)
    a = ap.parse_args()
    N = load_json(a.narrative, {}) if a.narrative else {}
    N = N or {}
    states, changes, week, index, sitemaps = load_all(a.date)
    html_out = build_html(a.date, states, changes, week, index, sitemaps, N)
    out_path = a.local or f"/tmp/competitor-watch-{a.date}.html"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_out)
    if a.local:
        url = out_path
    elif a.preview:
        url = upload(out_path, f"{S3_PREFIX}/preview/report.html")
    else:
        url = upload(out_path, f"{S3_PREFIX}/{a.date}/competitor-watch-report.html")
        upload(out_path, f"{S3_PREFIX}/latest/report.html")
    main_b, thread_b, text = slack_blocks(a.date, states, changes, week, index, sitemaps, N, url if not a.local else f"{PUBLIC}/{S3_PREFIX}/latest/report.html")
    with open(f"/tmp/competitor-watch-{a.date}.blocks.json", "w") as f:
        json.dump({"main": main_b, "thread": thread_b, "text": text}, f, indent=1, ensure_ascii=False)
    print(url)
    if a.post:
        ts = post(main_b, text, a.to)
        post(thread_b, "Details", a.to, thread_ts=ts)
        print(f"SLACK_POSTED channel={a.to} ts={ts}")
    print(text)


if __name__ == "__main__":
    main()
