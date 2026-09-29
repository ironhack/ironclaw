#!/usr/bin/env python3
"""
argos_sanity_slack.py - deterministic classification + Block Kit post for the daily Google Ads sanity check.

The collector (sanity_check.py) owns the numbers, this module owns the classification and the post shape,
the agent only adds a narrative (headline / findings / actions). Same shape as the weekly performance post:
headline, market scorecard, verified items, watch-outs, actions, context line, buttons, details in a thread.

State: /home/openclaw/ironclaw-data/argos/sanity-state.json remembers every issue id with first_seen /
last_seen so the post can say what is NEW today and what CLEARED since the last check instead of
re-listing 40 items every morning.

Manual use:
  python3 argos_sanity_slack.py /tmp/argos_sanity_data.json --narrative n.json --to U02MV9VPGV6 --post
"""
import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from argos_slack import clean, eur, short_name, market_of, post, CHANNEL  # noqa: E402

REPORT_URL = "https://ih-ironclaw.s3.eu-west-1.amazonaws.com/ironclaw/argos/shared/sanity.html"
STATE_PATH = "/home/openclaw/ironclaw-data/argos/sanity-state.json"
MARKETS = ["BER", "AMS", "MAD", "LIS", "PAR"]

# Budget flags (SERVING campaigns only, yesterday's spend vs daily budget):
#   over_no_return   >= 100% of budget and 0 conversions            -> critical
#   over_weak        >= 100% and ROAS < 1                           -> warning
#   capped_no_return 80-100% and 0 conversions                      -> warning
#   raise            >= 80% and ROAS >= 2                           -> opportunity (raise candidate)
#   near_cap         >= 80% otherwise                               -> info
#   ok               < 80%
FLAG_LABEL = {
    "over_no_return": "over budget, no conversions",
    "over_weak": "over budget, ROAS below 1",
    "capped_no_return": "at the cap, no conversions",
    "raise": "capped but efficient",
    "near_cap": "near the cap",
    "ok": "ok",
}


def budget_flag(b):
    p, c, r = b.get("pct_consumed", 0) or 0, b.get("conversions", 0) or 0, b.get("roas", 0) or 0
    if p >= 100 and c == 0:
        return "over_no_return"
    if p >= 100 and r < 1:
        return "over_weak"
    if p >= 80 and c == 0:
        return "capped_no_return"
    if p >= 80 and r >= 2:
        return "raise"
    if p >= 80:
        return "near_cap"
    return "ok"


def ns_pattern(name):
    n = (name or "").lower()
    if n.startswith("[tp") or n.startswith("a/b") or "experiment" in n or "maxconv" in n or "max conv" in n or n.startswith("dia"):
        return "experiment"
    if n.startswith("rmteu") or "remarketing" in n or "retarget" in n:
        return "legacy_remarketing"
    if any(k in n for k in ("cybermonday", "blackfriday", "stap", "seasonal", "xmas", "summer")):
        return "seasonal"
    return "other"


NS_LABEL = {"experiment": "finished experiments / test variants", "legacy_remarketing": "legacy remarketing (RMTEU)",
            "seasonal": "seasonal / expired", "other": "other"}


def trend_mark(t):
    return {"up": ", spend :arrow_up:", "down": ", spend :arrow_down:"}.get(t or "", "")


def market_for(name, acct_market):
    m = market_of(name)
    return m if m in MARKETS else acct_market


