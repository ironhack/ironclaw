#!/usr/bin/env python3
"""argos_slack.py - Block Kit Slack post for the Argos performance report.

Built from the full dataset (/tmp/argos_perf_data.json) plus an optional narrative JSON written by
the agent (headline, findings, actions, channel_notes). Same shape as the SEO weekly post:
headline, channel + market scorecards, funnel, movers (campaign / generic ad group / keyword),
watch-outs, actions, totals line, buttons; all detailed tables in a thread reply.

Used by generate_performance_report.py --post. Can also be run standalone:
    python3 argos_slack.py /tmp/argos_perf_data.json --url <report url> [--narrative n.json] [--post] [--to <channel>]
"""
import argparse
import json
import os
import sys
import urllib.request
from collections import defaultdict

CHANNEL = "C0BFMA3117F"
ENV_PATH = "/home/openclaw/.hermes/profiles/argos/.env"
REPORT_URL = "https://ih-ironclaw.s3.eu-west-1.amazonaws.com/ironclaw/argos/shared/performance.html"
CH_ORDER = ["brand", "generic", "pmax", "display", "other"]
CH_LABEL = {"brand": "Brand", "generic": "Generic", "pmax": "PMAX", "display": "Display", "other": "Other"}
STAGE_ORDER = ["Apps", "QApps", "TI", "SA", "BST"]
GREEN, YELLOW, RED, WHITE = ":large_green_circle:", ":large_yellow_circle:", ":red_circle:", ":white_circle:"


# ── helpers ───────────────────────────────────────────────────────────
def clean(s):
    return (s or "").replace("—", " - ").replace("–", "-")


def pct(new, old):
    if not old:
        return None if not new else float("inf")
    return (new - old) / old * 100.0


def fp(v, digits=0):
    if v is None:
        return "n/a"
    if v == float("inf"):
        return "new"
    return f"{'+' if v > 0 else ''}{v:.{digits}f}%"


def eur(v):
    return f"€{v:,.0f}"


def conv(v):
    s = f"{v:.1f}"
    return s[:-2] if s.endswith(".0") else s


def short_name(name):
    parts = (name or "").split("_")
    market = parts[0] if parts else name
    lang = parts[-1] if parts and len(parts[-1]) == 2 else ""
    n = (name or "").lower()
    typ = ("Brand" if "brand" in n else "PMAX" if "pmax" in n else "Display" if ("display" in n or "youtube" in n)
           else "Generic" if "generic" in n else "Awareness" if "awareness" in n else "")
    sub = ""
    if "bildungsgutschein" in n:
        sub = " BGS"
    elif "_high" in n:
        sub = " High"
    return " ".join(x for x in [market, typ] if x) + sub + (f" {lang}" if lang else "")


def market_of(name):
    return (name or "").split("_")[0] or "?"


def totals(entities, key=None, value=None):
    t = {"cost": 0.0, "conversions": 0.0, "conversions_value": 0.0, "clicks": 0, "impressions": 0, "n": 0}
    st = defaultdict(float)
    dev = defaultdict(lambda: {"cost": 0.0, "conversions": 0.0})
    for e in entities.values():
        if key and e.get(key) != value:
            continue
        for k in ("cost", "conversions", "conversions_value", "clicks", "impressions"):
            t[k] += e.get(k, 0) or 0
        t["n"] += 1
        for s, v in (e.get("stages") or {}).items():
            st[s] += v
        for d, dv in (e.get("devices") or {}).items():
            dev[d]["cost"] += dv.get("cost", 0)
            dev[d]["conversions"] += dv.get("conversions", 0)
    t["cpa"] = t["cost"] / t["conversions"] if t["conversions"] else 0.0
    t["roas"] = t["conversions_value"] / t["cost"] if t["cost"] else 0.0
    t["stages"] = dict(st)
    t["devices"] = dict(dev)
    return t


