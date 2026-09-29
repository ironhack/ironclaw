# Cron Job Delivery & Profile Behavior

## Cross-profile cron jobs don't work as expected

When creating cron jobs under a dedicated profile (`hermes -p scout cron create`), those jobs are stored in `~/.hermes/profiles/<name>/cron/jobs.json`. However, the Hermes gateway only handles cron jobs from its own profile. A default-profile gateway does NOT scan other profiles' cron directories.

**Lesson:** Create cron jobs in the same profile whose gateway is running.

## Workaround: model override on per-job basis

If you want a different model for cron jobs than the default profile, use the `model` parameter on each cron job instead of creating a separate profile:

```
cronjob(action='create', model={model: 'deepseek-v4-flash', provider: 'deepseek'}, ...)
```

This pins the model at creation time and achieves cost optimization without needing a second gateway process.

## Slack delivery

For cron jobs to deliver to Slack, two things must be configured:

1. **Slack platform enabled**: `hermes config set platforms.slack.enabled true` + gateway restart
2. **Deliver parameter**: `deliver='slack:C0B1KDU4Q8P'` (channel ID, not channel name)

The `SLACK_BOT_TOKEN` must be in `~/.hermes/.env` (or the profile's `.env`).

Cron jobs default to `deliver='local'` if not specified — this means the output stays local and is NOT sent to Slack. Always set `deliver` explicitly for Slack-facing jobs.

## Template porting from OpenClaw

When porting agents from OpenClaw to Hermes:
- HTML templates can be extracted from `.md` wrapper files into plain `.html` files in a skill's `templates/` directory
- The DB path stays the same — no migration needed, just reference the absolute path
- Python helpers (report generation, DB queries) go in `templates/` as `.py` files
- Logo/base64 assets reference the original workspace path

## OpenClaw cron disable

To disable an OpenClaw cron job: `openclaw cron disable <uuid>` (not `pause`).