def summarize(data):
    """Deterministic classification of the collector output. Everything the post and the agent use."""
    today = data.get("date") or date.today().isoformat()
    budgets, ads, not_serving, errors = [], [], [], []
    acct_market = {}
    for cid, acct in data.get("accounts", {}).items():
        prefixes = [market_of(b.get("campaign_name")) for b in acct.get("budget_constrained", [])]
        prefixes = [p for p in prefixes if p in MARKETS]
        acct_market[cid] = max(set(prefixes), key=prefixes.count) if prefixes else cid
        for k in ("error", "ad_query_error", "serving_query_error"):
            if acct.get(k):
                errors.append({"account": cid, "market": acct_market[cid], "what": k, "detail": str(acct[k])[:200]})
    for cid, acct in data.get("accounts", {}).items():
        am = acct_market[cid]
        for b in acct.get("budget_constrained", []):
            e = dict(b)
            e.update({"id": f"budget:{b.get('campaign_id')}", "account": cid, "market": market_for(b.get("campaign_name"), am),
                      "short": short_name(b.get("campaign_name")), "flag": budget_flag(b)})
            budgets.append(e)
        for a in acct.get("ad_issues", []):
            e = dict(a)
            e.update({"id": f"ad:{a.get('ad_id')}", "account": cid, "market": market_for(a.get("campaign_name"), am),
                      "short": short_name(a.get("campaign_name")),
                      "critical": a.get("approval_status") == "DISAPPROVED"})
            ads.append(e)
        for n in acct.get("not_serving", []):
            e = dict(n)
            e.update({"id": f"ns:{n.get('campaign_id')}", "account": cid, "market": am, "pattern": ns_pattern(n.get("campaign_name"))})
            not_serving.append(e)

    sev_order = {"over_no_return": 0, "over_weak": 1, "capped_no_return": 2, "raise": 3, "near_cap": 4, "ok": 5}
    budgets.sort(key=lambda e: (sev_order[e["flag"]], -(e.get("pct_consumed") or 0)))
    critical = [e for e in budgets if e["flag"] == "over_no_return"] + [a for a in ads if a["critical"]]
    warning = [e for e in budgets if e["flag"] in ("over_weak", "capped_no_return")]
    raise_c = [e for e in budgets if e["flag"] == "raise"]
    ns_groups = defaultdict(list)
    for n in not_serving:
        ns_groups[n["pattern"]].append(n)

    # market status: red = any critical, yellow = any warning or raise candidate, green = nothing flagged
    mstat = {}
    for m in MARKETS:
        items = [e for e in budgets if e["market"] == m] + [a for a in ads if a["market"] == m]
        if any(e.get("flag") == "over_no_return" or e.get("critical") for e in items):
            mstat[m] = "red"
        elif any(e.get("flag") in ("over_weak", "capped_no_return", "raise", "near_cap") for e in items):
            mstat[m] = "yellow"
        elif any(x["market"] == m for x in errors):
            mstat[m] = "red"
        else:
            mstat[m] = "green"

    return {
        "date": today,
        "accounts": len(data.get("accounts", {})),
        "serving_checked": len(budgets),
        "counts": {"critical": len(critical), "warning": len(warning), "raise": len(raise_c),
                   "ad_issues": len(ads), "not_serving": len(not_serving), "errors": len(errors)},
        "budgets": budgets, "ads": ads, "not_serving": not_serving, "errors": errors,
        "critical": critical, "warning": warning, "raise": raise_c,
        "not_serving_groups": {k: [n["campaign_name"] for n in v] for k, v in ns_groups.items()},
        "market_status": mstat,
    }


def compact_summary(S):
    """Small JSON for the agent's context (stdout of the collector)."""
    def b(e):
        return {"campaign": e["campaign_name"], "market": e["market"], "flag": e["flag"], "budget": e.get("budget"),
                "spent_yesterday": e.get("spent_yesterday"), "pct": e.get("pct_consumed"), "conversions": e.get("conversions"),
                "cpa": e.get("cpa"), "roas": e.get("roas"), "trend": e.get("trend"), "avg_spend_7d": e.get("avg_spend_7d")}
    return {
        "date": S["date"], "accounts": S["accounts"], "serving_campaigns_checked": S["serving_checked"], "counts": S["counts"],
        "flag_legend": FLAG_LABEL,
        "budgets": [b(e) for e in S["budgets"]],
        "ad_issues": [{"campaign": a["campaign_name"], "ad_group": a.get("ad_group_name"), "ad_id": a.get("ad_id"),
                       "approval": a.get("approval_status"), "review": a.get("review_status")} for a in S["ads"]],
        "not_serving": {NS_LABEL[k]: v for k, v in S["not_serving_groups"].items()},
        "errors": S["errors"],
        "market_status": S["market_status"],
    }


# ---------------------------------------------------------------- state (new / cleared)
def load_state():
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except Exception:
        return {"issues": {}}