def status(c, p):
    """Traffic-light for a slice: conversions first, efficiency second, on meaningful volume only.
    red    = conversions down 15%+ (on 5+ previous conversions), or ROAS down 25%+ on flat/higher spend >= EUR 500
    green  = conversions up 5%+ with CPA not worse than +10%
    yellow = everything else; white = negligible spend"""
    if c["cost"] < 50 and p["cost"] < 50:
        return WHITE
    cp = pct(c["conversions"], p["conversions"])
    rp = pct(c["roas"], p["roas"])
    cpa_p = pct(c["cpa"], p["cpa"]) if p["cpa"] else None
    if cp is not None and cp != float("inf") and cp <= -15 and p["conversions"] >= 5:
        return RED
    if (rp is not None and rp != float("inf") and rp <= -25 and c["cost"] >= 500 and c["cost"] >= p["cost"] * 0.95
            and (cp is None or cp <= 0)):
        return RED
    if cp is not None and (cp == float("inf") or cp >= 5) and (cpa_p is None or cpa_p <= 10):
        return GREEN
    return YELLOW


def week_label(start, end):
    from datetime import date
    s, e = date.fromisoformat(start), date.fromisoformat(end)
    if s.month == e.month:
        return f"{s.strftime('%b')} {s.day}-{e.day}"
    return f"{s.strftime('%b')} {s.day}-{e.strftime('%b')} {e.day}"


def movers(cur, prev, n=5, min_conv=1.0, min_cost=10.0):
    out = []
    for eid in set(cur) | set(prev):
        c, p = cur.get(eid, {}), prev.get(eid, {})
        e = c or p
        cd = (c.get("conversions", 0) or 0) - (p.get("conversions", 0) or 0)
        xd = (c.get("cost", 0) or 0) - (p.get("cost", 0) or 0)
        if abs(cd) < min_conv and abs(xd) < min_cost:
            continue
        out.append({"campaign": e.get("campaign_name"), "channel": e.get("channel", e.get("type")),
                    "ad_group": e.get("ad_group_name"), "keyword": e.get("keyword_text"), "status": e.get("status"),
                    "conv": c.get("conversions", 0) or 0, "conv_prev": p.get("conversions", 0) or 0, "conv_delta": cd,
                    "cost": c.get("cost", 0) or 0, "cost_prev": p.get("cost", 0) or 0, "cost_delta": xd,
                    "roas": c.get("roas", 0) or 0, "roas_prev": p.get("roas", 0) or 0,
                    "cpa": c.get("cost_per_conversion", 0) or 0})
    by_conv = sorted(out, key=lambda e: -abs(e["conv_delta"]))
    by_cost = sorted(out, key=lambda e: -abs(e["cost_delta"]))
    return {"conv_up": [e for e in by_conv if e["conv_delta"] > 0][:n],
            "conv_down": [e for e in by_conv if e["conv_delta"] < 0][:n],
            "cost_up": [e for e in by_cost if e["cost_delta"] > 0][:n],
            "cost_down": [e for e in by_cost if e["cost_delta"] < 0][:n]}


def mover_line(e, level):
    icon = ":small_red_triangle:" if e["conv_delta"] > 0 else ":small_red_triangle_down:"
    name = short_name(e["campaign"])
    if level == "ad_groups":
        name += f" · {e['ad_group']}"
    elif level == "keywords":
        name += f" · \"{e['keyword']}\""
    paused = " (paused)" if e.get("status") and e["status"] != "ENABLED" else ""
    rx = lambda v: ">50x" if v > 50 else f"{v:.1f}x"
    eff = f"ROAS {rx(e['roas_prev'])} to {rx(e['roas'])}" if (e["roas"] or e["roas_prev"]) else f"CPA {eur(e['cpa'])}"
    return f"{icon} *{name}*{paused} conv {conv(e['conv_prev'])} to {conv(e['conv'])} ({'+' if e['conv_delta'] > 0 else ''}{conv(e['conv_delta'])}), spend {'+' if e['cost_delta'] >= 0 else '-'}{eur(abs(e['cost_delta']))}, {eff}"


def stage_label(s):
    return s


