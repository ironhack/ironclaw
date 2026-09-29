#!/usr/bin/env python3
"""Scout Report Generation — script-only cron job (no_agent=True).

Generates 13 HTML reports (1 general + 12 branded per bootcamp),
uploads to S3, copies to shared folder.

Posts directly to Slack via Bot API — stdout is intentionally empty
so Hermes delivers nothing (no wrapper noise).

No LLM, no timeout — pure script + aws CLI. ~30s runtime.
"""

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import urllib.request
from datetime import date

SLACK_CHANNEL = "C0B1KDU4Q8P"
SLACK_TOKEN_FILE = "/home/openclaw/.hermes/.env"


def _load_slack_token() -> str:
    try:
        with open(SLACK_TOKEN_FILE) as f:
            for line in f:
                line = line.strip()
                if line.startswith("SLACK_BOT_TOKEN="):
                    return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return os.getenv("SLACK_BOT_TOKEN", "")


def slack_post(text: str) -> None:
    token = _load_slack_token()
    if not token:
        print(f"[scout-report] WARN: no SLACK_BOT_TOKEN found, falling back to stdout", file=sys.stderr)
        print(text)
        return
    body = json.dumps({"channel": SLACK_CHANNEL, "text": text}).encode()
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            resp = json.loads(r.read())
        if not resp.get("ok"):
            print(f"[scout-report] Slack error: {resp.get('error')}", file=sys.stderr)
    except Exception as e:
        print(f"[scout-report] Slack post failed: {e}", file=sys.stderr)

DB_PATH = "/home/openclaw/ironclaw-data/workspace-ironclaw-jobs/jobs.db"
SKILL_DIR = "/home/openclaw/.hermes/skills/ironhack/job-market-scout"
S3_BUCKET = "ih-ironclaw"
S3_REGION = "eu-west-1"
LOGO_PATH = "/home/openclaw/ironclaw-data/workspace-ironclaw-jobs/logo.b64"

# --- Load helpers and templates ---
exec(open(f"{SKILL_DIR}/templates/report_helpers.py").read())

with open(LOGO_PATH) as f:
    LOGO_B64 = f.read().strip()

# The templates already use {{ }} for CSS braces (Python str.format escaping).
# .format() will resolve {{ -> { and }} -> } correctly — no pre-escaping needed.

def generate_branded_report(slug, display_name, description, rows, date_str, logo):
    with open(f"{SKILL_DIR}/templates/report-branded.html") as tf:
        raw = tf.read()
    cards = []
    for row in rows:
        lang_class, lang_label = LANG_MAP.get(row[4], ('tag-unk', 'Language n/a'))
        exp_class, exp_label = EXP_MAP.get(row[5], ('tag-unk', '&ndash;'))
        summary = row[6] if row[6] else SUMMARY_PENDING
        cards.append(JOB_CARD_TEMPLATE.format(
            title=row[0], company=row[1], location=row[2], url=row[3],
            lang_class=lang_class, lang_label=lang_label,
            exp_class=exp_class, exp_label=exp_label,
            summary_text=summary,
        ))
    return raw.format(
        logo_b64=logo, date=date_str,
        bootcamp_name=display_name, bootcamp_description=description,
        active_count=len(rows), job_cards='\n'.join(cards),
    )

def generate_general_report(all_rows, date_str):
    with open(f"{SKILL_DIR}/templates/report-general.html") as tf:
        raw = tf.read()
    sections = []
    for slug, display_name, desc in BOOTCAMPS:
        rows = [r for r in all_rows if r[0] == slug]
        if not rows:
            continue
        rows_html = []
        for r in rows[:10]:
            lang_class, lang_label = LANG_MAP.get(r[4], ('tag-unk', 'Language n/a'))
            exp_class, exp_label = EXP_MAP.get(r[5], ('tag-unk', '&ndash;'))
            rows_html.append(
                f'<tr><td>{r[1]}</td><td>{r[2]}</td><td>{r[3]}</td>'
                f'<td><span class="{lang_class}">{lang_label}</span></td>'
                f'<td>{exp_label}</td><td><a href="{r[6]}">View</a></td></tr>'
            )
        sections.append(
            f'<h2>{display_name}</h2><p>{desc}</p>'
            f'<table><tr><th>Job Title</th><th>Company</th><th>Location</th>'
            f'<th>Language</th><th>Level</th><th>URL</th></tr>'
            f'{"".join(rows_html)}</table>'
        )
    return raw.format(date=date_str, sections='\n'.join(sections))

