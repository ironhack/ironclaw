---
name: google-marketing-intelligence
description: "Argos domain skill: query GA4, GSC, and Google Ads via Python client libraries using a service account. Covers auth, key metrics, report structures, and reporting cadence for Ironhack marketing."
version: 1.0.0
author: Helios (Hermes Agent)
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [google-ads, ga4, gsc, marketing, analytics, reporting]
    related_skills: []
---

# Google Marketing Intelligence — Argos Domain Skill

Argos's operating guide for querying Google Ads (GADS), Google Analytics 4 (GA4), and Google Search Console (GSC) via service account authentication. Load this skill at the start of every data retrieval or reporting session.

## Authentication

All three platforms use a **Google Service Account** JSON key. The key path is in `GOOGLE_APPLICATION_CREDENTIALS`.

### Required Scopes per Platform

| Platform | Scope |
|---|---|
| GA4 (Data API) | `https://www.googleapis.com/auth/analytics.readonly` |
| GSC (Search Console) | `https://www.googleapis.com/auth/webmasters.readonly` |
| Google Ads | Uses env vars (developer token + service account JSON) |

### Python Auth Pattern (GA4 + GSC)

Credentials are loaded from the `GOOGLE_APPLICATION_CREDENTIALS_JSON` env var (inline JSON content — not a file path):

```python
import json
import os
from google.oauth2 import service_account

SCOPES = [
    "https://www.googleapis.com/auth/analytics.readonly",
    "https://www.googleapis.com/auth/webmasters.readonly",
]

service_account_info = json.loads(os.environ["GOOGLE_APPLICATION_CREDENTIALS_JSON"])
credentials = service_account.Credentials.from_service_account_info(
    service_account_info,
    scopes=SCOPES,
)
```

### Google Ads Auth

The `google-ads` library only accepts `json_key_file_path` as a file path string — it does NOT accept inline service account dicts. Write the JSON to a temp file first:

```python
import json
import os
import tempfile
from google.ads.googleads.client import GoogleAdsClient

service_account_info = json.loads(os.environ["GOOGLE_APPLICATION_CREDENTIALS_JSON"])

_keyfile = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
json.dump(service_account_info, _keyfile)
_keyfile.close()

client = GoogleAdsClient.load_from_dict({
    "developer_token": os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"],
    "login_customer_id": os.environ["GOOGLE_ADS_LOGIN_CUSTOMER_ID"],
    "use_proto_plus": True,
    "json_key_file_path": _keyfile.name,
})
```

## Package Installation

```bash
pip install --break-system-packages \
  google-analytics-data \
  google-auth \
  google-api-python-client \
  google-ads
```

On Debian/Ubuntu with system Python (PEP 668), `--break-system-packages` is required unless running inside a venv. If `python3-venv` is available, a venv is the cleaner option; otherwise the flag is safe for the Hermes agent environment.

---

## GA4 — Google Analytics 4 (Data API v1)

**Property ID** from `GA4_PROPERTY_ID` env var (numeric only, e.g. `123456789`).

### Key Dimensions & Metrics

| Dimension | Description |
|---|---|
| `date` | YYYYMMDD |
| `sessionDefaultChannelGroup` | Channel grouping (Paid Search, Organic, etc.) |
| `campaignName` | GA4 campaign name (UTM) |
| `sessionCampaignId` | Campaign ID |
| `country` | Country |
| `deviceCategory` | desktop / mobile / tablet |
| `landingPage` | Landing page path |

| Metric | Description |
|---|---|
| `sessions` | Sessions |
| `conversions` | All conversion events |
| `totalRevenue` | Revenue |
| `bounceRate` | Bounce rate |
| `averageSessionDuration` | Avg session duration (seconds) |
| `newUsers` | New users |

### Sample GA4 Query

```python
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    DateRange, Dimension, Metric, RunReportRequest
)

client = BetaAnalyticsDataClient(credentials=credentials)
property_id = os.environ["GA4_PROPERTY_ID"]

request = RunReportRequest(
    property=f"properties/{property_id}",
    dimensions=[
        Dimension(name="date"),
        Dimension(name="campaignName"),
        Dimension(name="country"),
        Dimension(name="sessionDefaultChannelGroup"),
    ],
    metrics=[
        Metric(name="sessions"),
        Metric(name="conversions"),
        Metric(name="totalRevenue"),
    ],
    date_ranges=[DateRange(start_date="7daysAgo", end_date="yesterday")],
)
response = client.run_report(request)
```