def diff_state(state, S):
    """Return (new_ids, cleared list) without writing."""
    today = S["date"]
    issues = state.get("issues", {})
    current = {e["id"]: e for e in S["budgets"] if e["flag"] != "ok"}
    current.update({a["id"]: a for a in S["ads"]})
    current.update({n["id"]: n for n in S["not_serving"]})
    prev_dates = [v["last_seen"] for v in issues.values() if v.get("last_seen") and v["last_seen"] < today]
    prev = max(prev_dates) if prev_dates else None
    if prev is None:  # first tracked run (or the state was seeded today): nothing is "new" without history
        return set(), [], None, current
    new_ids = {i for i in current if i not in issues or issues[i].get("first_seen") == today}
    cleared = [dict(v, id=i) for i, v in issues.items() if v.get("last_seen") == prev and i not in current]
    return new_ids, cleared, prev, current


def save_state(state, S, current):
    today = S["date"]
    issues = state.setdefault("issues", {})
    for i, e in current.items():
        rec = issues.get(i) or {"first_seen": today}
        rec.update({"last_seen": today, "name": e.get("campaign_name"), "kind": i.split(":")[0],
                    "flag": e.get("flag") or e.get("approval_status") or e.get("serving_status")})
        issues[i] = rec
    # forget issues not seen for 60 days
    keep = {}
    for i, v in issues.items():
        try:
            age = (datetime.fromisoformat(today) - datetime.fromisoformat(v["last_seen"])).days
        except Exception:
            age = 0
        if age <= 60:
            keep[i] = v
    state["issues"] = keep
    state["last_run"] = today
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=1)


def days_open(rec, today):
    try:
        return (datetime.fromisoformat(today) - datetime.fromisoformat(rec["first_seen"])).days
    except Exception:
        return 0


# ---------------------------------------------------------------- text
DOT = {"red": ":red_circle:", "yellow": ":large_yellow_circle:", "green": ":large_green_circle:"}


def budget_line(e, new_ids, state, today):
    tag = ":new: " if e["id"] in new_ids else ""
    since = ""
    rec = state.get("issues", {}).get(e["id"])
    if rec and e["id"] not in new_ids:
        d = days_open(rec, today)
        if d >= 2:
            since = f" (day {d + 1})"
    conv = e.get("conversions") or 0
    ret = "0 conv" if conv == 0 else f"{conv:g} conv, ROAS {e.get('roas', 0):.2f}x"
    return (f"{tag}*{e['short']}* {eur(e.get('spent_yesterday', 0))} vs {eur(e.get('budget', 0))} budget "
            f"({e.get('pct_consumed', 0):.0f}%), {ret}{trend_mark(e.get('trend'))}{since}")


def ad_line(a, new_ids):
    tag = ":new: " if a["id"] in new_ids else ""
    return f"{tag}*{a['short']}* ad {a.get('ad_id')} in `{a.get('ad_group_name')}` is {a.get('approval_status')} ({a.get('review_status')})"


def auto_headline(S, new_ids, cleared, prev=None):
    c, w, r = S["counts"]["critical"], S["counts"]["warning"], S["counts"]["raise"]
    parts = []
    if c:
        names = [e["short"] for e in S["critical"] if "flag" in e][:3]
        dis = [a for a in S["critical"] if a.get("critical")]
        bits = []
        if names:
            bits.append(f"{len(names)} campaign{'s' if len(names) > 1 else ''} over budget with no conversions ({', '.join(names)})")
        if dis:
            bits.append(f"{len(dis)} disapproved ad{'s' if len(dis) > 1 else ''} in {', '.join(sorted({a['short'] for a in dis}))}")
        parts.append(" and ".join(bits))
    if w:
        parts.append(f"{w} at the cap with weak or no return")
    if r:
        parts.append(f"{r} efficient campaign{'s' if r > 1 else ''} capped (raise candidates)")
    if not parts:
        parts.append("all serving campaigns within budget, ads approved")
    head = "; ".join(parts)
    n_new = len([i for i in new_ids if not i.startswith("ns:")])
    if prev is None:
        tail = "; issue history starts today"
    else:
        tail = f"; {n_new} new since {prev}" if n_new else f"; nothing new since {prev}"
    if cleared:
        tail += f", {len(cleared)} cleared"
    return head[0].upper() + head[1:] + tail + "."


