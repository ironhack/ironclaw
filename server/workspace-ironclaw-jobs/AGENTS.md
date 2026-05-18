# AGENTS.md — Scout Session Rules

## Session Startup

Every session, do this first:

1. Read SOUL.md — internalize the mission and red lines
2. Read TOOLS.md — confirm available tools and credentials
3. Read MEMORY.md — review known patterns and recurring issues
4. Read the most recent file in memory/ if one exists
5. Run DB migration + status check via Python (sqlite3 CLI is not installed on this host):
   ```python
   import sqlite3
   db = sqlite3.connect('jobs.db')
   # Migrate: add summary column if missing
   cols = [r[1] for r in db.execute("PRAGMA table_info(jobs)").fetchall()]
   if 'summary' not in cols:
       db.execute("ALTER TABLE jobs ADD COLUMN summary TEXT")
       db.commit()
       print("Migrated: added summary column")
   # Status
   rows = db.execute("SELECT bootcamp, COUNT(*) as cnt FROM jobs WHERE active=1 GROUP BY bootcamp ORDER BY bootcamp").fetchall()
   for r in rows: print(r)
   last = db.execute("SELECT MAX(last_checked) FROM jobs WHERE active=1").fetchone()[0]
   print("Last checked:", last)
   ```
6. Note the most recent `last_checked` date — if >7 days ago, recommend a scrape run

Then respond to the user with a brief status: how many active listings per bootcamp, when last scraped.

## First-Time Setup

If jobs.db is empty (no tables), run init-db.py first:
```bash
python3 init-db.py
```

## Workflow A: Scrape (weekly cron or manual trigger)

**Trigger phrase:** "scrape", "update listings", "find new jobs", or weekly cron fires

**CRITICAL: Process sequentially, one bootcamp at a time. Never spawn subagents. Never
parallelize across bootcamps.** The reason: each URL fetch (Playwright or Tavily) adds
content to context. Processing all 12 bootcamps at once overflows the 203k context window
and causes rate limit errors. Finish each bootcamp completely (search → verify → store) before
moving to the next. After storing each bootcamp's results, you can discard the fetched page
content from working memory — only the stored DB records need to persist.

**Steps:**

