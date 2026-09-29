# ironclaw

Ironhack's internal agents ("IronClaw"): scheduled intelligence pipelines that post to Slack and publish
HTML reports. Since June 2026 they run on **Hermes Agent** on the `openclaw-server` VPS; the original
OpenClaw setup was removed on 2026-09-25 (see `archive/openclaw/`).

This repo is the **ops log and documentation**, plus a **mirror of the live code** (`server/hermes/`,
pulled with `scripts/sync-from-server.sh`). The server is the source of truth for code; secrets never
leave it.

## Quick reference

```bash
ssh openclaw-server                                  # user openclaw, 4 cores / 8 GB, Ubuntu
systemctl --user list-units 'hermes-*'               # one gateway per profile
HERMES="HERMES_HOME=$HOME/.hermes $HOME/.hermes/hermes-agent/venv/bin/python -m hermes_cli.main"
cd ~/.hermes && eval $HERMES cron list                # default profile jobs
cd ~/.hermes/profiles/argos && HERMES_HOME=$PWD ~/.hermes/hermes-agent/venv/bin/python -m hermes_cli.main --profile argos cron list
eval $HERMES cron run <job_id>                       # queue a job on the next scheduler tick
```

Data home for all pipelines: **`/home/openclaw/ironclaw-data/`** (`~/.openclaw` is a compatibility symlink).

## Profiles (one Hermes gateway each)

| Profile | Persona | Model | Slack home | Purpose |
|---|---|---|---|---|
| default | Hermes / "Optimizer" in #ironclaw-seo | deepseek-v4-pro | `C0BBCLM27FZ` (free-response in #ironclaw-seo, #ironclaw-jobs) | SEO assessment, competitor watch, job-market Scout |
| argos | Argos | deepseek-v4-pro | #argos-home `C0BFMA3117F` | Google Ads / GA4 / GSC intelligence |
| helios | Helios | deepseek-v4-pro | `C0BCJF82PMF` | Hermes infrastructure maintainer |
| athena | Athena | deepseek-chat | `C0BCBAJUPGT` | Course content work |
| talos | Talos | deepseek-v4-pro | Telegram | Autonomous ops agent |

Each profile has its own Slack app / bot token in its `.env`. Channels: #ironclaw-seo `C0B1MLM0L3X`,
#ironclaw-watch `C0B1MM39P8D`, #ironclaw-jobs `C0B1KDU4Q8P`, #argos-home `C0BFMA3117F`.

## Pipelines

Times in Rome (CET/CEST); cron expressions are UTC, see `server/hermes/cron-jobs.md` for the exact table.

| Pipeline | When | Jobs | Output |
|---|---|---|---|
| **SEO assessment** (Optimizer) | Mon + Thu 12:00 fetch, 14:00 post | `SEO: Data Fetch` (script) → `SEO: Intel & Audit` (agent) | Block Kit post in #ironclaw-seo + `…/seo/DATE/report.html` (preview `seo/preview/`) |
| **Competitor watch** | Mon 11:00 fetch, 14:00 post | `Weekly Watch: Fetch` (script) → `Weekly Watch: Report` (agent) | Post in #ironclaw-watch + `…/watch/DATE/competitor-watch-report.html` (`watch/latest/`) |
| **Google Ads performance** (Argos) | Mon + Thu 10:00 | `argos-performance-report` (script + agent) | Post in #argos-home + `…/ironclaw/argos/shared/performance.html` |
| **Google Ads daily sanity** (Argos) | daily 09:00 | `argos-daily-sanity` (script + agent, v2 since 2026-09-29) | Post in #argos-home + `…/ironclaw/argos/shared/sanity.html`; issue state in `ironclaw-data/argos/sanity-state.json` |
| **Job-market Scout** | Wed 12:00-16:00 | `Scout: Staleness Check` → `Weekly Scrape A/B` → `Report Generation` (scripts) | `…/jobs/` reports |
| Helios update watcher | daily 11:00 | agent | origin channel |

Paused 2026-09-25: `SEO: WD Monitor`, `SEO: UX Monitor` (folded into the SEO assessment).

