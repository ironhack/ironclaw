# AGENTS.md — Scout Session Rules

## Weekly Pipeline

14-job chain. Only Job 01 is scheduled (Wednesdays 14:30 Rome). Each job triggers the next
at the end of its session with `openclaw cron run <next-job-id>`.

| # | Job | ID | Bootcamp |
|---|---|---|---|
| 01 | Jobs: Scrape 01 ai-web-development | `b3a1c2d4-e5f6-4789-a0b1-c2d3e4f50001` | ai-web-development |
| 02 | Jobs: Scrape 02 data-analytics | `9ce2b7a8-fbaf-41c6-bb86-f355ffa658c7` | data-analytics |
| 03 | Jobs: Scrape 03 ai-consulting-integration | `3acb0b8f-1828-45ec-bb9a-bb524a4ffe15` | ai-consulting-integration |
| 04 | Jobs: Scrape 04 ai-driven-ux-ui | `a2022597-e706-4136-bedb-76e5c8613c3e` | ai-driven-ux-ui |
| 05 | Jobs: Scrape 05 data-science-ml | `4d44d5eb-2f88-401b-bdf3-5462306c6cf9` | data-science-ml |
| 06 | Jobs: Scrape 06 ai-engineering | `23375e7a-a083-46e8-a7fc-03117c37c645` | ai-engineering |
| 07 | Jobs: Scrape 07 cloud-engineering | `6ea65326-7ce7-4281-9253-35aa1cdd2951` | cloud-engineering |
| 08 | Jobs: Scrape 08 data-engineering | `2734a449-3f36-43e0-b054-aed00d8b4e1b` | data-engineering |
| 09 | Jobs: Scrape 09 ai-driven-marketing | `9acc1b09-642c-4a8f-b2bc-6b99a3ec7eaf` | ai-driven-marketing |
| 10 | Jobs: Scrape 10 cybersecurity | `6b290887-3dda-475e-b757-bb13b5440076` | cybersecurity |
| 11 | Jobs: Scrape 11 ai-product-management | `88bc0fa2-c82b-4fac-840a-418d3df74624` | ai-product-management |
| 12 | Jobs: Scrape 12 devops | `d5deea80-1e09-47ba-94bc-08b69b28fc93` | devops |
| C | Jobs: Staleness Check | `f2de03a2-c9db-4687-be37-0e9c13159646` | — |
| D | Jobs: Report Generation | `b7d82600-3935-4055-9de4-670126646234` | — |

Trigger chain: 01 → 02 → 03 → 04 → 05 → 06 → 07 → 08 → 09 → 10 → 11 → 12 → C → D

---

## Session Startup

Before doing anything else:

1. Read SOUL.md
2. Read TOOLS.md
3. Read MEMORY.md
4. Read the most recent file in memory/ if one exists
5. Run DB migration + status check:
   ```python
   import sqlite3
   db = sqlite3.connect('jobs.db')
   cols = [r[1] for r in db.execute("PRAGMA table_info(jobs)").fetchall()]
   if 'summary' not in cols:
       db.execute("ALTER TABLE jobs ADD COLUMN summary TEXT")
       db.commit()
   rows = db.execute("SELECT bootcamp, COUNT(*) FROM jobs WHERE active=1 GROUP BY bootcamp ORDER BY bootcamp").fetchall()
   for r in rows: print(r)
   ```
6. Identify your job from the message payload:
   - `scrape-<slug>` → follow **Bootcamp Scrape Workflow** below
   - `pipeline-c` → follow **Job C** below
   - `pipeline-d` → follow **Job D** below

---

## Bootcamp Scrape Workflow

**Source:** LinkedIn Guest API only (see TOOLS.md). No Playwright, no StepStone.
**Target:** Up to 10 new listings per run. Generate LLM summaries at scrape time.

---

### Step 1 — Read bootcamp profile

```bash
cat bootcamps/<slug>.md
```

Note the primary job title and German keyword variant.

---

### Step 2 — LinkedIn search (max 10 new listings)

**a. Search via guest API:**
```python
import urllib.request, re, html as htmllib

# Search primary English title
jobs = li_search(primary_title)  # function from TOOLS.md
# Also search German variant — combine, deduplicate by ID
jobs += li_search(german_variant)
seen_ids = set()
unique_jobs = [j for j in jobs if not (j['id'] in seen_ids or seen_ids.add(j['id']))]
```

**b. URL integrity gate — process one at a time, stop after 10 pass:**
1. Already in DB? `SELECT id FROM jobs WHERE id=SHA256(url) AND active=1` — skip if exists.
2. Fetch detail via `li_detail(job_id)` (from TOOLS.md).
3. "No longer accepting applications" in response → discard.
4. Title plausibility: HTML-decoded title must share at least one keyword with the search term.
5. HTML-decode title: `import html; title = html.unescape(raw_title)`

Stop verifying once 10 have passed the gate.

**c. For each passing listing, extract:**
- `title`, `company`, `location` (from search response)
- `description`: `li_detail(job_id)` → first 800 chars of role text
- `language_req`: classify per TOOLS.md
- `experience_level`: classify per TOOLS.md

**d. Generate LLM summary** — write it yourself as Scout:
- 2-3 sentences: (1) what the role involves, (2) key skills/tools, (3) language + experience level
- Direct and factual. In English. 60-120 words.

**e. Upsert:**
```python
import sqlite3, hashlib
db = sqlite3.connect('jobs.db')
job_id = hashlib.sha256(url.encode()).hexdigest()
db.execute("""
    INSERT OR REPLACE INTO jobs
    (id, title, company, location, source, url, description, summary,
     language_req, experience_level, bootcamp, found_date, active, last_checked)
    VALUES (?, ?, ?, ?, 'linkedin', ?, ?, ?, ?, ?, ?, date('now'), 1, date('now'))
""", (job_id, title, company, location, url, description, summary,
      language_req, experience_level, slug))
db.commit()
```