---

## GSC — Google Search Console (Search Analytics API)

**Site URL** from `GSC_SITE_URL` env var (must match exactly as in GSC, including trailing slash).

### Key Dimensions

`query`, `page`, `country`, `device`, `date`, `searchAppearance`

### Key Metrics

`clicks`, `impressions`, `ctr`, `position`

### Sample GSC Query

```python
from googleapiclient.discovery import build

service = build("searchconsole", "v1", credentials=credentials)
site_url = os.environ["GSC_SITE_URL"]

body = {
    "startDate": "2025-06-01",
    "endDate": "2025-06-30",
    "dimensions": ["query", "country", "device"],
    "rowLimit": 25000,
    "startRow": 0,
}
response = service.searchanalytics().query(siteUrl=site_url, body=body).execute()
rows = response.get("rows", [])
```

---

## Google Ads (GADS) — Key Report Types

**Customer IDs** from `GADS_CUSTOMER_ID` (comma-separated for multi-account). `login_customer_id` = MCC account ID.

### Campaign Performance

```python
ga_service = client.get_service("GoogleAdsService")
customer_id = os.environ["GADS_CUSTOMER_ID"].split(",")[0].strip()

query = """
    SELECT
      campaign.id,
      campaign.name,
      campaign.status,
      campaign.advertising_channel_type,
      campaign_budget.amount_micros,
      metrics.impressions,
      metrics.clicks,
      metrics.cost_micros,
      metrics.conversions,
      metrics.conversions_value,
      metrics.average_cpc,
      metrics.search_impression_share,
      metrics.search_budget_lost_impression_share,
      metrics.search_rank_lost_impression_share,
      metrics.ctr
    FROM campaign
    WHERE segments.date DURING LAST_7_DAYS
      AND campaign.status != 'REMOVED'
    ORDER BY metrics.cost_micros DESC
"""
response = ga_service.search_stream(customer_id=customer_id, query=query)
```

### Ad Group Performance

```python
query = """
    SELECT
      campaign.name,
      ad_group.name,
      ad_group.status,
      metrics.impressions,
      metrics.clicks,
      metrics.cost_micros,
      metrics.conversions,
      metrics.average_cpc
    FROM ad_group
    WHERE segments.date DURING LAST_7_DAYS
      AND ad_group.status != 'REMOVED'
"""
```

### Keywords

```python
query = """
    SELECT
      campaign.name,
      ad_group.name,
      ad_group_criterion.keyword.text,
      ad_group_criterion.keyword.match_type,
      ad_group_criterion.status,
      metrics.impressions,
      metrics.clicks,
      metrics.cost_micros,
      metrics.conversions,
      metrics.average_cpc,
      metrics.search_impression_share
    FROM keyword_view
    WHERE segments.date DURING LAST_7_DAYS
      AND ad_group_criterion.status != 'REMOVED'
    ORDER BY metrics.cost_micros DESC
"""
```

### Search Terms

```python
query = """
    SELECT
      campaign.name,
      ad_group.name,
      search_term_view.search_term,
      search_term_view.status,
      metrics.impressions,
      metrics.clicks,
      metrics.cost_micros,
      metrics.conversions,
      metrics.average_cpc
    FROM search_term_view
    WHERE segments.date DURING LAST_7_DAYS
    ORDER BY metrics.cost_micros DESC
    LIMIT 500
"""
```

### Auction Insights (Brand Campaigns)

Auction insight fields are selectable with `FROM campaign` (not a separate resource). Query:

```python
query = """
    SELECT
      campaign.id,
      campaign.name,
      segments.auction_insight_domain,
      metrics.auction_insight_search_impression_share,
      metrics.auction_insight_search_overlap_rate,
      metrics.auction_insight_search_position_above_rate,
      metrics.auction_insight_search_top_impression_percentage,
      metrics.auction_insight_search_outranking_share
    FROM campaign
    WHERE segments.date BETWEEN 'YYYY-MM-DD' AND 'YYYY-MM-DD'
    ORDER BY metrics.auction_insight_search_impression_share DESC
"""
```

**Important**: Auction insights require developer token with Auction Insights access. If PERMISSION_DENIED is returned, contact Google Ads API support for access upgrade. The query syntax above is correct — the fields exist and are selectable with `campaign`, `ad_group`, `customer`, and `keyword_view` resources. Filter brand campaigns client-side by name pattern.

