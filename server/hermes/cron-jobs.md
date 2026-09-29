# Hermes cron jobs (exported by scripts/sync-from-server.sh)

| Profile | ID | Name | Schedule (UTC) | Type | Script | Deliver | Failure → | Enabled |
|---|---|---|---|---|---|---|---|---|
| default | 0f3b5313c9e1 | Scout: Staleness Check | 0 10 * * 3 | script | scout-staleness.py | local |  | yes |
| default | 5036ca814356 | Scout: Weekly Scrape (Part A — bootcamps 1-6) | 0 12 * * 3 | script | scout-scrape-a.py | local |  | yes |
| default | 2a8f5a32731f | Scout: Report Generation | 0 14 * * 3 | script | scout-report.py | local |  | yes |
| default | 3472abb11b86 | SEO: Data Fetch | 0 10 * * 1,4 | script | seo-data-fetch.sh |  |  | yes |
| default | 0c0c1fddcd38 | SEO: Intel & Audit | 0 12 * * 1,4 | agent |  | local | slack:C0B1MLM0L3X | yes |
| default | fa35fc5c66f3 | SEO: WD Monitor | 30 14 * * 2 | script | seo-wd-monitor.sh | slack:C0B1MLM0L3X |  | PAUSED |
| default | 545d0f187758 | Weekly Watch: Fetch | 0 9 * * 1 | script | competitor-watch-fetch.sh | local | slack:C0B1MM39P8D | yes |
| default | 77bf232bfcb5 | Weekly Watch: Report | 0 12 * * 1 | agent |  | local | slack:C0B1MM39P8D | yes |
| default | 15a123239d81 | SEO: UX Monitor | 30 14 * * 2 | script | seo-ux-monitor.sh | slack:C0B1MLM0L3X |  | PAUSED |
| default | 5319d2302a09 | Scout: Weekly Scrape (Part B — bootcamps 7-12) | 0 13 * * 3 | script | scout-scrape-b.py | local |  | yes |
| argos | de090919d14d | argos-daily-sanity | 0 7 * * * | agent | argos/sanity_check.py | local | slack:C0BFMA3117F | yes |
| argos | f69227a6569b | argos-performance-report | 0 8 * * 1,4 | agent | argos/performance_report.py | local | slack:C0BFMA3117F | yes |
| helios | 47d19ca8ab32 | Hermes update/news watcher | 0 9 * * * | agent |  | origin |  | yes |

Prompts of agent jobs live in the skill folders (references/cron-prompt-v2.txt) and in the job store on the server.
