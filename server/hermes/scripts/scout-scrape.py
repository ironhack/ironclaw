#!/usr/bin/env python3
"""Scout Weekly Scrape — script-only cron job (no_agent=True).

Scrapes LinkedIn guest API for all 12 Ironhack bootcamps.
- Searches 2-3 keyword variants per bootcamp
- Deduplicates by job ID
- Skips listings already in DB
- Fetches detail page for each new listing
- Regex-classifies language_req and experience_level
- Calls DeepSeek API for 2-3 sentence summaries
- Commits after each listing (safe to interrupt/rerun)
- 429 rate-limit → backs off 30s and retries

No LLM agent, no timeout — pure script + cheap API call. Stdout = Slack message.
"""

import hashlib
import html as htmllib
import json
import os
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

BOOTCAMPS = {
    "ai-web-development": {
        "name": "AI Web Development",
        "terms": [
            "Junior Web Developer",
            "Junior Frontend Developer",
            "Junior Full Stack",
            "Webentwickler Junior",
        ],
    },
    "data-analytics": {
        "name": "Data Analytics",
        "terms": [
            "Junior Data Analyst",
            "Junior Business Analyst",
            "Junior Datenanalyst",
        ],
    },
    "ai-consulting-integration": {
        "name": "AI Consulting & Integration",
        "terms": [
            "Junior AI Consultant",
            "Junior AI Engineer",
            "AI Consultant junior",
        ],
    },
    "ai-driven-ux-ui": {
        "name": "AI-Driven UX/UI",
        "terms": [
            "Junior UX Designer",
            "Junior UI Designer",
            "Junior Product Designer",
        ],
    },
    "data-science-ml": {
        "name": "Data Science & Machine Learning",
        "terms": [
            "Junior Data Scientist",
            "Junior Machine Learning",
            "Junior ML Engineer",
        ],
    },
    "ai-engineering": {
        "name": "AI Engineering",
        "terms": [
            "Junior AI Engineer",
            "Junior ML Engineer",
            "AI Engineer junior",
        ],
    },
    "cloud-engineering": {
        "name": "Cloud Engineering",
        "terms": [
            "Junior Cloud Engineer",
            "Junior AWS",
            "Junior DevOps",
        ],
    },
    "data-engineering": {
        "name": "Data Engineering",
        "terms": [
            "Junior Data Engineer",
            "Junior ETL",
            "Data Engineer junior",
        ],
    },
    "ai-driven-marketing": {
        "name": "AI-Driven Marketing",
        "terms": [
            "Junior Marketing",
            "Junior Digital Marketing",
            "Junior SEO",
        ],
    },
    "cybersecurity": {
        "name": "Cybersecurity",
        "terms": [
            "Junior Cybersecurity",
            "Junior Security Engineer",
            "Junior SOC Analyst",
        ],
    },
    "ai-product-management": {
        "name": "AI Product Management",
        "terms": [
            "Junior Product Manager",
            "Junior Product Owner",
            "Associate Product Manager",
        ],
    },
    "devops": {
        "name": "DevOps & Cloud Computing",
        "terms": [
            "Junior DevOps",
            "Junior SRE",
            "Junior Cloud",
        ],
    },
}


def li_search(keywords: str) -> list[dict]:
    """Search LinkedIn guest API. 429 → backoff 30s and retry once."""
    url = (
        "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
        f"?keywords={keywords.replace(' ', '%20')}&location=Germany&start=0&count=10"
    )
    for attempt in (1, 2):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=10) as r:
                body = r.read().decode("utf-8", errors="replace")
            break
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt == 1:
                print(f"    429 on '{keywords}', backing off 30s...", file=sys.stderr)
                time.sleep(30)
                continue
            print(f"    Search error '{keywords}': HTTP {e.code}", file=sys.stderr)
            return []
        except Exception as e:
            print(f"    Search error '{keywords}': {e}", file=sys.stderr)
            return []

    job_ids = re.findall(r'data-entity-urn="urn:li:jobPosting:(\d+)"', body)
    titles = re.findall(
        r'class="[^"]*base-search-card__title[^"]*"[^>]*>\s*([^<\n]+)', body
    )
    companies = re.findall(
        r'class="[^"]*base-search-card__subtitle[^"]*"[^>]*>\s*<[^>]+>\s*([^<\n]+)',
        body,
    )
    locations = re.findall(
        r'class="[^"]*job-search-card__location[^"]*"[^>]*>\s*([^<\n]+)', body
    )

    results = []
    for i, jid in enumerate(job_ids):
        results.append({
            "id": jid,
            "title": htmllib.unescape(titles[i].strip()) if i < len(titles) else "",
            "company": companies[i].strip() if i < len(companies) else "",
            "location": locations[i].strip() if i < len(locations) else "",
            "url": f"https://www.linkedin.com/jobs/view/{jid}/",
        })
    return results