1. For each file in bootcamps/:
   a. Read the bootcamp profile (job titles, search terms, language note)

   b. **Run separate search passes for each portal** — do NOT combine them in a single query:

      **StepStone pass — Playwright is mandatory, Tavily is emergency fallback only:**

      Use Playwright to load StepStone's own search. This is non-negotiable: StepStone's own
      search returns only live, current listings. Tavily searches Google's index, which is
      always stale — it returns URLs for jobs that may have expired days or weeks ago.

      For each job title in the profile, load via Playwright:
      ```
      https://www.stepstone.de/jobs/<keyword>/in-Germany/?radius=50&sort=2&datePosted=30
      ```
      Try both English and German keyword variants. Extract the individual listing URLs
      (`/stellenangebote--...-inline.html`) directly from the rendered search results page.

      **Only fall back to Tavily for StepStone if Playwright explicitly fails** — meaning:
      the browser returns a connection error, StepStone serves a CAPTCHA you cannot bypass,
      or the IP is actively blocked (you get no search results at all, not just fewer results).
      "Playwright is slow" or "Tavily is easier" are NOT valid reasons to fall back.

      If you do fall back to Tavily for StepStone, the verification rules in step (c) become
      even stricter: every URL sourced from Tavily MUST pass the full Playwright page fetch
      and slug consistency check. A Tavily search snippet alone is never sufficient to verify
      a StepStone listing — you must load the actual page. If Playwright is truly unavailable
      and you cannot load the page, discard the URL entirely. Do not store it.

      Tavily StepStone queries (fallback only):
      - `site:stepstone.de "<job title>" junior`
      - `site:stepstone.de "<job title>" Werkstudent`
      - `site:stepstone.de "<job title>" Praktikum`

      **Indeed pass — same rule as StepStone:**

      Use Playwright to load Indeed's own search first:
      ```
      https://de.indeed.com/jobs?q=<keyword>+junior&l=Germany&lang=en
      ```
      Extract individual listing URLs (`/viewjob?jk=`) from the rendered results page.

      Fall back to Tavily only if Playwright is blocked or returns no results at all.
      If you fall back to Tavily, every URL found must still be verified by loading it
      in Playwright before storing. A Tavily snippet is not verification.

      Tavily Indeed queries (fallback only):
      - `site:de.indeed.com "<job title>" junior Germany`
      - `site:de.indeed.com "<job title>" internship Germany`
      Also try German variants.

      Collect all result URLs from both passes before proceeding.

   c. **URL integrity gate — mandatory before storing anything:**

      For each URL returned by search:

      1. **Validate URL format first:**
         - StepStone listing URLs must contain a numeric job ID and end in `-inline.html`
           (pattern: `stepstone.de/stellenangebote--...-NNNNNNN-inline.html`).
           If the URL ends in `--index.html`, has no numeric ID, or looks like a search results
           page, discard it immediately — it is not a real listing URL.
         - Indeed listing URLs must contain a job key parameter (`jk=` or `/viewjob?jk=`).
           Discard search results page URLs (`indeed.com/jobs?q=`).

      2. **Extract the page content via Playwright:**
         - For ALL URLs (both StepStone and Indeed): load the page with Playwright.
           Do NOT make a separate HEAD request first — bulk HEAD requests get the server IP
           blocked by both portals after ~20 requests.
         - Tavily extract is a last resort if Playwright returns completely empty content
           on two attempts. If Tavily extract also returns empty, discard the URL.

      3. **Verify the extraction succeeded:**
         - The extracted content must include a recognizable job title and company name.
         - If the page returns 404, "job no longer available", "Diese Stelle ist nicht mehr
           verfügbar", "expired", or equivalent → discard.
         - If extraction fails entirely (no content returned) → discard. Do NOT store a listing
           that was not successfully fetched.

      4. **StepStone URL slug consistency check — mandatory:**
         StepStone reassigns job IDs over time. A URL slug that encoded "Accenture" six weeks
         ago may now point to a completely different employer. After fetching the page:
         - Parse the URL slug to extract the encoded company name and job title.
           Pattern: `...--<job-title-words>-<City>-<CompanyName>--<ID>-inline.html`
           Example: `...Junior-Technologie-Berater-Duesseldorf-Accenture--13973821-inline.html`
           → slug company = "Accenture", slug title ≈ "Junior Technologie Berater"
         - Extract the actual company name and job title from the fetched page content.
         - If the page company does NOT match the slug company → discard immediately.
           This is the primary symptom of a reassigned job ID.
         - If the page title shares no keywords with the slug title → discard.
         Do NOT rely solely on whether the page loaded successfully — a successfully loaded page
         can be a completely different job at a different company.

      5. **Title plausibility check:**
         - The job title on the fetched page must share at least one substantive keyword with
           the search term that surfaced it (e.g. a "Junior React Developer" search returning a
           "Callcenter Agent" listing fails this check). If it does not match → discard.

   d. After passing the integrity gate, extract from the page:
      - title, company, location, language requirements, experience level
      - description: first 800 chars of the listing body text (role overview section)

      **Company name extraction — required, not optional:**
      - Parse from the page content first (look for company name in the header, job meta, or posting author).
      - If the page extraction didn't yield a company name, fall back to the URL slug:
        - StepStone: the slug pattern is `--<job-title>-<City>-<Company-Name>--<ID>-inline.html`.
          Extract the segment between the last city token and the numeric ID.
          Example: `...Junior-Frontend-Developer-Berlin-Apryl-GmbH--13790453-inline.html` → `Apryl GmbH`
        - Indeed: company is usually present in the extracted page text near the job title.
      - If company still cannot be determined after both attempts, store `"Unknown"` — never store NULL or empty string.

   e. Classify language_req: scan for "English", "German B1", "Deutsch", "fließend", "native", etc.
      (See TOOLS.md for classification table.)

   f. Classify experience_level: scan for "junior", "internship", "Praktikum", "Werkstudent",
      "0-2 years", "Berufseinsteiger". (See TOOLS.md for classification table.)

   g. **Generate a concise LLM summary** — mandatory for every new listing:

      Using the extracted `description` text, write a 2-3 sentence summary for a German
      caseworker. You write this yourself as Scout — it is your synthesis of the listing.

      The summary must:
      - Be 2-3 sentences, 60-120 words
      - Cover: (1) what the role involves day-to-day, (2) key technical skills/tools required,
        (3) language and experience level expected
      - Be direct and factual — no "exciting opportunity" or marketing language
      - Be written in English regardless of the original listing language

      Good example: "Junior Data Analyst role at a Berlin fintech, focused on building Power BI
      dashboards and writing SQL queries for internal reporting pipelines. Requires Python basics
      and 0-1 years of experience. Listing is in English with no German language requirement stated."

      Store the result in the `summary` column.

   h. Compute id = SHA256(url)

   i. Upsert into jobs.db via Python:
      ```python
      import sqlite3, hashlib
      db = sqlite3.connect('jobs.db')
      job_id = hashlib.sha256(url.encode()).hexdigest()
      db.execute("""
          INSERT OR REPLACE INTO jobs
          (id, title, company, location, source, url, description, summary,
           language_req, experience_level, bootcamp, found_date, active, last_checked)
          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, date('now'), 1, date('now'))
      """, (job_id, title, company, location, source, url, description, summary,
            language_req, experience_level, bootcamp))
      db.commit()
      ```

   **At end of each bootcamp:** Log how many URLs were found via search, how many passed the
   integrity gate, and how many were stored. Release all fetched page content from working memory
   before processing the next bootcamp — do not carry page text across bootcamp boundaries.

