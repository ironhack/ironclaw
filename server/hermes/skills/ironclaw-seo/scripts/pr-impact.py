#!/usr/bin/env python3
"""
pr-impact.py — Quantify the SEO impact of recently merged PRs.

For each merged PR on ironhack/foundry and ironhack/new-website-worker,
classify it and — where attribution is possible — measure the before/after
delta in Google Search Console page-level data anchored on the merge date.

Classification:
  redirect-static   — touches redirections.json (worker): parse added source
                      -> dest entries, measure BOTH source (drop-out) and dest
                      (consolidation gain).
  redirect-tracking — strips tracking query params (utm/gclid/fbclid) at the
                      edge: measure the ?utm_source-etc. variant pages.
  new-page          — adds a Next.js page route: no before baseline, monitor.
  template          — broad component/refactor change: NOT attributable.

Auth: GITHUB_TOKEN from ~/.hermes/.env (same as pr-correlations.py);
      GSC service account from GOOGLE_SA_KEY_PATH / GOOGLE_IMPERSONATE_EMAIL
      (same as gsc-query.py).

Usage:
    python3 pr-impact.py [--days 30] [--before 7] [--buffer 3] [--after 7]
                         [--prs 44,42,43] [--json out.json]

The --buffer days are skipped after the merge to allow for Google's crawl +
index lag. GSC itself lags ~3 days, so the "after" window is clamped to
(today - 3d): a PR merged too recently reports INSUFFICIENT DATA instead of a
misleading zero.
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta

import google.auth.transport.requests
from google.oauth2 import service_account

REPOS = ["ironhack/foundry", "ironhack/new-website-worker"]
SITE = "https://www.ironhack.com"
SITE_ENCODED = "https%3A%2F%2Fwww.ironhack.com%2F"
GSC_LAG_DAYS = 3  # Search Console data is ~3 days behind real time
TRACKING_PATTERN = "utm_source|utm_medium|utm_campaign|gclid|fbclid"

# File markers that decide classification.
REDIRECT_FILE = "redirections.json"
NEXT_PAGE_RE = re.compile(r"apps/blog/app/(?:l/)?\[?region\]?/?\[?language\]?/([^/]+)/page\.tsx")
NEXT_PAGE_RE2 = re.compile(r"apps/blog/app/l/\[region\]/\[language\]/([^/]+)/page\.tsx")

# --- GitHub auth -------------------------------------------------------------
def read_token():
    env_path = os.path.expanduser("~/.hermes/.env")
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith("GITHUB_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def gh_api(path):
    req = urllib.request.Request(
        "https://api.github.com" + path,
        headers={
            "Authorization": "Bearer " + (read_token() or ""),
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "ironclaw-ih",
        },
    )
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


# --- GSC auth + query --------------------------------------------------------
def gsc_creds():
    sa_key = os.environ.get("GOOGLE_SA_KEY_PATH", "/home/openclaw/ironclaw-data/gsc-service-account.json")
    imp = os.environ.get("GOOGLE_IMPERSONATE_EMAIL", "rodolfo.puglia@ironhack.com")
    creds = service_account.Credentials.from_service_account_file(
        sa_key, scopes=["https://www.googleapis.com/auth/webmasters.readonly"], subject=imp
    )
    creds.refresh(google.auth.transport.requests.Request())
    return creds


def gsc_page_query(start_date, end_date, page_regex, creds=None):
    """Page-level GSC query filtered to pages matching page_regex (includingRegex).
    Returns a dict {page: {clicks, impressions, ctr, position}}."""
    if creds is None:
        creds = gsc_creds()
    url = f"https://searchconsole.googleapis.com/webmasters/v3/sites/{SITE_ENCODED}/searchAnalytics/query"
    body = json.dumps({
        "startDate": start_date,
        "endDate": end_date,
        "dimensions": ["page"],
        "dimensionFilterGroups": [{
            "filters": [{"dimension": "page", "operator": "includingRegex", "expression": page_regex}],
        }],
        "rowLimit": 25000,
    }).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Authorization": "Bearer " + creds.token, "Content-Type": "application/json",
    })
    try:
        resp = json.loads(urllib.request.urlopen(req, timeout=60).read())
    except urllib.error.HTTPError as e:
        return {"_error": e.read().decode()[:300]}
    out = {}
    for r in resp.get("rows", []):
        page = r["keys"][0]
        out[page] = {
            "clicks": r.get("clicks", 0),
            "impressions": r.get("impressions", 0),
            "ctr": r.get("ctr", 0),
            "position": r.get("position", 0),
        }
    return out


def regex_for_paths(paths):
    """Build a GSC includingRegex from URL path fragments."""
    if not paths:
        return None
    return "|".join(re.escape(p) for p in paths)


# --- PR discovery ------------------------------------------------------------
def fetch_merged_prs(days):
    cutoff = date.today() - timedelta(days=days)
    out = []
    for repo in REPOS:
        code, prs = gh_api(
            f"/repos/{repo}/pulls?state=closed&sort=updated&direction=desc&per_page=100"
        )
        if code != 200:
            out.append({"_error": f"{repo} HTTP {code}: {prs.get('message','')}"})
            continue
        for pr in prs:
            ma = pr.get("merged_at")
            if not ma:
                continue
            md = datetime.fromisoformat(ma.replace("Z", "+00:00")).date()
            if md >= cutoff:
                out.append({"repo": repo, "number": pr["number"], "title": pr["title"],
                            "merged_at": ma, "merged_date": md.isoformat()})
    out.sort(key=lambda p: p.get("merged_at", ""), reverse=True)
    return out


def fetch_files(repo, number):
    code, files = gh_api(f"/repos/{repo}/pulls/{number}/files?per_page=100")
    if code != 200:
        return []
    return files


def extract_added_redirects(patch):
    """Parse added redirect entries from a redirections.json patch.
    Returns list of {source, dest}."""
    entries = []
    if not patch:
        return entries
    for line in patch.splitlines():
        if not line.startswith("+"):
            continue
        m = re.search(r'"key"\s*:\s*"([^"]+)"', line)
        if m:
            src = m.group(1)
            d = re.search(r'"value"\s*:\s*"([^"]+)"', line)
            entries.append({"source": src, "dest": d.group(1) if d else ""})
    return entries


def classify(pr, files):
    """Return (type, affected_paths, dest_paths, note)."""
    titles = (pr.get("title") or "").lower()
    all_filenames = [f.get("filename", "") for f in files]
    joined = " ".join(all_filenames).lower()

    # 1. Static redirects (redirections.json)
    redir_file = next((f for f in files if f.get("filename", "").endswith(REDIRECT_FILE)), None)
    if redir_file:
        entries = extract_added_redirects(redir_file.get("patch"))
        sources = [e["source"] for e in entries]
        dests = [e["dest"] for e in entries if e["dest"]]
        note = f"static redirects: {len(entries)} new source->dest entries"
        return ("redirect-static", sources, dests, note)

    # 2. Tracking-param stripping at the edge
    if "strip-tracking" in joined or "tracking query" in titles or (
        "utm" in joined and "redirect" in joined
    ):
        return ("redirect-tracking", ["utm_source", "gclid", "fbclid"], [], "strips tracking query params at edge")

    # 3. New Next.js page route (only ADDED files, not modified)
    page_routes = []
    for f in files:
        fn = f.get("filename", "")
        if f.get("status") != "added" or not fn.endswith("page.tsx"):
            continue
        m = re.search(r"\[language\]/(.+)/page\.tsx$", fn)
        if m:
            slug = m.group(1)
            slug = re.sub(r"\[\.\.\.[^\]]+\]", "*", slug)  # catch-all -> *
            page_routes.append("/" + slug)
    if page_routes:
        return ("new-page", page_routes, [], "new page route (no pre-merge baseline)")

    # 4. Everything else: template/refactor
    return ("template", [], [], "component/refactor change — not attributable at URL level")


# --- measurement -------------------------------------------------------------
def fmt(n):
    return f"{int(n):,}"


def pct(new, old):
    if old == 0:
        return float("inf") if new > 0 else 0.0
    return (new - old) / old * 100


def measure_window(regex, start, end, creds):
    if start > end:
        return None, "window not started yet"
    res = gsc_page_query(start.isoformat(), end.isoformat(), regex, creds)
    if "_error" in res:
        return None, f"GSC error: {res['_error']}"
    return res, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("days", nargs="?", type=int, default=30, help="look-back window in days")
    ap.add_argument("--before", type=int, default=7, help="days of 'before' window")
    ap.add_argument("--buffer", type=int, default=3, help="days skipped after merge (crawl lag)")
    ap.add_argument("--after", type=int, default=7, help="days of 'after' window")
    ap.add_argument("--prs", type=str, default="", help="comma list of PR numbers to restrict to")
    ap.add_argument("--json", type=str, default="", help="optional path to write JSON")
    args = ap.parse_args()

    token = read_token()
    if not token:
        print("ERROR: GITHUB_TOKEN not found in ~/.hermes/.env", file=sys.stderr)
        sys.exit(1)

    restrict = {int(x) for x in args.prs.split(",") if x.strip()}
    prs = fetch_merged_prs(args.days)
    creds = None
    results = []

    for pr in prs:
        if "_error" in pr:
            print("WARN:", pr["_error"], file=sys.stderr)
            continue
        if restrict and pr["number"] not in restrict:
            continue

        repo, num = pr["repo"], pr["number"]
        files = fetch_files(repo, num)
        typ, paths, dests, note = classify(pr, files)

        mdate = datetime.fromisoformat(pr["merged_date"]).date()
        today = date.today()
        before_start = mdate - timedelta(days=args.before)
        before_end = mdate - timedelta(days=1)
        after_start = mdate + timedelta(days=args.buffer)
        after_end = mdate + timedelta(days=args.buffer + args.after - 1)
        # Clamp after window to available GSC data
        max_after_end = today - timedelta(days=GSC_LAG_DAYS)

        entry = {
            "pr": num, "repo": repo, "title": pr["title"], "merged": pr["merged_date"],
            "type": typ, "note": note, "paths": paths, "dests": dests,
        }

        if typ in ("template",):
            entry["verdict"] = "not attributable (template/refactor)"
        elif typ == "new-page":
            entry["verdict"] = "new route — no pre-merge baseline; monitor for first impressions"
            entry["paths"] = paths
        else:
            # redirect-static or redirect-tracking
            regex = regex_for_paths(paths)
            if regex is None:
                entry["verdict"] = "no attributable URLs resolved"
            else:
                if creds is None:
                    creds = gsc_creds()
                before, err = measure_window(regex, before_start, before_end, creds)
                if err:
                    entry["verdict"] = f"before window: {err}"
                else:
                    # before aggregate
                    b_imp = sum(v["impressions"] for v in before.values())
                    b_clk = sum(v["clicks"] for v in before.values())
                    entry["before"] = {"impressions": b_imp, "clicks": b_clk, "pages": len(before)}

                    if after_start > max_after_end:
                        entry["verdict"] = (
                            f"INSUFFICIENT post-merge data (merged {pr['merged_date']}; "
                            f"GSC lag ~3d, re-measure after {(max_after_end + timedelta(days=1)).isoformat()}). "
                            f"Before baseline: {fmt(b_imp)} impressions / {fmt(b_clk)} clicks."
                        )
                        entry["after"] = None
                    else:
                        after, err2 = measure_window(regex, after_start, max_after_end, creds)
                        if err2:
                            entry["verdict"] = f"after window: {err2}"
                        else:
                            a_imp = sum(v["impressions"] for v in after.values())
                            a_clk = sum(v["clicks"] for v in after.values())
                            entry["after"] = {"impressions": a_imp, "clicks": a_clk, "pages": len(after)}
                            entry["verdict"] = (
                                f"impressions {fmt(b_imp)} -> {fmt(a_imp)} "
                                f"({pct(a_imp, b_imp):+.1f}%), clicks {fmt(b_clk)} -> {fmt(a_clk)}"
                            )

                    # Destination side for static redirects
                    if typ == "redirect-static" and dests:
                        d_regex = regex_for_paths(dests)
                        if d_regex and after_start <= max_after_end:
                            dbefore, _ = measure_window(d_regex, before_start, before_end, creds)
                            dafter, _ = measure_window(d_regex, after_start, max_after_end, creds)
                            d_b = sum(v["impressions"] for v in dbefore.values())
                            d_a = sum(v["impressions"] for v in dafter.values())
                            entry["dest_delta"] = f"dest impressions {fmt(d_b)} -> {fmt(d_a)}"

        results.append(entry)

    # --- render --------------------------------------------------------------
    print(f"# PR Impact — merged PRs last {args.days} days (measured {date.today().isoformat()})\n")
    for e in results:
        print(f"## #{e['pr']} ({e['repo']}) — {e['title']}")
        print(f"  Type: {e['type']}  |  Merged: {e['merged']}")
        if e["paths"]:
            print(f"  Affected paths: {', '.join(e['paths'][:8])}")
        if e.get("before"):
            print(f"  Before ({args.before}d pre-merge): {e['before']['impressions']:,} imp / {e['before']['clicks']:,} clicks across {e['before']['pages']} page(s)")
        if e.get("after"):
            print(f"  After: {e['after']['impressions']:,} imp / {e['after']['clicks']:,} clicks")
        if e.get("dest_delta"):
            print(f"  Destination: {e['dest_delta']}")
        print(f"  Verdict: {e['verdict']}")
        print()

    if args.json:
        with open(args.json, "w") as f:
            json.dump(results, f, indent=2)


if __name__ == "__main__":
    main()
