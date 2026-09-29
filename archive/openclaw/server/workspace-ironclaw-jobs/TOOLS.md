# TOOLS.md — Scout Environment

## LinkedIn Guest API (primary source)

LinkedIn exposes an unauthenticated guest API used for public job embeds. No auth, no Playwright,
works from any IP. Use this as the sole job source.

**Search endpoint:**
```python
import urllib.request, re

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'text/html,application/xhtml+xml,*/*',
    'Referer': 'https://www.linkedin.com/',
}

def li_search(keywords, count=10):
    url = (f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
           f"?keywords={keywords.replace(' ', '%20')}&location=Germany&start=0&count={count}")
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as r:
        body = r.read().decode('utf-8', errors='replace')
    job_ids = re.findall(r'data-entity-urn="urn:li:jobPosting:(\d+)"', body)
    titles   = re.findall(r'class="[^"]*base-search-card__title[^"]*"[^>]*>\s*([^<\n]+)', body)
    companies = re.findall(r'class="[^"]*base-search-card__subtitle[^"]*"[^>]*>\s*<[^>]+>\s*([^<\n]+)', body)
    locations = re.findall(r'class="[^"]*job-search-card__location[^"]*"[^>]*>\s*([^<\n]+)', body)
    jobs = []
    for i, jid in enumerate(job_ids):
        jobs.append({
            'id': jid,
            'title': titles[i].strip() if i < len(titles) else '',
            'company': companies[i].strip() if i < len(companies) else '',
            'location': locations[i].strip() if i < len(locations) else '',
            'url': f"https://www.linkedin.com/jobs/view/{jid}/",
        })
    return jobs
```

**Detail endpoint (full description):**
```python
def li_detail(job_id):
    url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as r:
        body = r.read().decode('utf-8', errors='replace')
    m = re.search(r'<div[^>]+class="[^"]*show-more-less-html__markup[^"]*"[^>]*>(.*?)</div', body, re.DOTALL)
    if not m:
        m = re.search(r'<div[^>]+class="[^"]*description__text[^"]*"[^>]*>(.*?)</section', body, re.DOTALL)
    if m:
        text = re.sub(r'<[^>]+>', ' ', m.group(1))
        return re.sub(r'\s+', ' ', text).strip()[:800]
    return ''
```

**Search tips:**
- Try both English title ("Junior Data Analyst") and German variant ("Junior Datenanalyst")
- De-duplicate by job ID across both searches before fetching details
- `&f_TPR=r2592000` can be appended to filter last 30 days (not always honoured by guest API)
- HTML-decode titles: `import html; title = html.unescape(title)`

**No Playwright needed** for job searches. Playwright is not installed in a useful state.

## URL Integrity Rules

**LinkedIn valid listing URL:**
```
https://www.linkedin.com/jobs/view/<NUMERIC-ID>/
```
- Must be numeric ID only — discard any other format
- Already in DB? `SELECT id FROM jobs WHERE id=SHA256(url) AND active=1` — skip
- Title plausibility: fetched title must share at least one keyword with the search term
- "No longer accepting applications" in detail response → discard

**Never construct or modify URLs.** Only use IDs returned by the search endpoint.

## Language Requirement Classification

When reading a listing, classify `language_req`:

| Signal in listing | Classification |
|---|---|
| "English working language", listing is in English with no German mentioned | `english_only` |
| "German B1", "basic German", "Deutsch von Vorteil", "Grundkenntnisse Deutsch" | `german_b1` |
| "fließend Deutsch", "Deutsch C1", "Muttersprache", "verhandlungssicher" | `german_required` |
| No language requirement stated | `unknown` |

## Experience Level Classification

| Signal in listing | Classification |
|---|---|
| "internship", "Praktikum", "intern" | `internship` |
| "junior", "Junior", "entry level", "Berufseinsteiger", "0-2 years" | `junior` |
| "Werkstudent", "working student", "student job" | `entry_level` |
| Anything else | `other` |

## LLM Summary Generation

After extracting a listing, generate a concise summary to store in the `summary` column.
You write this yourself as Scout — it is your synthesis, not an API call.

Using the 800-char description, write a 2-3 sentence summary for a German caseworker evaluating
whether this role suits an Ironhack bootcamp graduate. Cover:
(1) what the role involves day-to-day, (2) key technical skills or tools required,
(3) language/experience level expected.
Be direct and factual. No marketing language. Written in English.