def auto_actions(S):
    acts = []
    for e in [x for x in S["critical"] if "flag" in x][:2]:
        acts.append(f"Cap or pause {e['short']}: {e.get('pct_consumed', 0):.0f}% of budget, 0 conversions{trend_mark(e.get('trend'))}.")
    dis = [a for a in S["critical"] if a.get("critical")]
    if dis:
        acts.append(f"Fix or pause the {len(dis)} disapproved ad{'s' if len(dis) > 1 else ''} in "
                    f"{', '.join(sorted({a['short'] for a in dis}))} (ad groups {', '.join(sorted({a.get('ad_group_name', '') for a in dis}))}).")
    if S["raise"]:
        best = S["raise"][0]
        acts.append(f"Raise the budget on {best['short']}: {best.get('pct_consumed', 0):.0f}% consumed at {best.get('roas', 0):.1f}x ROAS.")
    return acts[:4]


def build_blocks(S, N, url, state):
    today = S["date"]
    new_ids, cleared, prev, current = diff_state(state, S)
    headline = clean(N.get("headline") or auto_headline(S, new_ids, cleared, prev))
    mk = "  ".join(f"{DOT[S['market_status'][m]]} {m}" for m in MARKETS)

    main = [
        {"type": "header", "text": {"type": "plain_text", "text": f"Google Ads daily check · {today}", "emoji": True}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*{headline}*"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": mk}},
    ]
    crit = [budget_line(e, new_ids, state, today) for e in S["critical"] if "flag" in e] + \
           [ad_line(a, new_ids) for a in S["critical"] if a.get("critical")]
    warn = [budget_line(e, new_ids, state, today) for e in S["warning"]]
    if crit or warn:
        main.append({"type": "section", "text": {"type": "mrkdwn", "text": "*Needs a hand today*\n" +
                     "\n".join(f":red_circle: {l}" for l in crit) + ("\n" if crit and warn else "") +
                     "\n".join(f":large_yellow_circle: {l}" for l in warn)}})
    else:
        main.append({"type": "section", "text": {"type": "mrkdwn", "text": ":large_green_circle: *Nothing needs a hand today*: no campaign over budget without return, no disapproved ads."}})
    if S["raise"]:
        main.append({"type": "section", "text": {"type": "mrkdwn", "text": "*Capped but efficient (raise candidates)*\n" +
                     "\n".join(f"• {budget_line(e, new_ids, state, today)}" for e in S["raise"][:4])}})
    if cleared:
        main.append({"type": "section", "text": {"type": "mrkdwn", "text": "*Cleared since last check*\n" +
                     "\n".join(f":white_check_mark: {short_name(c.get('name'))} ({c.get('kind')}: {c.get('flag')}, open since {c.get('first_seen')})" for c in cleared[:6])}})
    if S["errors"]:
        main.append({"type": "section", "text": {"type": "mrkdwn", "text": "*Data gaps*\n" +
                     "\n".join(f":warning: account {x['market']}: {x['what']}" for x in S["errors"])}})
    if N.get("findings"):
        main.append({"type": "section", "text": {"type": "mrkdwn", "text": "*Watch-outs*\n" + "\n".join(f"• {clean(f)}" for f in N["findings"][:4])}})
    actions = N.get("actions") or auto_actions(S)
    if actions:
        main.append({"type": "section", "text": {"type": "mrkdwn", "text": "*Actions*\n" + "\n".join(f"{i + 1}. {clean(a)}" for i, a in enumerate(actions[:4]))}})
    ns = S["counts"]["not_serving"]
    ns_new = len([i for i in new_ids if i.startswith("ns:")])
    grp = ", ".join(f"{len(v)} {NS_LABEL[k]}" for k, v in sorted(S["not_serving_groups"].items(), key=lambda kv: -len(kv[1])))
    ctx = (f"{S['serving_checked']} serving campaigns checked across {S['accounts']} accounts · "
           f"{ns} enabled-but-ended campaigns are dead weight ({grp}){f', {ns_new} new' if ns_new else ''} · "
           f"yesterday's spend vs daily budget")
    main.append({"type": "context", "elements": [{"type": "mrkdwn", "text": ctx}]})
    main.append({"type": "actions", "elements": [
        {"type": "button", "text": {"type": "plain_text", "text": "Open report"}, "url": url},
        {"type": "button", "text": {"type": "plain_text", "text": "Weekly performance"},
         "url": "https://ih-ironclaw.s3.eu-west-1.amazonaws.com/ironclaw/argos/shared/performance.html"},
    ]})

    # thread: every serving campaign, every ad issue, the dead-weight list grouped
    def full_budget(e):
        conv = e.get("conversions") or 0
        return (f"{'🔴' if e['flag'] == 'over_no_return' else '🟡' if e['flag'] in ('over_weak', 'capped_no_return') else '🟢' if e['flag'] == 'raise' else '⚪'} "
                f"*{e['short']}* {e.get('pct_consumed', 0):.0f}% ({eur(e.get('spent_yesterday', 0))} / {eur(e.get('budget', 0))}), "
                f"conv {conv:g}, CPA {eur(e.get('cpa', 0))}, ROAS {e.get('roas', 0):.2f}x, 7d avg {eur(e.get('avg_spend_7d', 0) or 0)}/day, trend {e.get('trend', 'n/a')}, {FLAG_LABEL[e['flag']]}")
    thread = [{"type": "section", "text": {"type": "mrkdwn", "text": "*All serving campaigns (yesterday vs daily budget)*\n" + "\n".join(full_budget(e) for e in S["budgets"])}}]
    if S["ads"]:
        thread.append({"type": "section", "text": {"type": "mrkdwn", "text": "*Ad policy*\n" + "\n".join(ad_line(a, new_ids) for a in S["ads"])}})
    if S["not_serving"]:
        lines = []
        for k, names in sorted(S["not_serving_groups"].items(), key=lambda kv: -len(kv[1])):
            lines.append(f"*{NS_LABEL[k]} ({len(names)})*: " + ", ".join(f"`{n[:48]}`" for n in names))
        thread.append({"type": "section", "text": {"type": "mrkdwn", "text": "*Enabled but ended (0 impressions in 7 days)*\n" + "\n".join(lines)}})
    if N.get("notes"):
        thread.append({"type": "section", "text": {"type": "mrkdwn", "text": "*Notes*\n" + clean(N["notes"])}})
    for b in main + thread:
        if b.get("type") == "section":
            b["text"]["text"] = b["text"]["text"][:2990]
    # replace the Unicode dots used in the thread rows with shortcodes (Slack rule: shortcodes only)
    rep = {"🔴": ":red_circle:", "🟡": ":large_yellow_circle:", "🟢": ":large_green_circle:", "⚪": ":white_circle:"}
    for b in thread:
        if b.get("type") == "section":
            for k, v in rep.items():
                b["text"]["text"] = b["text"]["text"].replace(k, v)
    return main, thread, f"Google Ads daily check {today}: {headline}", current