### Performance Report — Multi-timeframe Query Pattern

For the new performance report, data is collected at 4 levels (campaign, ad_group, keyword, ad) across 6 date buckets (3 timeframes × current/previous periods). The efficient approach queries 60 days of data once per level and splits client-side by date:

```python
# Timeframes
TIMEFRAMES = {
    "last_7d":  {"current": (yesterday-6d, yesterday),    "previous": (yesterday-13d, yesterday-7d)},
    "last_14d": {"current": (yesterday-13d, yesterday),   "previous": (yesterday-27d, yesterday-14d)},
    "last_30d": {"current": (yesterday-29d, yesterday),   "previous": (yesterday-59d, yesterday-30d)},
}

# Query the full 60-day window, route each row to buckets by segments.date
query = f"""
    SELECT campaign.id, campaign.name, ..., segments.date, metrics.impressions, ...
    FROM campaign
    WHERE segments.date BETWEEN '{start_60d_ago}' AND '{yesterday}'
      AND campaign.status != 'REMOVED'
"""
```

### Geographic Performance

```python
query = """
    SELECT
      geographic_view.country_criterion_id,
      geographic_view.location_type,
      campaign.name,
      metrics.impressions,
      metrics.clicks,
      metrics.cost_micros,
      metrics.conversions
    FROM geographic_view
    WHERE segments.date DURING LAST_7_DAYS
    ORDER BY metrics.cost_micros DESC
"""
```

### Device Performance

```python
query = """
    SELECT
      campaign.name,
      segments.device,
      metrics.impressions,
      metrics.clicks,
      metrics.cost_micros,
      metrics.conversions
    FROM campaign
    WHERE segments.date DURING LAST_7_DAYS
"""
```

### Budget Check (Daily Sanity — uses YESTERDAY)

```python
query = """
    SELECT
      campaign.name,
      campaign.status,
      campaign_budget.amount_micros,
      metrics.cost_micros,
      campaign.serving_status,
      campaign.payment_mode
    FROM campaign
    WHERE campaign.status = 'ENABLED'
      AND segments.date DURING YESTERDAY
"""
# campaign.serving_status = 'BUDGET_CONSTRAINED' → limited by budget
# Use YESTERDAY (not TODAY) so spend reflects a full day, not mid-day partial
```

### Ad Status Check (Daily Sanity)

```python
query = """
    SELECT
      campaign.name,
      ad_group.name,
      ad_group_ad.ad.id,
      ad_group_ad.status,
      ad_group_ad.policy_summary.approval_status,
      ad_group_ad.policy_summary.review_status
    FROM ad_group_ad
    WHERE campaign.status = 'ENABLED'
      AND ad_group.status = 'ENABLED'
      AND ad_group_ad.status = 'ENABLED'
    ORDER BY campaign.name
"""
# Filter for approval_status != 'APPROVED' to find non-serving ads
```

---

## Campaign Classification (Brand / Generic / PMAX / Display)

Ironhack convention, confirmed with Pablo Gomez (paid media) on 2026-09-21. Channel is derived from the **campaign name**, evaluated in this order (implemented in `campaign_channel()` in `scripts/argos/performance_report.py`):

| Channel | Rule (case-insensitive substring of campaign name) | Example |
|---|---|---|
| **brand** | contains `brand` | `BER_Germany_Berlin_Global_Search_Brand_DE` |
| **pmax** | contains `pmax` (checked before generic — `Generic_PMAX` is PMAX) | `MAD_Spain_Madrid_Global_Search_Generic_PMAX` |
| **generic** | contains `generic` and not `pmax` | `AMS_Netherlands_Global_Search_Generic` |
| **display** | contains `display` or `youtube` | `AMS_Netherlands_Global_Display_Prospecting_DemGen_Youtube_EN` |

Fallback when the name matches nothing: `advertising_channel_type` PERFORMANCE_MAX → pmax, DISPLAY/VIDEO/DEMAND_GEN → display, SEARCH → generic, else `other`.

## Funnel Stages (primary conversion actions)

`metrics.conversions` only counts the primary conversion actions, which are the Zapier funnel stages named `Zapier <month> | <stage>`. The stage is the text after the last `|`:

