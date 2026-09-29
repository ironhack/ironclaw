# Redirect Monitor — Track Extension

## How to add a new track (e.g., UX)

1. **Build the redirect map** at `references/<track>-redirect-map.json`:
```json
{
  "sources": [
    {
      "url": "https://www.ironhack.com/es/diseno-ux-ui/madrid",
      "country": "Spain",
      "language": "ES",
      "type": "Location",
      "destination": "https://www.ironhack.com/es/diseno-ux-ui"
    }
  ],
  "destinations": [
    {
      "url": "https://www.ironhack.com/es/diseno-ux-ui",
      "country": "Spain",
      "language": "ES"
    }
  ]
}
```

Source types: `Remote` (for /remote, /remoto, /a-distance) or `Location` (for city names).

2. **Create a cron wrapper** at `~/.hermes/scripts/seo-<track>-monitor.sh`:
```bash
#!/bin/bash
exec /home/openclaw/.hermes/scripts/seo-wd-monitor.sh <track>
```

3. **Create the cron job**:
```
cronjob(action="create", name="SEO: UX Monitor", schedule="30 14 * * 2",
  script="seo-ux-monitor.sh", no_agent=true, deliver="slack:C0B1MLM0L3X")
```

## How it works

`seo-wd-monitor.sh` runs with `TRACK=<track>`:
- Copies `references/<track>-redirect-map.json` to `scripts/wd-redirect-map.json` (the Python script hardcodes this filename)
- Uses `$WORKSPACE/<track>-monitor/` for snapshots and S3 path
- First run: baseline report (no previous snapshot to compare)
- Subsequent runs: WoW comparison with deltas

## Python 3.11 compat

`wd-report.py` uses f-strings with backslash-escaped quotes (`<span class=\\'zero\\'>`). This fails on Python < 3.12. Fix: extract string literals into variables before using in f-strings.

## Live redirects

| Track | Status |
|-------|--------|
| WD | 25/25 OK — all redirects healthy, source impressions at 0 |
| UX | 0/25 — redirects not yet deployed, pages return 200 |