Reports are public-read on S3 `ih-ironclaw` (eu-west-1) under the prefixes `seo/`, `watch/`, `jobs/`,
`ironclaw/`, `argos/`, `helios/`, base URL `https://ih-ironclaw.s3.eu-west-1.amazonaws.com/`.

### How the pipelines are built (since 2026-09-25)

Scripts own the data and the numbers; the model only reads and writes narrative. Each pipeline has:

- a **fetch/prepare script** (no_agent cron job) that pulls data, pre-computes everything and prints a
  digest the agent job reads;
- **deterministic state** on disk (`ironclaw-data/...`): SEO backlog with fix outcomes, competitor state +
  change log, GSC/GA4 snapshots, Google Ads datasets;
- a **generator** that renders the HTML report and the Block Kit Slack post (headline, status scorecard,
  verified changes / outcomes, actions, buttons; details in a thread) and posts it itself. Agent jobs
  deliver `local` and alert the channel only on failure, so there is one post per run.

Per-pipeline details live in the skill folders (`server/hermes/skills/*/SKILL.md`, `argos/skills/*`).

## Server layout

```
/home/openclaw/
  .hermes/                      Hermes home (default profile): config.yaml, .env, cron/jobs.json, skills/, scripts/
    hermes-agent/               Hermes source + venv (python 3.11; camoufox installed here)
    profiles/{argos,helios,athena,talos,scout}/   per-profile config, .env, cron, skills, scripts
    skills/ironhack/{ironclaw-seo,job-market-scout}/  , skills/openclaw-imports/competitor-watch/
    scripts/                    no_agent cron scripts (seo-data-fetch.sh, competitor-watch-fetch.sh, scout-*.py)
  ironclaw-data/                pipeline data (was ~/.openclaw)
    workspace-ironclaw-seo/     memory/ (GSC/GA4 snapshots, seo-data-DATE.json), seo-backlog.json, seo-journal.md
    workspace/competitor-snapshots/DATE/   raw competitor captures
    workspace/competitor-watch/            state/, changes.jsonl, extractions/, prepared/, sitemaps/
    workspace-ironclaw-jobs/    Scout: jobs.db, logo.b64 (also used by Argos reports)
    gsc-service-account.json, .env
  archive/                      OpenClaw software + state tarballs (2026-09-25)
  caddy/, camofox-browser/      HTTPS for the Hermes dashboard; anti-detection browser API
```

## Repo layout

```
README.md            this file (current state)
CLAUDE.md            how to work in this repo / on the server
CHANGELOG.md         ops log, most recent first — update after every server session
scripts/sync-from-server.sh   pull live scripts, skills and the cron inventory into server/hermes/
server/hermes/       mirror of the live code (scripts/, skills/, argos/, cron-jobs.md) — never edit here, edit on the server and re-sync
archive/openclaw/    the OpenClaw-era workspaces, deploy script and Slack app (history only)
```

## Secrets (never committed)

`~/.hermes/.env` and `~/.hermes/profiles/*/.env` on the server: DeepSeek keys, Slack bot/app tokens per
profile, Google service account JSON, Google Ads developer token and customer IDs, AWS keys, GitHub PAT.
`ironclaw-data/gsc-service-account.json` for the SEO scripts.

## Pending

- Uninstall the dead OpenClaw Slack app `ironclaw2` (A0B19LV97DM) from the workspace.
- Drop the `~/.openclaw` symlink after a couple of clean Monday runs.
- Competitor watchlist: only Le Wagon and Liora cover more than one market; no PT/NL-specific competitor.
- Liora `formations` URL in the watch fetch list captures a blog article, not the catalog.
- 4geeks.com crashes the headless browser; captures stay partial.
- neuefische.de blocked the VPS after heavy scraping on 2026-09-28 (recovered within hours); tracked pages cut 19 → 10. If it recurs, that site needs a lighter fetch or another egress.
- Hermes gateways (argos, helios, athena) can get stuck in a Slack socket-mode reconnect loop (`Session is closed`); cron still runs but mentions go unanswered. Fix: `systemctl --user restart hermes-gateway-<profile>`. Consider a journal-check timer.
- Watch digest should print the tracked page count per competitor (the model misread the 10-page neue fische list as a timeout on 2026-09-28).