def post_report(S, narrative, url, channel=CHANNEL, blocks_out=None, update_state=True):
    state = load_state()
    main, thread, text, current = build_blocks(S, narrative or {}, url, state)
    if blocks_out:
        with open(blocks_out, "w", encoding="utf-8") as f:
            json.dump({"main": main, "thread": thread, "text": text}, f, indent=1, ensure_ascii=False)
    ts = post(main, text, channel)
    post(thread, "Details", channel, thread_ts=ts)
    if update_state:
        save_state(state, S, current)
    return ts


def render_text(S, narrative, url):
    state = load_state()
    main, thread, text, _ = build_blocks(S, narrative or {}, url, state)
    out = []
    for b in main + [{"type": "section", "text": {"type": "mrkdwn", "text": "----- thread -----"}}] + thread:
        if b["type"] in ("section", "header"):
            out.append(b["text"]["text"])
        elif b["type"] == "context":
            out.append(b["elements"][0]["text"])
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data")
    ap.add_argument("--narrative")
    ap.add_argument("--post", action="store_true")
    ap.add_argument("--to", help="channel or user id (preview); state is not updated for previews")
    ap.add_argument("--url", default=REPORT_URL)
    ap.add_argument("--blocks-out")
    ap.add_argument("--summary", action="store_true", help="print the compact summary JSON and exit")
    a = ap.parse_args()
    with open(a.data) as f:
        data = json.load(f)
    S = summarize(data)
    if a.summary:
        print(json.dumps(compact_summary(S), indent=1, ensure_ascii=False))
        return
    N = {}
    if a.narrative:
        with open(a.narrative) as f:
            N = json.load(f)
    if a.post:
        ts = post_report(S, N, a.url, channel=a.to or CHANNEL, blocks_out=a.blocks_out, update_state=not a.to)
        print(f"SLACK_POSTED channel={a.to or CHANNEL} ts={ts}")
    else:
        print(render_text(S, N, a.url))


if __name__ == "__main__":
    main()