def li_detail(job_id: str) -> str:
    """Fetch job detail page. Returns description text (empty on failure)."""
    url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=8) as r:
            body = r.read().decode("utf-8", errors="replace")
    except Exception:
        return ""

    if "no longer accepting" in body.lower():
        return ""

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
        return re.sub(r"\s+", " ", text).strip()[:800]
    return ""


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
    except Exception as e:
        print(f"    Summary error: {e}", file=sys.stderr)
        return ""


def classify_language(text: str, title: str) -> str:
    t = (text + " " + title).lower()
    if re.search(r"fließend\s*(es)?\s*deutsch|deutsch\s*c1|muttersprache|verhandlungssicher", t):
        return "german_required"
    if re.search(r"deutsch\s*b1|basic\s*german|grundkenntnisse\s*deutsch|deutsch\s*von\s*vorteil", t):
        return "german_b1"
    if re.search(r"english\s*working\s*language|fluent\s*english|english\s*fluency|proficient\s*english", t):
        return "english_only"
    if re.search(r"german|deutsch", t):
        return "unknown"
    return "english_only"


def classify_experience(title: str, text: str) -> str:
    t = (title + " " + text).lower()
    if re.search(r"werkstudent|working\s*student|student\s*job", t):
        return "entry_level"
    if re.search(r"internship|praktikum|\bintern\b", t):
        return "internship"
    if re.search(r"\bjunior\b|entry\s*level|berufseinsteiger|0-2\s*years|0-1\s*years|1-2\s*years", t):
        return "junior"
    if re.search(r"\bsenior\b|\blead\b|\bprincipal\b|head\s*of|\bdirector\b|\barchitect\b", t):
        return "senior"
    return "other"


# --- Main ---
db = sqlite3.connect(DB_PATH)
existing_ids = set(r[0] for r in db.execute("SELECT id FROM jobs WHERE active=1").fetchall())

total_new = 0
total_skipped = 0

for slug, info in BOOTCAMPS.items():
    name = info["name"]
    print(f"  {slug}...", file=sys.stderr)

    seen = set()
    new_for_bootcamp = 0

    for term in info["terms"]:
        results = li_search(term)
        for job in results:
            if job["id"] in seen:
                continue
            seen.add(job["id"])

            job_hash = hashlib.sha256(job["url"].encode()).hexdigest()
            if job_hash in existing_ids:
                total_skipped += 1
                continue

            if not re.match(r"^\d+$", job["id"]):
                continue

            title_words = set(job["title"].lower().split())
            term_words = set(term.lower().split())
            if not (title_words & term_words):
                continue

            time.sleep(3)  # between detail fetches
            desc = li_detail(job["id"])
            if not desc or "no longer accepting" in desc.lower():
                continue

            lang = classify_language(desc, job["title"])
            exp = classify_experience(job["title"], desc)
            summary = generate_summary(job["title"], job["company"], desc, lang, exp)

            db.execute(
                """INSERT OR REPLACE INTO jobs
                   (id, title, company, location, source, url, description, summary,
                    language_req, experience_level, bootcamp, found_date, active, last_checked)
                   VALUES (?, ?, ?, ?, 'linkedin', ?, ?, ?, ?, ?, ?, date('now'), 1, date('now'))""",
                (job_hash, job["title"], job["company"], job["location"],
                 job["url"], desc, summary, lang, exp, slug),
            )
            db.commit()  # commit each listing — safe to interrupt
            existing_ids.add(job_hash)
            new_for_bootcamp += 1
            total_new += 1

        time.sleep(2)  # between search terms

    print(f"    {new_for_bootcamp} new", file=sys.stderr)
    time.sleep(8)  # between bootcamps

# --- Summary ---
active = db.execute("SELECT COUNT(*) FROM jobs WHERE active=1").fetchone()[0]
no_summary = db.execute(
    "SELECT COUNT(*) FROM jobs WHERE active=1 AND (summary IS NULL OR summary='')"
).fetchone()[0]

bootcamps = db.execute(
    "SELECT bootcamp, COUNT(*) FROM jobs WHERE active=1 "
    "GROUP BY bootcamp ORDER BY COUNT(*) DESC"
).fetchall()

today = date.today().isoformat()
print(f"\nScout scrape done — {today}")
print(f"Bootcamps scraped: {len(BOOTCAMPS)}")
print(f"New listings found: {total_new}")
print(f"Skipped (already in DB): {total_skipped}")
print(f"Total active: {active} across {len(bootcamps)} bootcamps")
print(f"Missing summaries: {no_summary}")
print()
for slug, count in bootcamps:
    print(f"  {slug}: {count}")

db.close()
