#!/usr/bin/env python3
"""Fill missing summaries using DeepSeek API.

Reads listings with NULL/empty summary, calls DeepSeek to generate
2-3 sentence blurbs, updates DB. Commits per listing.
"""

import json
import os
import sqlite3
import sys
import time
import urllib.request

DB_PATH = "/home/openclaw/ironclaw-data/workspace-ironclaw-jobs/jobs.db"

API_KEY = ""
try:
    with open(os.path.expanduser("~/.hermes/.env")) as f:
        for line in f:
            if line.startswith("DEEPSEEK_API_KEY="):
                API_KEY = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
except Exception:
    pass

LANG_LABELS = {
    "english_only": "English only, no German required",
    "german_b1": "requires basic German (B1)",
    "german_required": "requires fluent German",
    "unknown": "no language requirement stated",
}
EXP_LABELS = {
    "junior": "junior/entry-level",
    "internship": "internship",
    "entry_level": "working student (Werkstudent)",
    "senior": "senior-level",
    "other": "experience level not specified",
}


def fill_one(title, company, desc, lang, exp):
    prompt = (
        f"Write a 2-3 sentence summary (60-120 words) of this job listing "
        f"for Ironhack bootcamp graduates. Include: what the role involves, "
        f"key skills required, and language/experience level.\n\n"
        f"Title: {title}\nCompany: {company}\n"
        f"Description: {desc[:500]}\n"
        f"Language: {LANG_LABELS.get(lang, lang)}\n"
        f"Experience: {EXP_LABELS.get(exp, exp)}\n\n"
        f"Summary:"
    )
    body = json.dumps({
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 150,
        "temperature": 0.3,
    }).encode()
    req = urllib.request.Request(
        "https://api.deepseek.com/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        resp = json.loads(r.read())
    return resp["choices"][0]["message"]["content"].strip()


db = sqlite3.connect(DB_PATH)
rows = db.execute(
    "SELECT id, title, company, description, language_req, experience_level "
    "FROM jobs WHERE active=1 AND (summary IS NULL OR summary='')"
).fetchall()

if not rows:
    print("No summaries needed.")
    db.close()
    sys.exit(0)

filled = 0
errors = 0
for i, (job_id, title, company, desc, lang, exp) in enumerate(rows):
    try:
        summary = fill_one(title, company, desc or "", lang, exp)
        if summary:
            db.execute("UPDATE jobs SET summary=? WHERE id=?", (summary, job_id))
            db.commit()
            filled += 1
    except Exception as e:
        print(f"  [{i+1}/{len(rows)}] Error: {e}", file=sys.stderr)
        errors += 1
    time.sleep(0.3)  # DeepSeek is fast, light delay

print(f"\nSummaries filled: {filled}, Errors: {errors}, Total checked: {len(rows)}")
db.close()
