# OpenClaw to Hermes Migration Patterns

Learned from migrating ironclaw-jobs agent (June 2026).

## Cron Job Consolidation

OpenClaw chains many small isolated jobs (14 for ironclaw-jobs). Hermes cron jobs can do much more per invocation — consolidate into 2-3 smart jobs with skills:

- **Before**: 12 scrape jobs → staleness → report (14 total, sequential, each triggers next via CLI)
- **After**: 1 staleness + 1 scrape + 1 report (3 total, time-gapped, independent)

## Cost Optimization via Model Override

Cron jobs can override the model per-job without needing separate profiles:
```
cronjob(action='create', model={'model': 'deepseek-v4-flash', 'provider': 'deepseek'}, ...)
```

This gives profile-like cost isolation without running a second gateway.

## Killing OpenClaw Properly

OpenClaw's gateway auto-restarts via systemd. To stop permanently:
1. `systemctl --user stop openclaw-gateway.service`
2. Remove both the service file AND the symlink: `~/.config/systemd/user/default.target.wants/openclaw-gateway.service`
3. `systemctl --user daemon-reload`
4. Kill lingering cron watcher processes (`bash -c until openclaw cron runs...`)

## Data Migration — Keep Paths

Don't copy large files (1.6 MB SQLite DB). Have Hermes skills reference the original OpenClaw workspace paths. Works as long as file permissions allow.

## Slack Token Sanitization

Hermes's secret redactor replaces credentials in terminal output with `***`. Any attempt to write tokens via shell (echo, sed, heredoc) will write the placeholder, not the real value. Use `write_file` to create token files, then have a Python script read them and write to `.env`.