| Stage | Meaning |
|---|---|
| `Apps` | Applications |
| `QApps` | Qualified applications |
| `TI` | Technical interview |
| `SA` | Student agreement |
| `BST` | Booked student |

Segment by `segments.conversion_action_name` (compatible with `segments.date` and `segments.device` at campaign / ad_group / keyword_view / ad_group_ad level, but **only with conversion metrics** — impressions/clicks/cost cannot be in the same query). Rows for non-primary actions (Syllabus, Financing requests, YouTube views…) come back with `conversions = 0` and `all_conversions > 0` — drop them. Summing the stages reproduces `metrics.conversions` exactly.

---

## Reporting Cadence (VP of Marketing spec)

| Cadence | Schedule | Cron job name | What |
|---|---|---|---|
| **Performance Report** | Mon + Thu (morning) | `argos-performance-report` | 3 timeframes (7d/14d/30d) × 4 levels (campaign/ad_group/keyword/ad), each entity with channel, funnel-stage split and device split; + auction insights (brand). Each timeframe compares current vs previous same-length period. Collector writes `/tmp/argos_perf_data.json` and prints a compact summary (see argos-reports skill). |
| **Daily Sanity Check** | Every day | `argos-daily-sanity` | All ads working, campaigns delivering, budget-limited campaigns (uses yesterday's spend, not today's partial) |

### Performance Report KPIs (all levels)

Each entity (campaign, ad group, keyword, ad) reports these KPIs with current period values and delta vs previous:

| KPI | Delta Direction |
|---|---|
| Impressions | ↑ = good |
| Clicks | ↑ = good |
| CTR | ↑ = good |
| CPC | ↓ = good |
| Conversions | ↑ = good |
| Cost/Conversions (CPA) | ↓ = good |
| Conversion Value | ↑ = good |
| ROAS | ↑ = good |

### CPA and ROAS formulas

```
CPA = cost / conversions
ROAS = conversions_value / cost   (or revenue / cost if tracking revenue)
```

**Only cost-prefixed metrics are in micros.** Divide `cost_micros` and `average_cpc` by `1_000_000` before displaying. `metrics.conversions_value` is already in the account's base currency unit — do NOT divide it by 1,000,000. Treating conversions_value as micros will divide your ROAS by 1,000,000 and produce nonsense (e.g. 0.00001x instead of 10x).

---

## Pitfalls

- **`cost_micros` is in millionths of the currency unit** — always divide by `1_000_000` before displaying. This applies to `cost_micros`, `average_cpc`, and any field with `_micros` suffix.
- **`conversions_value` is NOT in micros** — it returns the account's base currency directly. Do NOT divide it by 1,000,000. If you treat it like cost_micros, ROAS will be off by 6 orders of magnitude (0.00001x instead of 10x).
- **GA4 Data API quota**: 10 requests/second per property. Add sleep between requests in loops.
- **GSC data lag**: GSC data is typically 3–4 days delayed. Never query "yesterday" — query up to 4 days ago at earliest.
- **Google Ads standard vs basic access**: basic access limits API calls. If you see quota errors, check developer token's access level in the MCC.
- **MCC vs client account**: `login_customer_id` must be the MCC (manager) ID. `customer_id` in queries is the individual client account. Mixing them causes `AuthorizationError.USER_PERMISSION_DENIED`.
- **IS metrics not available at ad group level** — Impression Share is only available at campaign and account level.
- **Search terms only show terms above Google's threshold** — low-volume terms are suppressed. This is by design.
- **Service account must be added as a user in GSC property** — it's not enough to grant API access; the service account email must be added as "Verified owner" or "Restricted user" on each GSC property.
- **Multi-account loops**: when iterating over multiple `GADS_CUSTOMER_ID` values, catch `GoogleAdsException` per account so one failing account doesn't block the rest.
- **Cron scheduler stale-lock**: `cronjob action=run` can reject a manual run with "Already being fired by the scheduler" even when the job completed hours ago. Workaround: execute the script directly with `python3 <path-to-script>` and process the output yourself. This is common after a recent run and the scheduler hasn't cleared its guard yet.
- **Google Ads enum codes are opaque integers**: `campaign.serving_status`, `ad_group_ad.policy_summary.approval_status`, and `campaign.advertising_channel_type` return raw proto enum integers in API responses. See `references/gads-enum-codes.md` for the mapping of common values (SERVING=2, ENDED=4, APPROVED=3, SEARCH=2, DISPLAY=3, etc.).