# --- Connect ---
db = sqlite3.connect(DB_PATH)
today = date.today().isoformat()
today_dir = today

# --- Query: reportable listings per bootcamp ---
# Exclude german_required and entry_level (Werkstudent).
# Order: english_only first, then german_b1, then unknown; junior first.
all_reportable = []
for slug, display_name, desc in BOOTCAMPS:
    rows = db.execute(
        """SELECT title, company, location, url, language_req, experience_level, summary
           FROM jobs WHERE bootcamp=? AND active=1
           AND language_req IN ('english_only','german_b1','unknown')
           AND experience_level != 'entry_level'
           ORDER BY CASE language_req
             WHEN 'english_only' THEN 1 WHEN 'german_b1' THEN 2 ELSE 3 END,
             CASE experience_level
             WHEN 'junior' THEN 1 WHEN 'internship' THEN 2 ELSE 3 END
           LIMIT 10""",
        (slug,),
    ).fetchall()
    all_reportable.extend(
        (slug, r[0], r[1], r[2], r[4], r[5], r[3]) for r in rows
    )

total_reportable = len(set(r[0] for r in all_reportable))  # unique slugs with listings

# --- Generate reports ---
with tempfile.TemporaryDirectory() as tmp:
    # Branded reports (one per bootcamp)
    for slug, display_name, desc in BOOTCAMPS:
        rows = db.execute(
            """SELECT title, company, location, url, language_req, experience_level, summary
               FROM jobs WHERE bootcamp=? AND active=1
               AND language_req IN ('english_only','german_b1','unknown')
               AND experience_level != 'entry_level'
               ORDER BY CASE language_req
                 WHEN 'english_only' THEN 1 WHEN 'german_b1' THEN 2 ELSE 3 END,
                 CASE experience_level
                 WHEN 'junior' THEN 1 WHEN 'internship' THEN 2 ELSE 3 END
               LIMIT 10""",
            (slug,),
        ).fetchall()

        html = generate_branded_report(slug, display_name, desc, rows, today, LOGO_B64)
        path = f"{tmp}/report-{slug}.html"
        with open(path, "w") as f:
            f.write(html)

    # General report
    general_html = generate_general_report(all_reportable, today)
    general_path = f"{tmp}/report.html"
    with open(general_path, "w") as f:
        f.write(general_html)

    # --- Upload to S3 ---
    def s3_cp(src, dst_key):
        subprocess.run(
            ["aws", "s3", "cp", src, f"s3://{S3_BUCKET}/{dst_key}",
             "--content-type", "text/html", "--region", S3_REGION],
            capture_output=True, timeout=30,
        )

    # Dated folder
    s3_cp(general_path, f"jobs/{today_dir}/report.html")
    for slug, _, _ in BOOTCAMPS:
        s3_cp(f"{tmp}/report-{slug}.html", f"jobs/{today_dir}/report-{slug}.html")

    # Shared folder (stable URLs)
    s3_cp(general_path, "jobs/shared/report.html")
    for slug, _, _ in BOOTCAMPS:
        s3_cp(f"{tmp}/report-{slug}.html", f"jobs/shared/report-{slug}.html")

# --- Record in DB ---
active_count = db.execute("SELECT COUNT(*) FROM jobs WHERE active=1").fetchone()[0]
db.execute(
    "INSERT INTO reports (generated_date, s3_url, job_count, notes) VALUES (?, ?, ?, ?)",
    (today, f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/jobs/shared/report.html",
     active_count, f"{total_reportable} bootcamps with reportable listings"),
)
db.commit()

# --- Slack summary (posted directly — no Hermes wrapper) ---
bootcamp_counts = db.execute(
    "SELECT bootcamp, COUNT(*) FROM jobs WHERE active=1 "
    "GROUP BY bootcamp ORDER BY COUNT(*) DESC"
).fetchall()

BASE_URL = f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/jobs/shared"

report_links = "\n".join(
    f"• <{BASE_URL}/report-{slug}.html|{slug}> ({count})"
    for slug, count in bootcamp_counts
)

lines = [
    f":bar_chart: *Scout Weekly Report — {today}*",
    f"{active_count} active listings across {len(bootcamp_counts)} bootcamps",
    "",
    f":page_facing_up: <{BASE_URL}/report.html|General Report>",
    "",
    f":file_folder: *All Bootcamp Reports:*",
    report_links,
]
slack_post("\n".join(lines))

# stdout intentionally empty — Hermes delivers nothing
db.close()
