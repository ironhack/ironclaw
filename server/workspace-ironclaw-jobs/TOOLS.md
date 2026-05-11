# TOOLS.md — Scout Environment

## Web Search & Fetch

**Primary: Tavily** (`TAVILY_API_KEY` in env)
- `tavily_search`: job discovery queries — use to find listings on StepStone/Indeed
- `tavily_extract`: fetch full listing page content from a URL
- Scope searches to job boards: `site:stepstone.de OR site:de.indeed.com`

**Fallback: Playwright/Chromium**
- Use when Tavily rate-limits or cannot render a dynamic listing page
- Available via the browser tool built into the OpenClaw runtime

## Job Board Search Patterns

**StepStone.de:**
```
site:stepstone.de "<job title>" junior
site:stepstone.de "<job title>" Praktikum
site:stepstone.de "<job title>" Werkstudent
```
Or direct URL structure:
```
https://www.stepstone.de/jobs/<keyword>/in-Germany/?radius=50&sort=2
```

**Indeed.de:**
```
site:de.indeed.com "<job title>" junior Germany
site:de.indeed.com "<job title>" internship Germany
```
Or direct URL structure:
```
https://de.indeed.com/jobs?q=<keyword>+junior&l=Germany&lang=en
```

**Tips:**
- Try both English and German job title variants (see each bootcamp profile)
- "Werkstudent" + tech term is high-signal for entry-level in Germany
- "Berufseinsteiger" = entry-level (German keyword)
- Filter for postings in last 30 days when possible

## Language Requirement Classification

When reading a listing, classify `language_req`:

| Signal in listing | Classification |
|---|---|
| "English working language", "English only", listing is in English with no German mentioned | `english_only` |
| "German B1", "basic German", "Deutsch von Vorteil", "Grundkenntnisse Deutsch" | `german_b1` |
| "fließend Deutsch", "Deutsch C1", "Muttersprache", "native German", "verhandlungssicher" | `german_required` |
| No language requirement stated | `unknown` |

## Experience Level Classification

| Signal in listing | Classification |
|---|---|
| "internship", "Praktikum", "intern" | `internship` |
| "junior", "Junior", "entry level", "Berufseinsteiger", "0-2 years" | `junior` |
| "Werkstudent", "working student", "student job" | `entry_level` |
| Anything else | `other` |

## SQLite Database

**Path:** `/home/openclaw/.openclaw/workspace-ironclaw-jobs/jobs.db`

**Initialize:** `python3 init-db.py` (run once at first startup)

**Schema:**
```sql
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,        -- SHA256(url)
  title TEXT NOT NULL,
  company TEXT,
  location TEXT,
  source TEXT,                -- 'stepstone' | 'indeed'
  url TEXT NOT NULL,
  description TEXT,
  language_req TEXT,          -- 'english_only' | 'german_b1' | 'german_required' | 'unknown'
  experience_level TEXT,      -- 'internship' | 'junior' | 'entry_level' | 'other'
  bootcamp TEXT NOT NULL,     -- slug matching bootcamp filename (without .md)
  found_date TEXT,            -- ISO date YYYY-MM-DD
  active INTEGER DEFAULT 1,   -- 1=live, 0=expired
  last_checked TEXT           -- ISO date of last verification
);

CREATE TABLE IF NOT EXISTS reports (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  generated_date TEXT NOT NULL,
  s3_url TEXT NOT NULL,
  job_count INTEGER,
  notes TEXT
);
```

**Useful queries:**
```bash
# Active listings per bootcamp
sqlite3 jobs.db "SELECT bootcamp, COUNT(*) FROM jobs WHERE active=1 GROUP BY bootcamp;"

# English-only or B1 listings for a bootcamp
sqlite3 jobs.db "SELECT title, company, location, url FROM jobs WHERE bootcamp='data-analytics' AND active=1 AND language_req IN ('english_only','german_b1') LIMIT 10;"

# Stale listings (not checked in 7+ days)
sqlite3 jobs.db "SELECT id, url FROM jobs WHERE active=1 AND last_checked < date('now','-7 days');"
```