**Good example:**
"Junior Data Analyst role at a Berlin fintech building Power BI dashboards and writing SQL queries
for internal reporting pipelines. Requires Python basics and 0-1 years of experience.
Listing is in English with no German language requirement stated."

Expected length: 60-120 words.

## SQLite Database

**Path:** `/home/openclaw/.openclaw/workspace-ironclaw-jobs/jobs.db`

**Initialize:** `python3 init-db.py` (run once at first startup)

**Note:** `sqlite3` CLI is NOT installed. Use Python for all DB access:
```python
import sqlite3
db = sqlite3.connect('jobs.db')
rows = db.execute("SELECT ...").fetchall()
```

**Schema:**
```sql
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,        -- SHA256(url)
  title TEXT NOT NULL,
  company TEXT,
  location TEXT,
  source TEXT,                -- 'linkedin'
  url TEXT NOT NULL,
  description TEXT,           -- raw text excerpt, up to 800 chars
  summary TEXT,               -- LLM-generated 2-3 sentence summary
  language_req TEXT,          -- 'english_only' | 'german_b1' | 'german_required' | 'unknown'
  experience_level TEXT,      -- 'internship' | 'junior' | 'entry_level' | 'other'
  bootcamp TEXT NOT NULL,
  found_date TEXT,
  active INTEGER DEFAULT 1,
  last_checked TEXT
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
```python
# Active listings per bootcamp
db.execute("SELECT bootcamp, COUNT(*) FROM jobs WHERE active=1 GROUP BY bootcamp").fetchall()

# English-only or B1 listings
db.execute("SELECT title, company, location, url FROM jobs WHERE bootcamp='data-analytics' AND active=1 AND language_req IN ('english_only','german_b1') LIMIT 10").fetchall()

# Stale listings
db.execute("SELECT id, url FROM jobs WHERE active=1 AND last_checked < date('now','-7 days')").fetchall()
```

## S3 File Sharing

**Bucket:** `ih-ironclaw`, region: `eu-west-1`
**Folder:** `jobs/YYYY-MM-DD/`

**Files uploaded per report run (13 total):**
```
jobs/YYYY-MM-DD/report.html
jobs/YYYY-MM-DD/report-ai-web-development.html
jobs/YYYY-MM-DD/report-data-analytics.html
jobs/YYYY-MM-DD/report-ai-consulting-integration.html
jobs/YYYY-MM-DD/report-ai-driven-ux-ui.html
jobs/YYYY-MM-DD/report-data-science-ml.html
jobs/YYYY-MM-DD/report-ai-engineering.html
jobs/YYYY-MM-DD/report-cloud-engineering.html
jobs/YYYY-MM-DD/report-data-engineering.html
jobs/YYYY-MM-DD/report-ai-driven-marketing.html
jobs/YYYY-MM-DD/report-cybersecurity.html
jobs/YYYY-MM-DD/report-ai-product-management.html
jobs/YYYY-MM-DD/report-devops.html
```

**Upload command:**
```bash
aws s3 cp /tmp/<filename>.html \
  s3://ih-ironclaw/jobs/YYYY-MM-DD/<filename>.html \
  --content-type text/html --region eu-west-1
```

**Direct permanent URL:**
`https://ih-ironclaw.s3.eu-west-1.amazonaws.com/jobs/YYYY-MM-DD/report-<slug>.html`

**Note:** Do NOT use `--acl public-read` — bucket policy handles access. Do NOT use presigned URLs.

## Report Templates

- General report (all bootcamps, table format): read `template-general.md`
- Branded per-bootcamp reports (Ironhack design, card layout): read `template-branded.md`

Only needed in Job D (report generation).

## Slack

**Channel:** `#ironclaw-jobs` (ID: `C0B1KDU4Q8P`)
- Use bullet lists, not markdown tables
- Keep summaries under 10 lines
- Always include the S3 URL when posting a report

## Style Rules

- No em dashes — use commas or colons instead
- Lead with the number: "47 active listings across 12 bootcamps"
- Cite sources explicitly
- Flag uncertainty: "last verified 5 days ago" is better than presenting stale data as current
