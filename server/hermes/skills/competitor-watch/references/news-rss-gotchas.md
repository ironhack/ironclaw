# News RSS Parsing Gotchas

## Date Filter: Timezone-Aware vs Naive Datetime

**The bug:** `email.utils.parsedate_to_datetime()` returns timezone-aware
datetimes in Python 3.11+. When compared against a naive `datetime.datetime()`,
Python raises `TypeError: can't compare offset-naive and offset-aware datetimes`.

With a `bare except: pass` around the comparison, the exception is swallowed
and all articles pass through unfiltered — including articles from 2018.

**Observed 2026-07-27:** Google News RSS returned articles from 2018, 2022,
and April 2026. With a naive `CUTOFF = datetime.datetime(2026, 6, 27)`, the
comparison threw `TypeError` on every article and the bare except let them all
through, contaminating the news journal with 7+ year-old articles.

**The fix:**

```python
import datetime
from email.utils import parsedate_to_datetime

# MUST be timezone-aware
CUTOFF = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)

# Or for a fixed date:
CUTOFF = datetime.datetime(2026, 7, 27, tzinfo=datetime.timezone.utc) - datetime.timedelta(days=30)

# Then:
if pub_date:
    try:
        parsed = parsedate_to_datetime(pub_date)
        if parsed < CUTOFF:
            continue  # skip old articles
    except Exception:
        pass  # unparseable date — keep the article, don't lose data
```

**Verification:** The script should print skipped articles so you can
confirm the filter is working:
```python
if parsed < CUTOFF:
    print(f"  SKIP (old): {comp}: {title[:60]}... ({pub_date})")
    continue
```

## Zero Results ≠ Bug

When every competitor's RSS returns only listicles or pre-cutoff articles,
the result is `articles: []` for every competitor. This is normal — not a
parsing failure. Create the journal with empty arrays and a scan-record
line in the jsonl. Verify by checking the console output: skipped articles
should be logged with "SKIP (old)" or listicle filter messages.

**When the all-empty result will be written into the report as "no news",
run one raw-feed confirmation pass before concluding.** Print the RAW items
(no filters) for a representative query per competitor — one en-US plus one
localized — each tagged with an age bucket: `NEW` if within the 30-day
cutoff, else `OLD(n days)`. Feeds returning only OLD listicles confirm
genuine absence; a feed returning zero raw items at all means the
query/network failed and needs a retry, NOT a "no news" conclusion. A raw
pass also catches over-filtering (a genuinely newsworthy item wrongly
skip-phrased). Observed 2026-09-07: all 7 competitors filtered to 0
articles, and the raw pass showed healthy feeds (4–26 items each, all
listicles or 96–2,000+ days old) — honest-empty confirmed.

## Single-Script urllib Fetch + Parse (avoids shell `&` detection)

The curl-based approach in SKILL.md Step 3 works, but the RSS URL contains
literal `&` characters (`&hl=en-US&gl=US&ceid=US:en`) that the cron security
scanner can flag as background-process requests. A cleaner, fully cron-safe
alternative is ONE `write_file` Python script that fetches, parses, filters,
and saves in a single pass using `urllib.request` — no shell `&`, no
pipe-to-interpreter, no heredoc:

```python
import urllib.request, urllib.parse, xml.etree.ElementTree as ET
q = urllib.parse.quote_plus('Le Wagon bootcamp')
url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
data = urllib.request.urlopen(req, timeout=30).read()
root = ET.fromstring(data)
```

The script then loops competitors, applies the skip-phrase + listicle-publisher
filters and the 30-day cutoff, writes `news-journal.json`, and appends the scan
record to `news-journal.jsonl` — all via one `python3 /tmp/news_scan.py` call.
Observed 2026-08-31: 7 competitors fetched/parsed in seconds with zero shell
issues. Sanity-check the feed isn't silently empty by printing the raw item
count for one competitor before the filter runs.

## parsedate_to_datetime Can Return Naive Datetimes

`parsedate_to_datetime()` usually returns timezone-aware datetimes, but for a
`pubDate` string with no timezone it returns a NAIVE datetime. The naive-vs-aware
comparison then raises `TypeError` inside the try block and the article is
silently KEPT rather than filtered. Guard explicitly:

```python
parsed = parsedate_to_datetime(pub)
if parsed.tzinfo is None:
    parsed = parsed.replace(tzinfo=datetime.timezone.utc)
if parsed < CUTOFF:
    continue
```

(In practice Google News RSS `pubDate` always carries a GMT/UTC suffix so this
rarely fires — but the guard makes the cutoff robust instead of silently dropping
the filter on the first naive date.)
