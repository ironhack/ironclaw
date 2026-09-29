# SEO Cron Setup Reference

## Pipeline v2 (2026-09-25)

Job 1 pre-computes everything (data, signals, outcomes, live check, news) and prints a digest; Job 2 (context_from Job 1) writes the narrative, builds the report with `seo-build-report.py` and posts to Slack. Job 2's prompt is in `cron-prompt-v2.txt` next to this file. `cron.script_timeout_seconds` is 600 on the default profile (fetch takes ~4 min).

## Job IDs (as of 2026-06-19, unchanged)

| Job ID | Name | Schedule | Type | Deliver |
|--------|------|----------|------|---------|
| `3472abb11b86` | SEO: Data Fetch | `0 10 * * 1,4` | no_agent | silent |
| `0c0c1fddcd38` | SEO: Intel & Audit | `0 12 * * 1,4` | LLM (deepseek-v4-pro) | slack:C0B1MLM0L3X |
| `15a123239d81` | SEO: UX Monitor | `30 14 * * 2` | no_agent | paused 2026-09-25 (folded into the weekly assessment) |
| `fa35fc5c66f3` | SEO: WD Monitor | `30 14 * * 2` | no_agent | paused 2026-09-25 (folded into the weekly assessment) |

## Script paths

- Data fetch: `~/.hermes/scripts/seo-data-fetch.sh`
- WD monitor: `~/.hermes/scripts/seo-wd-monitor.sh`

## Slack config

Channel: `#ironclaw-seo` (C0B1MLM0L3X)

All three config sections must match (`hermes config set`):
```
slack.free_response_channels: "C0B1KDU4Q8P,C0B1MLM0L3X"
platforms.slack.free_response_channels: "C0B1KDU4Q8P,C0B1MLM0L3X"
platforms.slack.extra.free_response_channels: "C0B1KDU4Q8P,C0B1MLM0L3X"
```

Channel prompts (all three sections):
```
slack.channel_prompts.C0B1MLM0L3X: "You are Optimizer, Ironhack's SEO and organic growth analyst. Load the ironclaw-seo skill..."
platforms.slack.channel_prompts.C0B1MLM0L3X: "..."
platforms.slack.extra.channel_prompts.C0B1MLM0L3X: "..."
```

## Env vars

```
GOOGLE_SA_KEY_PATH=/home/openclaw/ironclaw-data/gsc-service-account.json
```

## Workspace

```
/home/openclaw/ironclaw-data/workspace-ironclaw-seo/
```

## Data sources

- GSC: service account `ironclaw-seo@ironclaw-495411.iam.gserviceaccount.com`, impersonates `rodolfo.puglia@ironhack.com`
- GA4: same service account, property `256164398`, Analytics Data API v1beta
- GitHub: `rudyironhack` (admin on ironhack/foundry and ironhack/new-website-worker)
