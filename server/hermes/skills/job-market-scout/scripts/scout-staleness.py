#!/usr/bin/env python3
"""Scout Staleness Check — script-only cron job (no_agent=True).

Re-verifies stale listings against LinkedIn guest API.
- 7+ days unchecked → re-verify detail endpoint
- Detection (multi-signal):
  • LinkedIn's closed-job CSS class (structural, primary)
  • "No longer accepting applications" text
  • "Job has expired" / "Job posting has expired"
  • HTTP 404/410
- Valid response → update last_checked
- Exception → leave as-is
- 10 consecutive errors → abort (assume rate-limited)
- 30+ days unchecked → auto-expire as safety net

No LLM, no 3-minute timeout — pure script. Stdout = Slack message.
"""

import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from datetime import date

DB_PATH = "/home/openclaw/ironclaw-data/workspace-ironclaw-jobs/jobs.db"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*",
    "Referer": "https://www.linkedin.com/",
}


def _is_job_closed(body: str) -> bool:
    """Check if LinkedIn job detail page indicates the job is closed.

    Uses LinkedIn's own structural markup (class-based) as primary signal,
    with text-based patterns as fallback.
    """
    body_lower = body.lower()

    # --- Primary: LinkedIn's own CSS class for closed jobs ---
    # <figure class="closed-job closed-job__flavor topcard__flavor-row">
    #   <figcaption class="closed-job__flavor--closed">No longer accepting applications</figcaption>
    # </figure>
    if "closed-job__flavor--closed" in body:
        return True

    # --- Secondary: text-based patterns ---
    # "No longer accepting applications" — the most common LinkedIn text
    if "no longer accepting applications" in body_lower:
        return True
    # Shorter variant (some older/regional pages)
    if "no longer accepting" in body_lower:
        return True
    # Expired job postings
    if "this job has expired" in body_lower:
        return True
    if "job posting has expired" in body_lower:
        return True

    return False


def li_detail(job_id: str) -> tuple[str, bool]:
    """Fetch job detail. Returns (text, is_dead)."""
    url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=8) as r:
            body = r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return ("", e.code in (404, 410))
    except Exception:
        return ("", False)

    if _is_job_closed(body):
        return ("", True)

    m = re.search(
        r'<div[^>]+class="[^"]*show-more-less-html__markup[^"]*"[^>]*>(.*?)</div',
        body, re.DOTALL,
    )
    if not m:
        m = re.search(
            r'<div[^>]+class="[^"]*description__text[^"]*"[^>]*>(.*?)</section',
            body, re.DOTALL,
        )
    if m:
        text = re.sub(r"<[^>]+>", " ", m.group(1))
        return (re.sub(r"\s+", " ", text).strip()[:800], False)
    return ("", False)


# --- Connect ---
db = sqlite3.connect(DB_PATH)

# --- Phase 1: Auto-expire beyond 30 days ---
auto = db.execute(
    "SELECT COUNT(*) FROM jobs WHERE active=1 AND last_checked < date('now','-30 days')"
).fetchone()[0]
if auto > 0:
    db.execute(
        "UPDATE jobs SET active=0 WHERE active=1 AND last_checked < date('now','-30 days')"
    )
    db.commit()
print(f"Auto-expired (30+ days): {auto}")

# --- Phase 2: Re-verify stale (7-30 days) ---
stale = db.execute(
    "SELECT id, url, title, company, bootcamp FROM jobs "
    "WHERE active=1 AND last_checked < date('now','-7 days') "
    "AND last_checked >= date('now','-30 days')"
).fetchall()

verified_ok = 0
verified_dead = 0
verified_error = 0
consecutive_errors = 0

for i, (job_id, url, title, company, bootcamp) in enumerate(stale):
    m = re.search(r"/jobs/view/(\d+)", url)
    if not m:
        continue
    li_id = m.group(1)

    text, is_dead = li_detail(li_id)

    if is_dead:
        db.execute(
            "UPDATE jobs SET active=0, last_checked=date('now') WHERE id=?",
            (job_id,),
        )
        verified_dead += 1
        consecutive_errors = 0
    elif text:
        db.execute(
            "UPDATE jobs SET last_checked=date('now') WHERE id=?", (job_id,)
        )
        verified_ok += 1
        consecutive_errors = 0
    else:
        verified_error += 1
        consecutive_errors += 1

    # Commit every 5
    if (i + 1) % 5 == 0:
        db.commit()
        print(
            f"  [{i+1}/{len(stale)}] ok={verified_ok} dead={verified_dead} "
            f"err={verified_error}",
            file=sys.stderr,
        )

    # Abort on rate limit
    if consecutive_errors >= 10:
        print(
            f"  ABORT: {consecutive_errors} consecutive errors — likely rate-limited",
            file=sys.stderr,
        )
        break

    time.sleep(2)

db.commit()

# --- Phase 3: Final state ---
bootcamps = db.execute(
    "SELECT bootcamp, COUNT(*) FROM jobs WHERE active=1 "
    "GROUP BY bootcamp ORDER BY COUNT(*) DESC"
).fetchall()
total_active = sum(c for _, c in bootcamps)

today = date.today().isoformat()
print(f"\nScout staleness done — {today}")
print(f"Re-verified: {len(stale)} stale listings")
print(f"  Still active: {verified_ok}")
print(f"  Confirmed dead: {verified_dead}")
print(f"  Errors (left alone): {verified_error}")
print(f"Active listings: {total_active} across {len(bootcamps)} bootcamps")
print()
for slug, count in bootcamps:
    print(f"  {slug}: {count}")

db.close()
