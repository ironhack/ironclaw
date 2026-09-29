#!/usr/bin/env python3
"""seo-backlog.py - safe CLI for seo-backlog.json (no hand-editing, no JSON corruption).

  list [--status open|resolved|all] [--impact High]      table of items
  show <id>                                              full item
  add --id ID --issue "..." --recommendation "..." --impact High|Medium|Low --market all|ES|.. [--repo r] [--file f]
  resolve <id> --note "how verified" [--date YYYY-MM-DD] [--not-measurable "why"]
  reopen <id> --note "..."
  verify <id> --note "..." [--status confirmed|resolved]   update last_verified / verification_note
  not-measurable <id> --reason "..."                     for already-resolved items with no measurable metric
  set-outcome <id> --metric clicks|impressions|ctr|position|sessions --direction up|down
               --pages-regex REGEX [--markets esp,deu] [--queries-regex REGEX] [--hypothesis "..."]
               [--fix-date YYYY-MM-DD] [--min-effect 10] [--baseline-days 14] [--horizon-weeks 8]
  outcomes                                               list outcome definitions + last verdicts

An outcome definition is REQUIRED when resolving (or pass --not-measurable "reason").
seo-outcomes.py measures every definition each run and writes outcome.last back here.
"""
import argparse
import json
import os
import re
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from seo_common import BACKLOG_PATH, COUNTRIES, load_json, save_json  # noqa

VALID_METRICS = ("clicks", "impressions", "ctr", "position", "sessions")


def load():
    d = load_json(BACKLOG_PATH)
    if not d or "items" not in d:
        sys.exit(f"cannot read {BACKLOG_PATH}")
    return d


def save(d):
    d["last_updated"] = date.today().isoformat()
    d["version"] = int(d.get("version", 0)) + 1
    save_json(BACKLOG_PATH, d)


def find(d, id_):
    for i in d["items"]:
        if i["id"] == id_:
            return i
    sys.exit(f"no item with id '{id_}'")


def cmd_list(d, a):
    rows = [i for i in d["items"] if a.status == "all" or i.get("status") == a.status]
    if a.impact:
        rows = [i for i in rows if i.get("impact") == a.impact]
    order = {"High": 0, "Medium": 1, "Low": 2}
    rows.sort(key=lambda i: (i.get("status") != "open", order.get(i.get("impact"), 9), i.get("added_date", "")))
    today = date.today()
    for i in rows:
        days = (today - date.fromisoformat(i["added_date"])).days if i.get("added_date") else "?"
        oc = i.get("outcome")
        oc_s = f" outcome={oc.get('last', {}).get('verdict', 'pending')}" if oc else (" outcome=n/a" if i.get("status") == "resolved" else "")
        print(f"{i['id']:42s} {i.get('status', ''):8s} {i.get('impact', ''):6s} {i.get('market', ''):4s} {days!s:>4}d{oc_s}")
    print(f"{len(rows)} items")


def cmd_show(d, a):
    print(json.dumps(find(d, a.id), indent=2, ensure_ascii=False))


def cmd_add(d, a):
    if any(i["id"] == a.id for i in d["items"]):
        sys.exit(f"id '{a.id}' already exists")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{3,60}", a.id):
        sys.exit("id must be a kebab-case slug")
    d["items"].append({
        "id": a.id, "repo": a.repo or "ironhack/foundry", "file": a.file or "", "issue": a.issue,
        "recommendation": a.recommendation, "impact": a.impact, "market": a.market,
        "added_date": date.today().isoformat(), "status": "open", "resolved_date": None,
        "last_verified": date.today().isoformat(), "verification_status": "confirmed", "verification_note": a.note or "",
    })
    save(d)
    print(f"added {a.id}")


def cmd_resolve(d, a):
    i = find(d, a.id)
    if not i.get("outcome") and not a.not_measurable:
        sys.exit("refusing to resolve without an outcome definition: run set-outcome first, "
                 "or pass --not-measurable \"reason\" (e.g. social previews only, no GSC effect expected)")
    i["status"] = "resolved"
    i["resolved_date"] = a.date or date.today().isoformat()
    i["last_verified"] = date.today().isoformat()
    i["verification_status"] = "resolved"
    i["verification_note"] = a.note
    if a.not_measurable:
        i["outcome"] = {"not_measurable": True, "reason": a.not_measurable, "fix_date": i["resolved_date"]}
    elif not i["outcome"].get("fix_date"):
        i["outcome"]["fix_date"] = i["resolved_date"]
    save(d)
    print(f"resolved {a.id} on {i['resolved_date']}")