# ── auto text ─────────────────────────────────────────────────────────
def auto_headline(T, P, chan):
    sp, cp = pct(T["cost"], P["cost"]), pct(T["conversions"], P["conversions"])
    cpa_p, roas_p = pct(T["cpa"], P["cpa"]), pct(T["roas"], P["roas"])
    if cp is None or sp is None:
        return "No comparable previous period."
    if sp >= 0 and cp < -10:
        core = f"Paying more for fewer conversions: spend {fp(sp)} but conversions {fp(cp)} ({conv(P['conversions'])} to {conv(T['conversions'])}), CPA {fp(cpa_p)} to {eur(T['cpa'])}."
    elif sp < 0 and cp < sp - 10:
        core = f"Spend {fp(sp)} but conversions fell faster ({fp(cp)}): efficiency is deteriorating, ROAS {P['roas']:.1f}x to {T['roas']:.1f}x."
    elif cp >= 5 and (cpa_p is None or cpa_p <= 5):
        core = f"Conversions {fp(cp)} ({conv(P['conversions'])} to {conv(T['conversions'])}) at flat or better CPA ({eur(T['cpa'])}): the week worked."
    else:
        core = f"Spend {fp(sp)}, conversions {fp(cp)}, CPA {eur(T['cpa'])} ({fp(cpa_p)}), ROAS {T['roas']:.2f}x ({fp(roas_p)})."
    # channel drag / driver by conversions delta weighted by spend
    items = []
    for ch, (c, p) in chan.items():
        if c["cost"] < 100:
            continue
        items.append((ch, (c["conversions"] - p["conversions"]), c["roas"]))
    if items:
        drag = min(items, key=lambda x: x[1])
        driver = max(items, key=lambda x: x[1])
        tail = ""
        if drag[1] <= -5:
            tail += f" Drag: {CH_LABEL[drag[0]]} (conv {conv(drag[1])}, ROAS {drag[2]:.1f}x)."
        if driver[1] >= 5 and driver[0] != drag[0] and driver[2] >= 1:
            tail += f" Driver: {CH_LABEL[driver[0]]} (conv +{conv(driver[1])}, ROAS {driver[2]:.1f}x)."
        core += tail
    return core


def auto_findings(T, P, camps_c, camps_p, order):
    out = []
    # funnel concentration
    moves = []
    for s in order:
        c, p = T["stages"].get(s, 0), P["stages"].get(s, 0)
        if max(c, p) >= 5 and p:
            moves.append((s, (c - p) / p * 100))
    if moves:
        worst = min(moves, key=lambda m: m[1])
        best = max(moves, key=lambda m: m[1])
        if T["conversions"] < P["conversions"] and worst[1] < -10:
            out.append(f"The drop concentrates at {worst[0]} ({fp(worst[1])}): check whether it is sales follow-up lag or lead quality before cutting spend.")
        elif T["conversions"] >= P["conversions"] and best[1] > 10:
            out.append(f"Growth concentrates at {best[0]} ({fp(best[1])}).")
    # device shift
    tc = sum(v["conversions"] for v in T["devices"].values()); tp = sum(v["conversions"] for v in P["devices"].values())
    if tc and tp:
        for d in T["devices"]:
            sc = T["devices"][d]["conversions"] / tc; sp_ = P["devices"].get(d, {"conversions": 0})["conversions"] / tp
            if abs(sc - sp_) >= 0.05 and sc > 0.1:
                out.append(f"Device mix shifted: {d.title()} share of conversions {sp_ * 100:.0f}% to {sc * 100:.0f}%.")
                break
    # CPC jump / worst ROAS
    jumps = []
    for cid, c in camps_c.items():
        p = camps_p.get(cid, {})
        if c.get("cpc") and p.get("cpc") and (c["cpc"] - p["cpc"]) / p["cpc"] > 0.3 and c.get("cost", 0) > 200:
            jumps.append((short_name(c["campaign_name"]), (c["cpc"] - p["cpc"]) / p["cpc"] * 100, c["cpc"]))
    if jumps:
        j = max(jumps, key=lambda x: x[1])
        out.append(f"CPC watch: {j[0]} CPC {fp(j[1])} to €{j[2]:.2f}; check auction competition or quality score.")
    worst = [(short_name(c["campaign_name"]), c.get("roas", 0), c.get("cost", 0)) for c in camps_c.values() if c.get("cost", 0) > 300]
    if worst:
        w = min(worst, key=lambda x: x[1])
        if w[1] < 1:
            out.append(f"{w[0]} spent {eur(w[2])} at {w[1]:.2f}x ROAS: decide whether to cut or fix targeting.")
    return out[:4]


