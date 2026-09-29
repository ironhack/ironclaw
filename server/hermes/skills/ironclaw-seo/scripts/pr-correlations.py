#!/usr/bin/env python3
"""Fetch merged PRs for the SEO report's PR Correlations section.

Reads GITHUB_TOKEN from ~/.hermes/.env (classic PAT, authenticates as
rudyironhack). Does NOT rely on the gh CLI (not logged in) or the shell
env var (cron does not source .env).

CRITICAL gotcha baked in here: the GitHub pulls endpoint accepts
state=open|closed|all, NOT state=merged. A state=merged query silently
returns OPEN PRs with merged_at=null. We query state=closed and filter
on merged_at != null.

Usage:
    python3 pr-correlations.py [days]

Outputs (to stdout):
    1. Merged PRs in the last N days (default 30), newest first.
    2. Open PRs whose titles look SEO-relevant (for the "fix written,
       awaiting merge" view).

Notes:
- tirith blocks `python3 -c` with escaped quotes in cron; run this as a
  file: `python3 /path/to/pr-correlations.py`.
- A 401 here means the token is stale. Note the limitation and skip the
  section rather than blocking the whole report.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta

REPOS = ["ironhack/foundry", "ironhack/new-website-worker"]

# Lowercase tokens that mark a PR as SEO-relevant for the open-PR section.
SEO_HINTS = [
    "seo", "title", "meta", "og:", "open graph", "hreflang", "canonical",
    "schema", "sitemap", "robots", "redirect", "query param", "utm",
    "alt text", "structured data",
]


def read_token():
    env_path = os.path.expanduser("~/.hermes/.env")
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith("GITHUB_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def api(token, path):
    req = urllib.request.Request(
        f"https://api.github.com{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "ironclaw-ih",
        },
    )
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def is_seo(title):
    t = (title or "").lower()
    return any(h in t for h in SEO_HINTS)


def main():
    argv = list(sys.argv[1:])
    json_out = None
    if '--json' in argv:
        i = argv.index('--json'); json_out = argv[i + 1]; del argv[i:i + 2]
    days = int(argv[0]) if argv else 30
    collected = []
    cutoff = date.today() - timedelta(days=days)

    token = read_token()
    if not token:
        print("ERROR: GITHUB_TOKEN not found in ~/.hermes/.env", file=sys.stderr)
        sys.exit(1)

    for repo in REPOS:
        code, prs = api(token, f"/repos/{repo}/pulls?state=closed&sort=updated&direction=desc&per_page=100")
        if code != 200:
            print(f"ERROR: {repo} -> HTTP {code}: {prs.get('message', '')}", file=sys.stderr)
            continue

        merged = []
        for pr in prs:
            ma = pr.get("merged_at")
            if not ma:
                continue
            md = datetime.fromisoformat(ma.replace("Z", "+00:00")).date()
            if md >= cutoff:
                merged.append((ma[:10], pr))

        merged.sort(key=lambda x: x[0], reverse=True)
        print(f"=== {repo} — merged in last {days} days (since {cutoff}) ===")
        if not merged:
            print("  (none)")
        for ma, pr in merged:
            title = (pr.get("title") or "")[:75]
            print(f"  #{pr['number']} | {ma} | {title}")
        print()

        # Open, SEO-relevant PRs (fix written but not yet merged).
        code2, open_prs = api(token, f"/repos/{repo}/pulls?state=open&sort=updated&direction=desc&per_page=100")
        if code2 != 200:
            continue
        seo_open = [p for p in open_prs if is_seo(p.get("title"))]
        collected += [{"repo": repo, "number": p["number"], "title": p.get("title"), "updated_at": p.get("updated_at"),
                       "created_at": p.get("created_at"), "url": p.get("html_url")} for p in seo_open]
        if seo_open:
            print(f"  --- open SEO-relevant PRs ({len(seo_open)}) ---")
            for p in seo_open:
                print(f"  #{p['number']} | OPEN | {(p.get('title') or '')[:75]}")
            print()

    if json_out:
        with open(json_out, "w") as f:
            json.dump(collected, f, indent=2)


if __name__ == "__main__":
    main()