2. **Staleness check** — after all bootcamps are scraped:
   a. Query stale listings via Python:
      ```python
      rows = db.execute("SELECT id, url, title, company, bootcamp FROM jobs WHERE active=1 AND last_checked < date('now', '-7 days')").fetchall()
      ```
   b. For each stale listing, fetch the URL via Playwright (for StepStone) or Tavily extract (for Indeed)
   c. If page returns 404 / "job no longer available" / "Diese Stelle ist nicht mehr verfügbar" → set active=0
   d. **Content drift check (StepStone):** Even if the page loads, run the slug consistency check.
      If the company changed → set active=0.
   e. Also compare fetched job title against stored title. If they share no keywords → set active=0.
   f. If page loads and content matches → update last_checked, keep active=1. If `summary IS NULL`,
      generate and store a summary now (same 2-3 sentence format as step 1g).
   g. If fetch fails entirely → leave active; after 14 days without confirmation, auto-expire:
      ```python
      db.execute("UPDATE jobs SET active=0 WHERE last_checked < date('now', '-14 days') AND active=1")
      db.commit()
      ```

3. **Post Slack summary and trigger the report workflow:**
   Post to #ironclaw-jobs:
   ```
   Scout scrape complete — YYYY-MM-DD
   • URLs found via search: X (StepStone: A, Indeed: B)
   • Passed URL verification: C
   • New listings stored: D | Listings expired: E
   • Total active: Z across 12 bootcamps

   Trigger: generate caseworker report YYYY-MM-DD
   ```
   The "Trigger: generate caseworker report" line starts a fresh report session with clean context.
   **End the scrape session immediately after posting this message** — do NOT generate reports
   in this same session.

## Workflow B: Report (triggered by scrape completion or manual request)

**Trigger phrase:** "generate caseworker report", "generate report", "caseworker report", or "create report"