# ── blocks ────────────────────────────────────────────────────────────
def build_blocks(data, N, url):
    meta = data["report_metadata"]
    tf = meta["timeframes"]["last_7d"]
    label = week_label(tf["current"]["start"], tf["current"]["end"])
    prev_label = week_label(tf["previous"]["start"], tf["previous"]["end"])
    d = data["data"]
    camps_c, camps_p = d["campaigns"]["last_7d"]["current"], d["campaigns"]["last_7d"]["previous"]
    T, P = totals(camps_c), totals(camps_p)
    order = [s for s in (meta.get("funnel_stages") or STAGE_ORDER)]
    chan = {}
    for ch in CH_ORDER:
        c, p = totals(camps_c, "channel", ch), totals(camps_p, "channel", ch)
        if c["n"] or p["n"]:
            chan[ch] = (c, p)
    mkts = {}
    for m in sorted(set(market_of(e["campaign_name"]) for e in list(camps_c.values()) + list(camps_p.values()))):
        cc = {k: v for k, v in camps_c.items() if market_of(v["campaign_name"]) == m}
        pp = {k: v for k, v in camps_p.items() if market_of(v["campaign_name"]) == m}
        mkts[m] = (totals(cc), totals(pp))

    headline = clean(N.get("headline") or auto_headline(T, P, chan))
    ch_line = "  ".join(f"{status(c, p)} {CH_LABEL[ch]} conv {fp(pct(c['conversions'], p['conversions']))} · ROAS {c['roas']:.1f}x"
                        for ch, (c, p) in chan.items() if ch != "other" or c["cost"] > 50)
    mk_line = "  ".join(f"{status(c, p)} {m} {fp(pct(c['conversions'], p['conversions']))}" for m, (c, p) in mkts.items())
    funnel = " › ".join(f"{s} {conv(P['stages'].get(s, 0))}→{conv(T['stages'].get(s, 0))} ({fp(pct(T['stages'].get(s, 0), P['stages'].get(s, 0)))})"
                        for s in order if max(T["stages"].get(s, 0), P["stages"].get(s, 0)) >= 1)

    main = [
        {"type": "header", "text": {"type": "plain_text", "text": f"Google Ads weekly · {label}", "emoji": True}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*{headline}*\n{ch_line}\n{mk_line}"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Funnel (primary conversions)*\n{funnel}"}},
        {"type": "divider"},
    ]
    cm = movers(camps_c, camps_p, n=5)
    lines = [mover_line(e, "campaigns") for e in cm["conv_down"][:3]] + [mover_line(e, "campaigns") for e in cm["conv_up"][:2]]
    if lines:
        main.append({"type": "section", "text": {"type": "mrkdwn", "text": "*Biggest conversion movers (campaigns)*\n" + "\n".join(lines)}})
    ag = movers(d["ad_groups"]["last_7d"]["current"], d["ad_groups"]["last_7d"]["previous"], n=8)
    kw = movers(d["keywords"]["last_7d"]["current"], d["keywords"]["last_7d"]["previous"], n=8)
    def prio(lst):
        return sorted(lst, key=lambda e: (0 if e["channel"] in ("generic", "pmax") else 1, -abs(e["conv_delta"])))
    gen_lines = ([mover_line(e, "ad_groups") for e in prio(ag["conv_down"])[:2]] + [mover_line(e, "ad_groups") for e in prio(ag["conv_up"])[:1]]
                 + [mover_line(e, "keywords") for e in prio(kw["conv_down"])[:2]] + [mover_line(e, "keywords") for e in prio(kw["conv_up"])[:1]])
    if gen_lines:
        main.append({"type": "section", "text": {"type": "mrkdwn", "text": "*Ad groups and keywords to look at (generic first)*\n" + "\n".join(gen_lines)}})
    fd = N.get("findings") or auto_findings(T, P, camps_c, camps_p, order)
    if fd:
        main.append({"type": "section", "text": {"type": "mrkdwn", "text": "*Watch-outs*\n" + "\n".join(f"• {clean(x)}" for x in fd[:4])}})
    if N.get("actions"):
        main.append({"type": "section", "text": {"type": "mrkdwn", "text": "*Actions*\n" + "\n".join(f"• {clean(x)}" for x in N["actions"][:4])}})
    main.append({"type": "context", "elements": [{"type": "mrkdwn", "text":
        f"Spend {eur(T['cost'])} ({fp(pct(T['cost'], P['cost']))}) · Conv {conv(T['conversions'])} ({fp(pct(T['conversions'], P['conversions']))}) · "
        f"CPA {eur(T['cpa'])} ({fp(pct(T['cpa'], P['cpa']))}) · ROAS {T['roas']:.2f}x ({fp(pct(T['roas'], P['roas']))}) · "
        f"{meta.get('accounts_count', 0)} accounts · {T['n']} campaigns · vs {prev_label}"}]})
    main.append({"type": "actions", "elements": [
        {"type": "button", "text": {"type": "plain_text", "text": "Open full report"}, "url": url, "style": "primary"},
        {"type": "button", "text": {"type": "plain_text", "text": "Generic view"}, "url": url + "#last_7d/generic"},
        {"type": "button", "text": {"type": "plain_text", "text": "Brand view"}, "url": url + "#last_7d/brand"},
        {"type": "button", "text": {"type": "plain_text", "text": "30 days"}, "url": url + "#last_30d/all"},
    ]})

    # thread
    def row(name, c, p):
        return (f"{status(c, p)} *{name}* spend {eur(c['cost'])} ({fp(pct(c['cost'], p['cost']))}), conv {conv(c['conversions'])} "
                f"({fp(pct(c['conversions'], p['conversions']))} from {conv(p['conversions'])}), CPA {eur(c['cpa'])} ({fp(pct(c['cpa'], p['cpa']))}), "
                f"ROAS {c['roas']:.2f}x ({fp(pct(c['roas'], p['roas']))})")
    thread = [
        {"type": "section", "text": {"type": "mrkdwn", "text": "*By channel*\n" + "\n".join(row(CH_LABEL[ch], c, p) for ch, (c, p) in chan.items())}},
        {"type": "section", "text": {"type": "mrkdwn", "text": "*By market*\n" + "\n".join(row(m, c, p) for m, (c, p) in mkts.items())}},
    ]
    tc = sum(v["conversions"] for v in T["devices"].values())
    tp = sum(v["conversions"] for v in P["devices"].values())
    if tc:
        dev_lines = []
        for dname in ("DESKTOP", "MOBILE", "TABLET"):
            if dname not in T["devices"]:
                continue
            c, p = T["devices"][dname], P["devices"].get(dname, {"cost": 0, "conversions": 0})
            share_c = c["conversions"] / tc if tc else 0; share_p = p["conversions"] / tp if tp else 0
            cpa_c = c["cost"] / c["conversions"] if c["conversions"] else 0
            dev_lines.append(f"*{dname.title()}* {share_c * 100:.0f}% of conversions ({share_p * 100:.0f}% before), CPA {eur(cpa_c)}, spend {eur(c['cost'])}")
        thread.append({"type": "section", "text": {"type": "mrkdwn", "text": "*Devices*\n" + "\n".join(dev_lines)}})
    thread.append({"type": "section", "text": {"type": "mrkdwn", "text": "*Campaign movers by conversions*\n" +
                   "\n".join(mover_line(e, "campaigns") for e in cm["conv_down"] + cm["conv_up"])}})
    thread.append({"type": "section", "text": {"type": "mrkdwn", "text": "*Campaign movers by spend*\n" +
                   "\n".join(f"{':small_red_triangle:' if e['cost_delta'] > 0 else ':small_red_triangle_down:'} *{short_name(e['campaign'])}*{' (paused)' if e.get('status') and e['status'] != 'ENABLED' else ''} "
                             f"{'+' if e['cost_delta'] > 0 else '-'}{eur(abs(e['cost_delta']))} (conv {conv(e['conv_prev'])} to {conv(e['conv'])}, ROAS {e['roas_prev']:.1f}x to {e['roas']:.1f}x)"
                             for e in cm["cost_up"][:3] + cm["cost_down"][:3])}})
    thread.append({"type": "section", "text": {"type": "mrkdwn", "text": "*Ad group movers*\n" + "\n".join(mover_line(e, "ad_groups") for e in ag["conv_down"][:5] + ag["conv_up"][:5])}})
    thread.append({"type": "section", "text": {"type": "mrkdwn", "text": "*Keyword movers*\n" + "\n".join(mover_line(e, "keywords") for e in kw["conv_down"][:5] + kw["conv_up"][:5])}})
    if N.get("channel_notes"):
        thread.append({"type": "section", "text": {"type": "mrkdwn", "text": "*Channel notes*\n" + "\n".join(f"• *{CH_LABEL.get(k, k)}*: {clean(v)}" for k, v in N["channel_notes"].items())}})
    for b in main + thread:
        if b.get("type") == "section":
            b["text"]["text"] = b["text"]["text"][:2990]
    return main, thread, f"Google Ads weekly {label}: {headline}"


