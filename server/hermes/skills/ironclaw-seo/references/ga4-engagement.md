# GA4 Engagement Data

## Access Setup

Service account: `ironclaw-seo@ironclaw-495411.iam.gserviceaccount.com`
Impersonation: `rodolfo.puglia@ironhack.com`
Property ID: `256164398`

### What needed to be enabled (one-time)

1. **Domain-wide delegation scope** — Google Workspace Admin → Security → API Controls → Domain-wide Delegation → add `https://www.googleapis.com/auth/analytics.readonly` for client ID `117678558143014238882`

2. **Analytics Data API** — enabled in GCP project `727593458652`

3. **No GA4 property-level access needed** — impersonation handles it

## Key Data Points

### Country names
GA4 uses FULL country names (not ISO codes):
- Germany, Spain, France, Netherlands, Portugal

GSC uses ISO3: esp, fra, deu, prt, nld

### Engagement Rate
Computed as `1 - bounceRate` or use `engagementRate` metric directly.
As of June 2026:
- FR: 48.8% — highest, consistent with no AI Overviews
- NL: 36.4%
- ES: 34.9%
- PT: 30.0%
- DE: 27.5% — lowest despite highest traffic (AIO lookers)

This cross-validates GSC findings: AI Overviews drive high-impression, low-intent traffic that bounces.

### Organic Share
Filter to `sessionDefaultChannelGroup = Organic Search`.
- FR: 29.3% organic (regulatory AIO blockage)
- DE: 8.5% organic (AIO absorption)

### New vs Returning
Available via dimension `newVsReturning`. DE gets 4,983 new visitors/week (highest), FR 1,248 (lowest) but FR engagement is double.

## Script

See `scripts/ga4-query.py`. Usage:
```bash
python3 ga4-query.py <start> <end>              # all channels
python3 ga4-query.py <start> <end> --organic-only  # organic only
```

Output: JSON per-market with sessions, activeUsers, screenPageViews, bounceRate, avgSessionDuration.
