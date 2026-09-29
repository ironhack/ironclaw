# HTML Report Generation Pattern

This reference captures the proven approach for generating the full HTML SEO report.
Write a single Python script to `/tmp/build_report.py`, run it, then upload the output to S3.

## Why a Python script instead of inline shell

- **Tirith security**: Backslash-escaped CSS in shell strings triggers rejection.
- **Python 3.11 f-strings**: No backslash allowed inside `{...}`. Two safe approaches below.
- **Self-contained**: Embed all computed data directly. The script IS the report.
- **No seo-report.py**: That script produces broken dates and only a skeleton.

## Two proven approaches for report generation

### Approach A: Raw string (recommended, simplest)

Use `r"""..."""` (raw string) to avoid ALL escaping issues. Embed data directly without f-string interpolation. This sidesteps the Python 3.11 backslash-in-f-string limitation entirely.

```python
#!/usr/bin/env python3
"""Generate comprehensive SEO report HTML for YYYY-MM-DD"""

# 1. EMBED ALL DATA as hardcoded values (from analysis phase)
# All computations done before the HTML string -- no f-string backslash risk

HTML = r"""<!DOCTYPE html>
<html>
...all CSS and HTML goes here with real values, no {variables}...
</html>"""

with open("/tmp/seo-report-YYYY-MM-DD.html", "w") as f:
    f.write(HTML)
```

Pro: zero escaping issues, no f-string gotchas. Con: must pre-compute all values manually.

### Approach B: F-strings with extracted variables

```python
#!/usr/bin/env python3
"""Generate comprehensive SEO report HTML for YYYY-MM-DD"""

# 1. EMBED ALL DATA (hardcoded from analysis phase)
perf = { "ES": {"clicks": 235, ...}, ... }

# 2. COMPUTE DERIVED VALUES
total_clicks = sum(p["clicks"] for p in perf.values())

# 3. EXTRACT STRINGS WITH SPECIAL CHARS before f-string interpolation
ZERO_CTR = "<span class='zero'>0.00%</span>"
ARROW_UP = "&#8593;"

# 4. BUILD HTML WITH F-STRINGS (Python 3.11 safe because special chars are in variables)
html = f"""<!DOCTYPE html>...{ZERO_CTR}...{total_clicks}..."""

# 5. WRITE TO FILE
with open("/tmp/seo-report-YYYY-MM-DD.html", "w") as f:
    f.write(html)
```

## Key style rules

- Inline CSS only, no external stylesheets
- Dark gradient header: `linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%)`
- Apple-like typography: `-apple-system, BlinkMacSystemFont, 'Segoe UI', ...`
- No em dashes anywhere (use hyphens, commas, colons)
- Impact badges: High=red (#cc0000), Medium=orange (#e65100), Low=grey (#6e6e73)
- Green up (#34c759), red down (#ff3b30)
- Max width 1200px, mobile responsive, print-friendly
- AIO risk flag: CTR < 0.5% AND impressions > 5,000

## CSS patterns

```css
/* Summary cards */
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; }
.card { background: #fff; border-radius: 12px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }

/* Tables */
table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 12px; overflow: hidden; }
th { background: #f5f5f7; color: #86868b; font-weight: 600; text-transform: uppercase; font-size: 12px; }

/* Delta indicators */
.delta.up { color: #34c759; }
.delta.down { color: #ff3b30; }

/* AIO risk flag */
.aio-warn { background: #fff8e1; border-left: 3px solid #ffc107; }

/* Insight boxes */
.insight { background: #f0f4ff; border-left: 3px solid #0f3460; }

/* Quick wins */
.quick-win { background: #e8f5e9; border-left: 3px solid #34c759; }
```

## Sections (MUST include all 10)

1. Header (report title + date range + markets)
2. Performance Snapshot (summary cards + per-market table with brand/non-brand split + GA4 organic sessions + engagement rate -- combine GSC and GA4 in one table to show the full picture per market in a single view)
3. 4-Week Click Trend (per-market weekly numbers + trend direction arrows)
4. Engagement & Traffic Quality (GA4 organic sessions, engagement rate, organic share, avg duration, 1-line insight per market)
5. Top Movers (top 3-5 gainers/losers per market by clicks)
6. Top Pages & AIO Risk (exclude FR "c" artifact, flag CTR<0.5% + imp>5K)
7. SEO Intelligence (condensed from Google News RSS research)
8. PR Correlations (skip if GitHub not authenticated, note limitation)
9. Backlog (grouped by impact tier, days open, resolved count, 2-3 quick wins)
10. Footer (generated date, data sources)

**Prioritize the GSC + GA4 combined view in section 2.** The merged table (clicks, impressions, CTR, position from GSC + sessions, organic share, engagement from GA4) tells a complete story per market in one place. This is the most referenced section by stakeholders.

## Pitfall: Backlog section accuracy

**Never manually transcribe or eyeball backlog items into the HTML report.** This produces wrong impact-tier counts and stale item descriptions. Reported 9/13/7 High/Med/Low when actual was 11/14/4 on 2026-07-27.

Before writing the HTML, verify counts programmatically from the JSON:
```python
import json
with open('workspace/seo-backlog.json') as f:
    data = json.load(f)
open_items = [i for i in data['items'] if i['status'] == 'open']
for imp in ['High', 'Medium', 'Low']:
    items = [i for i in open_items if i['impact'] == imp]
    print(f'{imp}: {len(items)}')
```
Use these verified counts in the section header (`29 open items (11 High, 14 Medium, 4 Low)`) and in each table. For table contents, read `id`, `issue`, `recommendation`, `market`, and `added_date` from the live JSON -- the backlog evolves between runs. Do not hardcode from memory or a previous report.

## Pitfall: Em dashes leak from backlog JSON into the report

The "No em dashes" red line applies to report output, but `seo-backlog.json` is manually maintained and items can contain em dashes (U+2014) or en dashes (U+2013) inside `issue`/`recommendation` text. The builder reads this JSON and embeds it, so those leak into the HTML. Two-part fix:
1. Sanitize the source JSON first: replace U+2014 with ` - ` and U+2013 with `-` in every item's `issue` and `recommendation`.
2. Add a safety net in the builder just before writing: `html = html.replace('\u2014', ' - ').replace('\u2013', '-')`.

Verify `html.count('\u2014') == 0` and `html.count('\u2013') == 0` before uploading. Also compute `days_open` in the builder as `(date.today() - date.fromisoformat(item['added_date'])).days` rather than hardcoding it.

## Upload

```bash
aws s3 cp /tmp/seo-report-YYYY-MM-DD.html s3://ih-ironclaw/seo/YYYY-MM-DD/report.html --region eu-west-1
```

## Pitfall: Python 3.11 f-string backslash

The Hermes venv runs Python 3.11. Do NOT put backslash-escaped quotes inside f-string expressions:
```python
# BROKEN:
html = f'<span class=\\'zero\\'>0</span>'

# FIX (approach B -- extract variable):
ZERO = "<span class='zero'>0</span>"
html = f"Value: {ZERO}"

# FIX (approach A -- use raw string instead, no interpolation):
html = r"""<span class='zero'>0</span>"""
```
**Recommendation:** Use Approach A (raw string) for HTML reports. The report data doesn't change during generation -- compute all values before the HTML block, then write a raw string with hardcoded numbers. This eliminates the entire class of f-string escaping bugs.
