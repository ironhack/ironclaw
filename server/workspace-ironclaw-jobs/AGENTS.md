# AGENTS.md — Scout Session Rules

## Weekly Pipeline

The pipeline runs as a four-job chain. Only Job A is scheduled (Wednesdays 14:30 Rome).
Each job triggers the next when done by running:
```bash
openclaw cron run <next-job-id>
```

| Job | ID | Schedule | Responsibility |
|---|---|---|---|
| A — StepStone Scrape | `b3a1c2d4-e5f6-4789-a0b1-c2d3e4f50001` | Wed 14:30 Rome | Scrape StepStone for all 12 bootcamps |
| B — LinkedIn Scrape | `5f02fe2a-a467-4959-8052-98f3681052ca` | disabled (triggered by A) | Scrape LinkedIn for all 12 bootcamps |
| C — Staleness Check | `265d5501-52ac-47ef-9c9e-cba6e79e1929` | disabled (triggered by B) | Re-verify existing active listings |
| D — Report Generation | `b3a1c2d4-e5f6-4789-a0b1-c2d3e4f50002` | disabled (triggered by C) | Generate 13 reports, upload to S3, post URLs |

Each job runs in an isolated session with clean context. This is deliberate: scraping
12 bootcamps × multiple Playwright fetches accumulates context that cannot be reclaimed
mid-session. Starting fresh for each job keeps context bounded.

---

## Session Startup

Before doing anything else in any session:

1. Read SOUL.md — internalize the mission and red lines
2. Read TOOLS.md — confirm available tools and credentials
3. Read MEMORY.md — review known patterns and recurring issues
4. Read the most recent file in memory/ if one exists
5. Run DB migration + status check via Python (sqlite3 CLI is not installed on this host):
   ```python
   import sqlite3
   db = sqlite3.connect('jobs.db')
   cols = [r[1] for r in db.execute("PRAGMA table_info(jobs)").fetchall()]
   if 'summary' not in cols:
       db.execute("ALTER TABLE jobs ADD COLUMN summary TEXT")
       db.commit()
       print("Migrated: added summary column")
   rows = db.execute("SELECT bootcamp, COUNT(*) FROM jobs WHERE active=1 GROUP BY bootcamp ORDER BY bootcamp").fetchall()
   for r in rows: print(r)
   last = db.execute("SELECT MAX(last_checked) FROM jobs WHERE active=1").fetchone()[0]
   print("Last checked:", last)
   ```
6. Identify which pipeline job you are running (the message payload will say `pipeline-a`,
   `pipeline-b`, etc.). Proceed with the corresponding workflow below.

---

## Job A — StepStone Scrape

**Triggered by:** weekly cron (Wed 14:30 Rome)
**Triggers next:** at end of this job, run:
```bash
openclaw cron run 5f02fe2a-a467-4959-8052-98f3681052ca
```

**Responsibility:** Discover new job listings on StepStone.de for all 12 bootcamps.

**CRITICAL: Process one bootcamp at a time.** Never parallelize. Each Playwright fetch adds
to the session context and cannot be reclaimed. Finish one bootcamp completely before starting
the next. The goal is to stay within the 203k context window for all 12 bootcamps.

**Steps:**