def cmd_reopen(d, a):
    i = find(d, a.id)
    i["status"] = "open"
    i["resolved_date"] = None
    i["last_verified"] = date.today().isoformat()
    i["verification_status"] = "confirmed"
    i["verification_note"] = a.note
    save(d)
    print(f"reopened {a.id}")


def cmd_verify(d, a):
    i = find(d, a.id)
    i["last_verified"] = date.today().isoformat()
    i["verification_status"] = a.status or i.get("verification_status", "confirmed")
    i["verification_note"] = a.note
    save(d)
    print(f"verified {a.id}")


def cmd_set_outcome(d, a):
    i = find(d, a.id)
    if a.metric not in VALID_METRICS:
        sys.exit(f"metric must be one of {VALID_METRICS}")
    try:
        re.compile(a.pages_regex)
    except re.error as e:
        sys.exit(f"bad pages regex: {e}")
    markets = [m for m in (a.markets or "").split(",") if m]
    for m in markets:
        if m not in COUNTRIES:
            sys.exit(f"market must be one of {COUNTRIES}")
    oc = i.get("outcome") or {}
    oc.update({
        "hypothesis": a.hypothesis or oc.get("hypothesis", ""),
        "metric": a.metric, "direction": a.direction,
        "scope": {"pages_regex": a.pages_regex, "markets": markets or None, "queries_regex": a.queries_regex or None},
        "fix_date": a.fix_date or oc.get("fix_date") or i.get("resolved_date") or date.today().isoformat(),
        "min_effect_pct": a.min_effect, "baseline_days": a.baseline_days, "horizon_weeks": a.horizon_weeks,
        "not_measurable": False,
    })
    i["outcome"] = oc
    save(d)
    print(f"outcome set for {a.id}: {a.metric} {a.direction} on {a.pages_regex} from {oc['fix_date']}")


def cmd_not_measurable(d, a):
    i = find(d, a.id)
    i["outcome"] = {"not_measurable": True, "reason": a.reason,
                    "fix_date": i.get("resolved_date") or date.today().isoformat()}
    save(d)
    print(f"{a.id}: marked not measurable")


def cmd_outcomes(d, a):
    for i in d["items"]:
        oc = i.get("outcome")
        if not oc:
            continue
        last = oc.get("last", {})
        if oc.get("not_measurable"):
            print(f"{i['id']:42s} not measurable: {oc.get('reason', '')}")
        else:
            print(f"{i['id']:42s} {oc['metric']:11s} {oc['direction']:4s} fix {oc.get('fix_date')} "
                  f"-> {last.get('verdict', 'pending')} {last.get('summary', '')}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("list"); s.add_argument("--status", default="open"); s.add_argument("--impact")
    s = sub.add_parser("show"); s.add_argument("id")
    s = sub.add_parser("add")
    for f in ("--id", "--issue", "--recommendation", "--impact", "--market"):
        s.add_argument(f, required=True)
    s.add_argument("--repo"); s.add_argument("--file"); s.add_argument("--note")
    s = sub.add_parser("resolve"); s.add_argument("id"); s.add_argument("--note", required=True); s.add_argument("--date"); s.add_argument("--not-measurable")
    s = sub.add_parser("reopen"); s.add_argument("id"); s.add_argument("--note", required=True)
    s = sub.add_parser("verify"); s.add_argument("id"); s.add_argument("--note", required=True); s.add_argument("--status")
    s = sub.add_parser("set-outcome"); s.add_argument("id")
    s.add_argument("--metric", required=True); s.add_argument("--direction", required=True, choices=["up", "down"])
    s.add_argument("--pages-regex", required=True); s.add_argument("--markets"); s.add_argument("--queries-regex")
    s.add_argument("--hypothesis"); s.add_argument("--fix-date"); s.add_argument("--min-effect", type=float, default=10.0)
    s.add_argument("--baseline-days", type=int, default=14); s.add_argument("--horizon-weeks", type=int, default=8)
    s = sub.add_parser("not-measurable"); s.add_argument("id"); s.add_argument("--reason", required=True)
    sub.add_parser("outcomes")
    a = ap.parse_args()
    d = load()
    {"list": cmd_list, "show": cmd_show, "add": cmd_add, "resolve": cmd_resolve, "reopen": cmd_reopen,
     "verify": cmd_verify, "set-outcome": cmd_set_outcome, "not-measurable": cmd_not_measurable,
     "outcomes": cmd_outcomes}[a.cmd](d, a)


if __name__ == "__main__":
    main()