def read_token():
    try:
        with open(ENV_PATH) as f:
            for line in f:
                line = line.strip()
                if line.startswith("SLACK_BOT_TOKEN="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return None


def post(blocks, text, channel, thread_ts=None):
    token = read_token()
    if not token:
        raise RuntimeError(f"SLACK_BOT_TOKEN not found in {ENV_PATH}")
    payload = {"channel": channel, "blocks": blocks, "text": text, "unfurl_links": False}
    if thread_ts:
        payload["thread_ts"] = thread_ts
    req = urllib.request.Request("https://slack.com/api/chat.postMessage", data=json.dumps(payload).encode(),
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"})
    resp = json.loads(urllib.request.urlopen(req, timeout=30).read())
    if not resp.get("ok"):
        raise RuntimeError(f"Slack error: {resp.get('error')} {resp.get('response_metadata', '')}")
    return resp["ts"]


def post_report(data, narrative, url, channel=CHANNEL, blocks_out=None):
    main, thread, text = build_blocks(data, narrative or {}, url)
    if blocks_out:
        with open(blocks_out, "w", encoding="utf-8") as f:
            json.dump({"main": main, "thread": thread, "text": text}, f, indent=1, ensure_ascii=False)
    ts = post(main, text, channel)
    post(thread, "Details", channel, thread_ts=ts)
    return ts


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("data", nargs="?", default="/tmp/argos_perf_data.json")
    ap.add_argument("--url", default=REPORT_URL)
    ap.add_argument("--narrative", default=None)
    ap.add_argument("--post", action="store_true")
    ap.add_argument("--to", default=CHANNEL)
    ap.add_argument("--blocks-out", default="/tmp/argos_slack_blocks.json")
    a = ap.parse_args()
    with open(a.data) as f:
        data = json.load(f)
    N = {}
    if a.narrative:
        with open(a.narrative) as f:
            N = json.load(f)
    main, thread, text = build_blocks(data, N, a.url)
    with open(a.blocks_out, "w", encoding="utf-8") as f:
        json.dump({"main": main, "thread": thread, "text": text}, f, indent=1, ensure_ascii=False)
    print(f"blocks written to {a.blocks_out}", file=sys.stderr)
    if a.post:
        ts = post(main, text, a.to)
        post(thread, "Details", a.to, thread_ts=ts)
        print(f"SLACK_POSTED channel={a.to} ts={ts}")