1. For each of the 12 bootcamp slugs (in this order — same order every run for consistency):
   `ai-web-development`, `data-analytics`, `ai-consulting-integration`, `ai-driven-ux-ui`,
   `data-science-ml`, `ai-engineering`, `cloud-engineering`, `data-engineering`,
   `ai-driven-marketing`, `cybersecurity`, `ai-product-management`, `devops`

   a. Read the bootcamp profile from `bootcamps/<slug>.md`

   b. **StepStone search via Playwright** — load the search URL directly, not via Tavily:
      ```
      https://www.stepstone.de/jobs/<keyword>/in-Germany/?radius=50&sort=2&datePosted=30
      ```
      Try the primary job title AND German keyword variant from the bootcamp profile.
      Extract all individual listing URLs (`/stellenangebote--...-inline.html`) from the
      rendered results page. Collect URLs before fetching any of them.

      Fall back to Tavily (`site:stepstone.de "<job title>" junior`) only if Playwright
      returns a connection error or CAPTCHA — not because it is easier.

   c. **URL integrity gate** — for each URL collected:
      1. Format check: must be `/stellenangebote--` path with a 7-8 digit numeric ID and
         ending in `-inline.html`. Discard anything else immediately.
      2. Playwright fetch: load the page. Do NOT use HEAD requests (gets IP blocked).
      3. Existence check: if page says "Diese Stelle ist nicht mehr verfügbar" or 404 → discard.
      4. **StepStone slug consistency check (mandatory):** StepStone reuses job IDs. Parse
         the company name from the URL slug (`...--<title>-<City>-<Company>--<ID>-inline.html`)
         and compare against the company on the fetched page. If they don't match → discard.
         This catches reassigned IDs that serve a completely different job at a different company.
      5. Title plausibility: the fetched title must share at least one keyword with the search
         term that found it. If not → discard.

   d. For each URL that passes the gate, extract:
      - `title`: job title from page header
      - `company`: from page (fall back to URL slug if not found; never store NULL)
      - `location`: city/region
      - `description`: first 800 chars of the role overview text
      - `language_req`: classify from listing text (see TOOLS.md classification table)
      - `experience_level`: classify from listing text (see TOOLS.md classification table)

   e. **Generate LLM summary** — write a 2-3 sentence summary yourself as Scout:
      - Cover: (1) what the role involves, (2) key skills/tools, (3) language + experience level
      - Direct and factual — no marketing language
      - In English regardless of listing language
      - Expected: 60-120 words

   f. Upsert into jobs.db:
      ```python
      import sqlite3, hashlib
      db = sqlite3.connect('jobs.db')
      job_id = hashlib.sha256(url.encode()).hexdigest()
      db.execute("""
          INSERT OR REPLACE INTO jobs
          (id, title, company, location, source, url, description, summary,
           language_req, experience_level, bootcamp, found_date, active, last_checked)
          VALUES (?, ?, ?, ?, 'stepstone', ?, ?, ?, ?, ?, ?, date('now'), 1, date('now'))
      """, (job_id, title, company, location, url, description, summary,
            language_req, experience_level, slug))
      db.commit()
      ```

   g. **After storing this bootcamp's results:** log count (URLs found / passed gate / stored).
      Do not carry page text into the next bootcamp iteration.

2. Post brief status to #ironclaw-jobs:
   ```
   Scout Job A done — YYYY-MM-DD
   StepStone: X new listings stored across 12 bootcamps
   Starting LinkedIn scrape (Job B)...
   ```

3. Trigger Job B:
   ```bash
   openclaw cron run 5f02fe2a-a467-4959-8052-98f3681052ca
   ```

4. Write memory log to `memory/YYYY-MM-DD-a.md`: new listings per bootcamp, patterns observed,
   any StepStone issues (rate limiting, CAPTCHA, ID reassignments seen).

---

## Job B — LinkedIn Scrape

**Triggered by:** Job A
**Triggers next:**
```bash
openclaw cron run 265d5501-52ac-47ef-9c9e-cba6e79e1929
```

**Responsibility:** Discover new listings on LinkedIn for all 12 bootcamps.

LinkedIn does not require login for public job search pages. Use Playwright on LinkedIn's
public search URLs. LinkedIn has bot detection — use the helper script `scrape_linkedin.py`
which handles scrolling and extraction. See TOOLS.md for LinkedIn URL patterns.

**Same sequential per-bootcamp discipline as Job A.** Process one bootcamp, store, move on.

**Steps:**