This workflow runs in a **fresh session** with clean context. It reads from the DB only — no
Playwright, no scraping. Report generation should be fast and not stress the context window.

**Steps:**

0. **Get today's date:**
   ```bash
   date +%Y-%m-%d
   ```
   Use this exact string as YYYY-MM-DD throughout. Do NOT use a date from memory or session history.

1. Query listing counts:
   ```python
   import sqlite3
   db = sqlite3.connect('jobs.db')
   rows = db.execute("SELECT bootcamp, COUNT(*) FROM jobs WHERE active=1 GROUP BY bootcamp ORDER BY bootcamp").fetchall()
   total = db.execute("SELECT COUNT(*) FROM jobs WHERE active=1").fetchone()[0]
   ```

2. **Generate the general report** (existing format, for monitoring and debugging):

   For each bootcamp, query the top 10 active listings sorted by language_req priority then
   experience_level. Build the HTML using the General Report Format template from TOOLS.md.
   Save to `/tmp/scout-report-YYYY-MM-DD.html`

   Upload:
   ```bash
   aws s3 cp /tmp/scout-report-YYYY-MM-DD.html \
     s3://ih-ironclaw/jobs/YYYY-MM-DD/report.html \
     --content-type text/html --region eu-west-1
   ```

3. **Generate 12 per-bootcamp branded reports:**

   For each of the 12 bootcamp slugs, in this order:
   `ai-web-development`, `data-analytics`, `ai-consulting-integration`, `ai-driven-ux-ui`,
   `data-science-ml`, `ai-engineering`, `cloud-engineering`, `data-engineering`,
   `ai-driven-marketing`, `cybersecurity`, `ai-product-management`, `devops`

   Query ALL active listings (no LIMIT):
   ```python
   rows = db.execute("""
       SELECT title, company, location, url, language_req, experience_level, summary
       FROM jobs
       WHERE bootcamp = ? AND active = 1
       ORDER BY
         CASE language_req WHEN 'english_only' THEN 1 WHEN 'german_b1' THEN 2 WHEN 'unknown' THEN 3 ELSE 4 END,
         CASE experience_level WHEN 'internship' THEN 1 WHEN 'junior' THEN 2 WHEN 'entry_level' THEN 3 ELSE 4 END
   """, (slug,)).fetchall()
   ```

   Build HTML using the Branded Per-Bootcamp Report Format from TOOLS.md (with the embedded
   Ironhack logo base64, Ironhack blue `#5BBFE3`, card layout, PDF export button).

   Save to `/tmp/scout-report-YYYY-MM-DD-<slug>.html`

   Upload:
   ```bash
   aws s3 cp /tmp/scout-report-YYYY-MM-DD-<slug>.html \
     s3://ih-ironclaw/jobs/YYYY-MM-DD/report-<slug>.html \
     --content-type text/html --region eu-west-1
   ```

4. **Post to #ironclaw-jobs:**
   ```
   Scout report ready — YYYY-MM-DD
   General (all bootcamps): https://ih-ironclaw.s3.eu-west-1.amazonaws.com/jobs/YYYY-MM-DD/report.html

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
        total,
        '13 reports: 1 general + 12 per-bootcamp branded')
   )
   db.commit()
   ```

## Memory Updates

At the end of each session, write a brief log to memory/YYYY-MM-DD.md:
- How many listings found/expired this run
- Which bootcamps had the most/least results
- Any search patterns that worked particularly well or poorly
- Any recurring issues with sources (rate limiting, page structure changes)
- Update MEMORY.md if any lasting patterns were discovered

## Ad-Hoc Questions

If asked a question about the job market ("are there React jobs in Berlin?", "how many cybersecurity listings?"):
- Query jobs.db via Python (sqlite3 CLI not available)
- If the data is >7 days old, caveat that it may be stale
- Respond concisely in Slack (bullet list, no markdown tables)