## S3 File Sharing

**Bucket:** `ih-ironclaw`, region: `eu-west-1`
**Folder:** `jobs/YYYY-MM-DD/`
**Direct permanent URL:** `https://ih-ironclaw.s3.eu-west-1.amazonaws.com/jobs/YYYY-MM-DD/report.html`

**Upload command:**
```bash
aws s3 cp /tmp/scout-report-YYYY-MM-DD.html \
  s3://ih-ironclaw/jobs/YYYY-MM-DD/report.html \
  --content-type text/html \
  --region eu-west-1
```

**Note:** The `ih-ironclaw` bucket has Block Public Access disabled and a bucket-level policy granting `s3:GetObject` on covered prefixes. The `jobs/*` prefix must be added to that policy before first upload (one-time SSH task). Do NOT use `--acl public-read` — the bucket policy handles access. Do NOT use presigned URLs — use direct permanent URLs only.

## HTML Report Format

The caseworker report should be a clean, professional HTML file. Structure:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Ironhack Germany Job Market Report — YYYY-MM-DD</title>
  <style>
    body { font-family: Arial, sans-serif; max-width: 1100px; margin: 40px auto; color: #333; }
    h1 { color: #1a1a2e; }
    h2 { color: #e63946; border-bottom: 2px solid #e63946; padding-bottom: 4px; margin-top: 40px; }
    table { width: 100%; border-collapse: collapse; margin-top: 12px; }
    th { background: #f4f4f4; text-align: left; padding: 8px 12px; font-size: 13px; }
    td { padding: 8px 12px; border-bottom: 1px solid #eee; font-size: 13px; }
    .tag-en { background: #d4edda; color: #155724; padding: 2px 6px; border-radius: 3px; font-size: 11px; }
    .tag-b1 { background: #fff3cd; color: #856404; padding: 2px 6px; border-radius: 3px; font-size: 11px; }
    .tag-unk { background: #f8f9fa; color: #6c757d; padding: 2px 6px; border-radius: 3px; font-size: 11px; }
    .footer { margin-top: 60px; font-size: 12px; color: #999; }
  </style>
</head>
<body>
  <h1>Ironhack Germany — Junior Job Market Report</h1>
  <p>Generated: YYYY-MM-DD | Source: StepStone.de + Indeed.de | Verified active listings only</p>
  <p>This report shows currently available entry-level positions in Germany for graduates of each Ironhack program.
     Listings are filtered for junior, internship, or entry-level experience requirements.
     Language requirement tags: <span class="tag-en">English-only</span> <span class="tag-b1">German B1 sufficient</span> <span class="tag-unk">Not specified</span></p>

  <!-- One <section> per bootcamp -->
  <h2>AI Web Development</h2>
  <p>Full-stack web development with JavaScript, React, Node.js, and MongoDB.</p>
  <table>
    <tr><th>Job Title</th><th>Company</th><th>Location</th><th>Language</th><th>Level</th><th>Source</th></tr>
    <!-- rows -->
  </table>

  <div class="footer">
    Report generated by Ironhack Scout agent. All listings sourced directly from public job boards.
    For verification, click any listing URL. Report date: YYYY-MM-DD.
  </div>
</body>
</html>
```

## Slack

**Channel:** `#ironclaw-jobs` (ID: `C0B1KDU4Q8P`)
- Use bullet lists, not markdown tables (Slack doesn't render them)
- Keep summaries under 10 lines
- Always include the S3 URL when posting a report

## Style Rules

- No em dashes — use commas or colons instead
- Lead with the number: "47 active listings across 12 bootcamps" not "We found many listings"
- Cite sources explicitly when talking about specific listings
- Flag uncertainty: "last verified 5 days ago" is better than presenting stale data as current