1. For each of the 12 bootcamp slugs (same order as Job A):

   a. Read `bootcamps/<slug>.md` for job titles

   b. **LinkedIn search via Playwright:**
      Use `scrape_linkedin.py` to load and extract from:
      ```
      https://www.linkedin.com/jobs/search/?keywords=<job-title>+junior&location=Germany&f_TPR=r2592000
      ```
      (`f_TPR=r2592000` = posted in the last 30 days)
      Also try the German keyword variant.

      Extract individual listing URLs. LinkedIn listing URLs contain `/jobs/view/<ID>/`.

   c. **URL integrity gate** for LinkedIn:
      1. Format check: must be `linkedin.com/jobs/view/<numeric-ID>` format.
         Discard search results pages (`/jobs/search/`).
      2. Playwright fetch: load the individual listing page.
      3. Existence check: if page says "No longer accepting applications" or shows a
         login wall with no job content → discard.
      4. Title plausibility: same check as StepStone.
      5. **Duplicate check:** query jobs.db — if a listing with the same title + company +
         location already exists from StepStone, skip it (don't duplicate in DB).

   d. Extract title, company, location, description (800 chars), language_req, experience_level.

   e. Generate LLM summary (same 2-3 sentence format as Job A).

   f. Upsert into jobs.db with `source = 'linkedin'`.

   g. Log per-bootcamp counts. Discard page content before next bootcamp.

2. Post status to #ironclaw-jobs:
   ```
   Scout Job B done — YYYY-MM-DD
   LinkedIn: X new listings stored across 12 bootcamps
   Starting staleness check (Job C)...
   ```

3. Trigger Job C:
   ```bash
   openclaw cron run 265d5501-52ac-47ef-9c9e-cba6e79e1929
   ```

4. Write memory log to `memory/YYYY-MM-DD-b.md`: new listings per bootcamp, LinkedIn
   patterns (which job titles work, bot detection issues, login walls encountered).

---

## Job C — Staleness Check

**Triggered by:** Job B
**Triggers next:**
```bash
openclaw cron run b3a1c2d4-e5f6-4789-a0b1-c2d3e4f50002
```

**Responsibility:** Re-verify all active listings that have not been checked in >7 days.
Expire dead ones. Populate missing summaries.

This job scales with DB size, not with the bootcamp list — keep it strictly sequential
and don't carry page content between verifications.

**Steps:**

1. Query stale listings:
   ```python
   import sqlite3
   db = sqlite3.connect('jobs.db')
   stale = db.execute("""
       SELECT id, url, title, company, source, bootcamp, summary
       FROM jobs
       WHERE active=1 AND last_checked < date('now', '-7 days')
       ORDER BY source, bootcamp
   """).fetchall()
   print(f"Stale listings to verify: {len(stale)}")
   ```

2. For each stale listing:

   a. Fetch the page via Playwright (for both StepStone and LinkedIn).

   b. **Expiry checks:**
      - Page 404, "Diese Stelle ist nicht mehr verfügbar", "No longer accepting", "expired" → set `active=0`
      - StepStone slug consistency check: if company in URL slug no longer matches page → set `active=0`
      - Title drift: if fetched title shares no keywords with stored title → set `active=0`
      - Fetch fails twice → leave active; after 14 days without any confirmation, auto-expire:
        ```python
        db.execute("UPDATE jobs SET active=0 WHERE active=1 AND last_checked < date('now', '-14 days')")
        db.commit()
        ```

   c. If listing is still valid: update `last_checked = date('now')`, keep `active=1`.
      If `summary IS NULL`, generate one now (same 2-3 sentence format).

   d. Commit each update immediately — don't batch updates.

3. Auto-expire anything beyond 14 days:
   ```python
   db.execute("UPDATE jobs SET active=0 WHERE active=1 AND last_checked < date('now', '-14 days')")
   db.commit()
   ```

4. Post status to #ironclaw-jobs:
   ```
   Scout Job C done — YYYY-MM-DD
   Verified: X listings | Expired: Y | Summaries filled: Z
   Starting report generation (Job D)...
   ```

5. Trigger Job D:
   ```bash
   openclaw cron run b3a1c2d4-e5f6-4789-a0b1-c2d3e4f50002
   ```

6. Write memory log to `memory/YYYY-MM-DD-c.md`: expiry counts, any patterns (which
   bootcamps had the most expirations, which sources expire faster).

---

## Job D — Report Generation

**Triggered by:** Job C
**Triggers next:** nothing — end of pipeline.

**Responsibility:** Read the DB and generate 13 HTML reports. No Playwright. No scraping.
This session is read-only against the DB and write-only to S3.

**Steps:**

0. Get today's date:
   ```bash
   date +%Y-%m-%d
   ```
   Use this exact string everywhere. Do not guess.

1. Query all active listings:
   ```python
   import sqlite3
   db = sqlite3.connect('jobs.db')
   total = db.execute("SELECT COUNT(*) FROM jobs WHERE active=1").fetchone()[0]
   by_bootcamp = db.execute("SELECT bootcamp, COUNT(*) FROM jobs WHERE active=1 GROUP BY bootcamp ORDER BY bootcamp").fetchall()
   ```

2. **Generate the general report** (all 12 bootcamps, table format, for monitoring):
   Use the General Report Format from TOOLS.md. Top 10 per bootcamp, sorted by language_req
   then experience_level. Save to `/tmp/scout-report-YYYY-MM-DD.html`. Upload to S3:
   ```bash
   aws s3 cp /tmp/scout-report-YYYY-MM-DD.html \
     s3://ih-ironclaw/jobs/YYYY-MM-DD/report.html \
     --content-type text/html --region eu-west-1
   ```

3. **Generate 12 per-bootcamp branded reports** (Ironhack branding, all active listings,
   card layout, LLM summary per listing, PDF export button):
   Use the Branded Report Format from TOOLS.md. No LIMIT — include all active listings.
   For each slug, save to `/tmp/scout-report-YYYY-MM-DD-<slug>.html` and upload:
   ```bash
   aws s3 cp /tmp/scout-report-YYYY-MM-DD-<slug>.html \
     s3://ih-ironclaw/jobs/YYYY-MM-DD/report-<slug>.html \
     --content-type text/html --region eu-west-1
   ```

4. Post all 13 URLs to #ironclaw-jobs:
   ```
   Scout pipeline complete — YYYY-MM-DD
   X active listings across 12 bootcamps

   General report: https://ih-ironclaw.s3.eu-west-1.amazonaws.com/jobs/YYYY-MM-DD/report.html

   Bootcamp reports:
   • AI Web Development: https://ih-ironclaw.s3.eu-west-1.amazonaws.com/jobs/YYYY-MM-DD/report-ai-web-development.html
   • Data Analytics: https://ih-ironclaw.s3.eu-west-1.amazonaws.com/jobs/YYYY-MM-DD/report-data-analytics.html
   • AI Consulting & Integration: https://ih-ironclaw.s3.eu-west-1.amazonaws.com/jobs/YYYY-MM-DD/report-ai-consulting-integration.html
   • AI-Driven UX/UI: https://ih-ironclaw.s3.eu-west-1.amazonaws.com/jobs/YYYY-MM-DD/report-ai-driven-ux-ui.html
   • Data Science & ML: https://ih-ironclaw.s3.eu-west-1.amazonaws.com/jobs/YYYY-MM-DD/report-data-science-ml.html
   • AI Engineering: https://ih-ironclaw.s3.eu-west-1.amazonaws.com/jobs/YYYY-MM-DD/report-ai-engineering.html
   • Cloud Engineering: https://ih-ironclaw.s3.eu-west-1.amazonaws.com/jobs/YYYY-MM-DD/report-cloud-engineering.html
   • Data Engineering: https://ih-ironclaw.s3.eu-west-1.amazonaws.com/jobs/YYYY-MM-DD/report-data-engineering.html
   • AI-Driven Marketing: https://ih-ironclaw.s3.eu-west-1.amazonaws.com/jobs/YYYY-MM-DD/report-ai-driven-marketing.html
   • Cybersecurity: https://ih-ironclaw.s3.eu-west-1.amazonaws.com/jobs/YYYY-MM-DD/report-cybersecurity.html
   • AI Product Management: https://ih-ironclaw.s3.eu-west-1.amazonaws.com/jobs/YYYY-MM-DD/report-ai-product-management.html
   • DevOps & Cloud: https://ih-ironclaw.s3.eu-west-1.amazonaws.com/jobs/YYYY-MM-DD/report-devops.html
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

6. Write memory log to `memory/YYYY-MM-DD-d.md`: total listings per bootcamp, report URLs,
   any bootcamps with <5 listings (flag for next scrape to prioritize).

---

## Memory Updates

Memory files for this pipeline follow a per-job naming convention:
- `memory/YYYY-MM-DD-a.md` — StepStone scrape log
- `memory/YYYY-MM-DD-b.md` — LinkedIn scrape log
- `memory/YYYY-MM-DD-c.md` — Staleness check log
- `memory/YYYY-MM-DD-d.md` — Report generation log

Update `MEMORY.md` at the end of any session where a lasting pattern is discovered
(new working search term, new blocking pattern, seasonal trend, etc.).

---

## Ad-Hoc Questions

If asked a question about the job market in #ironclaw-jobs:
- Query jobs.db via Python (sqlite3 CLI not available)
- If data is >7 days old, caveat that it may be stale
- Respond concisely in Slack (bullet list, no markdown tables)

## First-Time Setup

If jobs.db is missing or empty, run `python3 init-db.py` first.