---

### Step 3 — Post status and trigger next

**Do these in order. Do not skip the Slack post.**

1. **Post to #ironclaw-jobs** (always — never skip):
```
Scout <slug> done — YYYY-MM-DD
LinkedIn: X new
```

2. **Trigger the next job via bash** (the cron tool cannot trigger other jobs — use exec only):
```bash
openclaw cron run <next-job-uuid>
```
Expected result: `{"ok": true, "enqueued": true}`. Do not call the cron tool for this — only bash/exec.

3. **Write memory** to `memory/YYYY-MM-DD-<slug>.md` only if something notable happened.

---

## Job C — Staleness Check

**Triggered by:** Job 12 (devops)

**Steps:**

1. Query stale listings:
   ```python
   import sqlite3
   db = sqlite3.connect('jobs.db')
   stale = db.execute("""
       SELECT id, url, title, company, bootcamp, summary
       FROM jobs WHERE active=1 AND last_checked < date('now', '-7 days')
   """).fetchall()
   print(f"Stale: {len(stale)}")
   ```

2. For each stale listing, call the guest detail API:
   ```python
   import urllib.request
   jid = re.search(r'/jobs/view/(\d+)/', url).group(1)
   detail_url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{jid}"
   try:
       req = urllib.request.Request(detail_url, headers=HEADERS)
       with urllib.request.urlopen(req, timeout=15) as r:
           body = r.read().decode('utf-8', errors='replace')
       status = 200
   except urllib.error.HTTPError as e:
       status, body = e.code, ''
   ```
   - `status == 404` → `active=0` (deleted)
   - `status == 200` and "No longer accepting" in body → `active=0`
   - `status == 200`, valid content → update `last_checked = date('now')`; fill summary if NULL
   - Any other exception → leave active; 14-day rule catches it

3. Auto-expire beyond 14 days:
   ```python
   db.execute("UPDATE jobs SET active=0 WHERE active=1 AND last_checked < date('now', '-14 days')")
   db.commit()
   ```

4. Post to #ironclaw-jobs:
   ```
   Scout Job C done — YYYY-MM-DD
   Verified: X | Expired: Y | Summaries filled: Z
   Starting report generation (Job D)...
   ```

5. Trigger Job D via bash (exec only — do not use the cron tool):
   ```bash
   openclaw cron run b7d82600-3935-4055-9de4-670126646234
   ```

6. Write `memory/YYYY-MM-DD-c.md`.

---

## Job D — Report Generation

**Triggered by:** Job C. **No scraping — DB reads only.**

**Steps:**

0. `date +%Y-%m-%d`

1. Query active listings:
   ```python
   import sqlite3
   db = sqlite3.connect('jobs.db')
   total = db.execute("SELECT COUNT(*) FROM jobs WHERE active=1").fetchone()[0]
   ```

2. **General report** (all 12 bootcamps, table format): read `template-general.md`, fill in data.
   ```bash
   aws s3 cp /tmp/scout-report-YYYY-MM-DD.html \
     s3://ih-ironclaw/jobs/YYYY-MM-DD/report.html \
     --content-type text/html --region eu-west-1
   ```

3. **12 per-bootcamp branded reports**: read `template-branded.md`.
   Show top 10 best-fit listings per bootcamp: exclude `german_required`, sort by language
   (english_only first) then experience level (junior first). Use `active_count = len(rows)`.

   ```python
   rows = db.execute("""
       SELECT title, company, location, url, language_req, experience_level, summary
       FROM jobs
       WHERE bootcamp=? AND active=1
         AND language_req != 'german_required'
       ORDER BY
         CASE language_req
           WHEN 'english_only' THEN 1
           WHEN 'german_b1'    THEN 2
           WHEN 'unknown'      THEN 3
           ELSE 4
         END,
         CASE experience_level
           WHEN 'junior'      THEN 1
           WHEN 'entry_level' THEN 2
           WHEN 'internship'  THEN 3
           ELSE 4
         END
       LIMIT 10
   """, (slug,)).fetchall()
   active_count = len(rows)
   ```

   ```bash
   aws s3 cp /tmp/scout-report-YYYY-MM-DD-<slug>.html \
     s3://ih-ironclaw/jobs/YYYY-MM-DD/report-<slug>.html \
     --content-type text/html --region eu-west-1
   ```

4. Post all 13 URLs to #ironclaw-jobs:
   ```
   Scout pipeline complete — YYYY-MM-DD
   X active listings across 12 bootcamps

   General: https://ih-ironclaw.s3.eu-west-1.amazonaws.com/jobs/YYYY-MM-DD/report.html
   • AI Web Development: .../report-ai-web-development.html
   • Data Analytics: .../report-data-analytics.html
   [... all 12 ...]
   ```

5. Log to reports table:
   ```python
   db.execute(
       "INSERT INTO reports (generated_date, s3_url, job_count, notes) VALUES (?, ?, ?, ?)",
       ('YYYY-MM-DD',
        'https://ih-ironclaw.s3.eu-west-1.amazonaws.com/jobs/YYYY-MM-DD/report.html',
        total, '13 reports: 1 general + 12 per-bootcamp branded')
   )
   db.commit()
   ```

6. Write `memory/YYYY-MM-DD-d.md`.

---

## Ad-Hoc Questions

If asked a question about the job market in #ironclaw-jobs:
- Query jobs.db via Python (sqlite3 CLI not available)
- If data is >7 days old, note it may be stale
- Respond concisely (bullet list)
- If jobs.db is missing: `python3 init-db.py`
