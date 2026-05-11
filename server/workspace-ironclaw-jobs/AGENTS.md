# AGENTS.md — Scout Session Rules

## Session Startup

Every session, do this first:

1. Read SOUL.md — internalize the mission and red lines
2. Read TOOLS.md — confirm available tools and credentials
3. Read MEMORY.md — review known patterns and recurring issues
4. Read the most recent file in memory/ if one exists
5. Run: `sqlite3 jobs.db "SELECT bootcamp, COUNT(*) as active FROM jobs WHERE active=1 GROUP BY bootcamp ORDER BY bootcamp;"` — report active listing counts per bootcamp
6. Note the most recent `last_checked` date across the database — if it's >7 days ago, recommend a scrape run

Then respond to the user with a brief status: how many active listings per bootcamp, when last scraped.

## First-Time Setup

If jobs.db is empty (no tables), run init-db.py first:
```bash
python3 init-db.py
```

## Workflow A: Scrape (weekly cron or manual trigger)

**Trigger phrase:** "scrape", "update listings", "find new jobs", or weekly cron fires

**Steps:**

1. For each file in bootcamps/:
   a. Read the bootcamp profile (job titles, search terms, language note)
   b. For each search term, run a Tavily search scoped to StepStone.de and Indeed.de:
      - Query: `site:stepstone.de OR site:de.indeed.com "<job title>" junior Germany`
      - Also try German variants listed in the profile
   c. For each result URL, use Tavily extract to fetch the full listing page
   d. Extract: title, company, location, language requirements, experience level, description snippet
   e. Classify language_req: scan for "English", "German B1", "Deutsch", "fließend", "native" etc.
   f. Classify experience_level: scan for "junior", "internship", "Praktikum", "Werkstudent", "0-2 years", "Berufseinsteiger"
   g. Compute id = SHA256(url)
   h. Upsert into jobs.db (INSERT OR REPLACE), set last_checked = today, active = 1

2. **Staleness check** — after all bootcamps are scraped:
   a. Query: `SELECT id, url, bootcamp FROM jobs WHERE active=1 AND last_checked < date('now', '-7 days')`
   b. For each stale listing, fetch the URL via Tavily extract
   c. If page returns 404 / "job no longer available" / "Diese Stelle ist nicht mehr verfügbar" / equivalent → set active=0
   d. If page loads as valid listing → update last_checked, keep active=1
   e. If Tavily fails → leave active but note it; after 14 days without confirmation, auto-expire: `UPDATE jobs SET active=0 WHERE last_checked < date('now', '-14 days') AND active=1`

3. Post Slack summary to #ironclaw-jobs:
   ```
   Scout scrape complete — YYYY-MM-DD
   • New listings found: X
   • Listings expired: Y
   • Total active: Z across 12 bootcamps
   ```

## Workflow B: Report (on-demand or weekly cron)

**Trigger phrase:** "generate report", "caseworker report", "create report", or weekly cron fires

**Steps:**

1. For each bootcamp, query:
   ```sql
   SELECT * FROM jobs
   WHERE bootcamp = '<slug>' AND active = 1
   ORDER BY
     CASE language_req
       WHEN 'english_only' THEN 1
       WHEN 'german_b1' THEN 2
       WHEN 'unknown' THEN 3
       WHEN 'german_required' THEN 4
     END,
     CASE experience_level
       WHEN 'internship' THEN 1
       WHEN 'junior' THEN 2
       WHEN 'entry_level' THEN 3
       ELSE 4
     END
   LIMIT 10;
   ```

2. If a bootcamp has fewer than 5 active listings, note it — do not pad with inactive or fabricated listings.

3. Generate HTML report (see TOOLS.md for format). One section per bootcamp with:
   - Bootcamp name and brief description (1 sentence)
   - Table: Job Title | Company | Location | Language Requirement | Source | URL
   - Note at bottom if fewer than 5 listings were found

4. Upload to S3:
   ```bash
   aws s3 cp /tmp/scout-report-YYYY-MM-DD.html \
     s3://ih-ironclaw/jobs/YYYY-MM-DD/report.html \
     --acl public-read --content-type text/html --region eu-west-1
   ```

5. Post to #ironclaw-jobs:
   ```
   Scout report generated — YYYY-MM-DD
   Caseworker report: https://ih-ironclaw.s3.eu-west-1.amazonaws.com/jobs/YYYY-MM-DD/report.html
   Covers X active listings across 12 bootcamps.
   ```

6. Log to reports table: `INSERT INTO reports (generated_date, s3_url, job_count) VALUES (...)`

## Memory Updates

At the end of each session, write a brief log to memory/YYYY-MM-DD.md:
- How many listings found/expired this run
- Which bootcamps had the most/least results
- Any search patterns that worked particularly well or poorly
- Any recurring issues with sources (rate limiting, page structure changes)
- Update MEMORY.md if any lasting patterns were discovered

## Ad-Hoc Questions

If asked a question about the job market ("are there React jobs in Berlin?", "how many cybersecurity listings?"):
- Query jobs.db for the answer
- If the data is >7 days old, caveat that it may be stale
- Respond concisely in Slack (bullet list, no markdown tables)
