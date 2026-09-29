#!/usr/bin/env python3
"""Backfill missing AI summaries for active job listings.

Reads ~/.hermes/.env for DEEPSEEK_API_KEY, queries jobs.db for listings
without summaries, generates them via DeepSeek API, and updates the DB.
Rate-limited: 1 request/second with retry on failure.
"""

import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request

DB_PATH = "/home/openclaw/ironclaw-data/workspace-ironclaw-jobs/jobs.db"


def load_env():
    """Load KEY=value pairs from ~/.hermes/.env into os.environ."""
    env_path = os.path.expanduser("~/.hermes/.env")
    if not os.path.exists(env_path):
        print("ERROR: ~/.hermes/.env not found", file=sys.stderr)
        return False
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            val = val.split("  #")[0].strip()
            os.environ[key.strip()] = val
    return True


def generate_summary(title: str, company: str, desc: str, lang: str, exp: str) -> str:
    """Generate 2-3 sentence summary via DeepSeek API."""
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        return ""

    lang_labels = {
        "english_only": "English only, no German required",
        "german_b1": "requires basic German (B1)",
        "german_required": "requires fluent German",
        "unknown": "no language requirement stated",
    }
    exp_labels = {
        "junior": "junior/entry-level",
        "internship": "internship",
        "entry_level": "working student (Werkstudent)",
        "senior": "senior-level",
        "other": "experience level not specified",
    }

    prompt = (
        f"Write a 2-3 sentence summary (60-120 words) of this job listing "
        f"for Ironhack bootcamp graduates. Include: what the role involves, "
        f"key skills required, and language/experience level.\n\n"
        f"Title: {title}\nCompany: {company}\n"
        f"Description: {desc[:500]}\n"
        f"Language: {lang_labels.get(lang, lang)}\n"
        f"Experience: {exp_labels.get(exp, exp)}\n\n"
        f"Summary:"
    )

    body = json.dumps({
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 150,
        "temperature": 0.3,
    }).encode()

    for attempt in (1, 2):
        try:
            req = urllib.request.Request(
                "https://api.deepseek.com/v1/chat/completions",
                data=body,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=15) as r:
                resp = json.loads(r.read())
            return resp["choices"][0]["message"]["content"].strip()
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt == 1:
                print(f"    429 rate limit, backing off 5s...", file=sys.stderr)
                time.sleep(5)
                continue
            print(f"    HTTP {e.code} for '{title[:40]}...'", file=sys.stderr)
            return ""
        except Exception as e:
            if attempt == 1:
                time.sleep(2)
                continue
            print(f"    Error for '{title[:40]}...': {e}", file=sys.stderr)
            return ""


def main():
    if not load_env():
        return 1

    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        print("ERROR: DEEPSEEK_API_KEY not found in .env", file=sys.stderr)
        return 1

    db = sqlite3.connect(DB_PATH)

    # Find all active listings without summaries
    rows = db.execute("""
        SELECT id, title, company, description, language_req, experience_level, bootcamp
        FROM jobs
        WHERE active=1 AND (summary IS NULL OR summary='')
        ORDER BY found_date DESC
    """).fetchall()

    total = len(rows)
    print(f"Backfilling {total} missing summaries...", file=sys.stderr)

    success = 0
    failed = 0

    for i, row in enumerate(rows):
        job_id, title, company, desc, lang, exp, bootcamp = row

        if not desc:
            failed += 1
            continue

        summary = generate_summary(title, company, desc, lang, exp)

        if summary:
            db.execute(
                "UPDATE jobs SET summary = ? WHERE id = ?",
                (summary, job_id),
            )
            db.commit()
            success += 1
        else:
            failed += 1

        if (i + 1) % 20 == 0:
            print(f"  {i+1}/{total} done ({success} ok, {failed} fail)", file=sys.stderr)

        time.sleep(1)  # rate limit

    db.close()

    print(f"\nBackfill complete: {success} summaries added, {failed} failed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
