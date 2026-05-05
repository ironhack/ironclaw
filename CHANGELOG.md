# Changelog

Ops log for the IronClaw server. Most recent entry first.

---

## 2026-05-05 — SEO agent (ironclaw-seo) fully wired

**What**: Completed the ironclaw-seo (Optimizer) agent setup end-to-end.

**Workspace fixes:**
- Corrected Slack channel from `#ironclaw-optimizer` → `#ironclaw-seo` (ID: `C0B1MLM0L3X`) in TOOLS.md and AGENTS.md
- Added GitHub repos: `ironhack/foundry` and `ironhack/new-website-worker` (read + PR access)
- Added GSC property: `https://www.ironhack.com/` with country-dimension filtering for ES, PT, FR, NL, DE

**Credentials added to `gateway.systemd.env`:**
- `GITHUB_TOKEN` — fine-grained PAT, read access to both repos including PRs
- `GOOGLE_SA_KEY_PATH` — service account JSON at `/home/openclaw/.openclaw/gsc-service-account.json` (project `ironclaw-495411`)
- `GOOGLE_IMPERSONATE_EMAIL=rodolfo.puglia@ironhack.com` — domain-wide delegation target

**GSC auth setup:**
- Tried service account direct → GSC UI rejected the email (Workspace org policy)
- Set up domain-wide delegation: GCP service account client ID `117678558143014238882`, Workspace Admin authorized scope `webmasters.readonly`
- Tested live: GSC API returning real data (ES: 822 clicks / 113K impressions; FR: 659 / 126K; DE: 423 / 76K for week of Apr 21-27)

**Cron chain (3 jobs, daily):**
| Job | ID | Schedule | Status |
|---|---|---|---|
| SEO: Daily GSC Snapshot | `39031b84` | 06:00 daily Rome | enabled, triggers next |
| SEO: Daily Research Journal | `4289a69c` | disabled | triggered by Job 1 |
| SEO: Repo Audit + Daily Brief | `6c85765e` | disabled | triggered by Job 2, posts to #ironclaw-seo |

Chain flow: Job 1 pulls GSC data + saves snapshot → Job 2 searches web for SEO/GEO news + updates journal → Job 3 audits GitHub PRs, correlates with rankings, posts daily brief.

**Old "Weekly SEO Report" cron job still active** — review and remove if redundant.

**Still open:**
- Firecrawl API key still PLACEHOLDER in `gateway.systemd.env`

---

## 2026-05-05 — AWS CLI installed + S3 credentials restored

**What**: AWS credentials were in `/home/openclaw/.openclaw/.env` but not copied to `gateway.systemd.env` during migration — bot couldn't reach S3. Fixed by adding `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` to `gateway.systemd.env`. Installed AWS CLI v2 (official installer, Ubuntu 24.04 apt package not available). Fixed stale Docker paths in `workspace/TOOLS.md` (`/home/node/` → `/home/openclaw/`). S3 bucket `ih-ironclaw` (eu-west-1) confirmed accessible.

---

## 2026-05-05 — Tavily + DuckDuckGo search enabled

**What**: Set Tavily API key in `gateway.systemd.env` (replaces PLACEHOLDER). Also enabled DuckDuckGo plugin as fallback. Gateway restarted.

---

## 2026-05-05 — Multi-agent architecture finalized + #ironclaw-watch context

**What**: Settled on 3-agent design: ironclaw (router + competitive intel), ironclaw-seo, ironclaw-edu. Added per-channel `systemPrompt` to `#ironclaw-watch` (C0B1MM39P8D) so ironclaw automatically frames conversations there as competitive analysis across ES/PT/FR/NL/DE. Uses OpenClaw's `channels.slack.channels[id].systemPrompt` field. Channel binding stays: ironclaw-watch → ironclaw agent (chat + cron delivery).

---

## 2026-05-05 — Telegram removed

**What**: Disabled Telegram channel (`channels.telegram.enabled: false`) and removed its binding. Gateway now runs 7 plugins (was 8). Slack is the only active channel.

---

## 2026-05-05 — Slack channel bindings finalized

**What**: Finalized Slack channel routing. Removed catch-all binding (was routing all channels including delivery-only ones to ironclaw). Added explicit binding for `#ironclaw-watch` (C0B1MM39P8D) → ironclaw agent, so it supports both interactive chat and cron digest delivery. Final bindings:
- `#ironclaw-watch` → ironclaw (chat + cron delivery)
- `#ironclaw-seo` → ironclaw-seo
- `#ironclaw-edu` → ironclaw-edu
- DMs → ironclaw (via pairing, no binding needed)

Also added `channels.slack.channels: { "*": { requireMention: false } }` so channels respond to all messages without needing @mention.

---

## 2026-05-05 — Slack channel messages enabled (requireMention: false)

**What**: OpenClaw's Slack plugin defaults to `requireMention: true` in channels, silently dropping all non-mention messages. Added `channels.slack.channels: { "*": { requireMention: false } }` to `openclaw.json` so the bot responds to all messages in channels it belongs to, without needing an @mention. Gateway restarted.

---

## 2026-05-05 — Slack routing: DM binding + Rudy pairing

**What**: Replaced the `#ironclaw` channel binding with a catch-all Slack binding (no `accountId`), so DMs from any paired user route to the ironclaw agent. `#ironclaw-seo` and `#ironclaw-edu` channel bindings remain and take priority. Rudy's Slack account (`U02MV9VPGV6`) approved and set as command owner via `openclaw pairing approve slack WSVMMXHJ`. Gateway restarted, socket mode reconnected.

---

## 2026-05-05 — Slack app recreated, tokens updated

**What**: Slack app was recreated (new App ID: `A0B19LV97DM`, previous: `A0B1NSXT18W`). Updated `SLACK_BOT_TOKEN` and `SLACK_APP_TOKEN` in `gateway.systemd.env` on the server. Restarted `openclaw-gateway` (user systemd service). Slack socket mode confirmed connected. Channels unchanged.

---

## 2026-05-05 — Docker → bare-metal migration + multi-agent expansion

**What**: Replaced Docker setup with a bare-metal systemd install. Expanded from one agent to three. Upgraded search provider. Registered 3 cron jobs.

**Migration steps completed:**
- Backed up live data from running container via `docker cp` to `/home/openclaw/openclaw-backup-20260505`
- Moved data dir from `/root/.openclaw` (root-owned, Docker) to `/home/openclaw/.openclaw` (openclaw-user-owned, bare-metal)
- Installed Node.js 24 via NodeSource PPA
- Installed `openclaw@2026.5.4` globally via npm (upgraded from Docker version 2026.3.30)
- Installed gateway as a user systemd service (`openclaw-gateway.service`), enabled linger for boot persistence
- Stopped Docker containers (`openclaw-openclaw-gateway-1`, `openclaw-openclaw-cli-1`) — both removed
- Removed Docker image `openclaw:local`
- Fixed `OPENAI_API_KEU` typo in env — now correctly `OPENAI_API_KEY`

**Config changes (`openclaw.json`):**
- Fixed workspace path (was Docker-internal `/home/node/...`, now `/home/openclaw/.openclaw/workspace`)
- Added `agents.list` with three named agents: `ironclaw` (default), `optimizer`, `education`
- Added `bindings` routing Telegram → ironclaw, Slack channels → respective agents (channel IDs are PLACEHOLDER pending Slack app setup)
- Switched web search provider: `duckduckgo` → `tavily`
- Added Firecrawl for web fetch (bypasses bot blockers)
- Added Slack channel config (tokens pending)
- Renamed agent dir `main` → `ironclaw`

**Cron jobs registered:**
| Job | Agent | Schedule | ID |
|---|---|---|---|
| Weekly Competitor Watch | ironclaw | Mon 07:00 Rome | `2f2508cc` |
| Weekly SEO Report | ironclaw-seo | Mon 08:00 Rome | `ee6d4f9e` |
| Course Content Review Loop | ironclaw-edu | Daily 06:00 Rome | `2d5e3786` |

**Pending (blocked by missing credentials/setup):**
- Workspace files for optimizer and education agents: written locally in `server/`, deploy with `./scripts/deploy-workspaces.sh` once classifier allows rsync
- Slack app setup: create at api.slack.com, fill `SLACK_BOT_TOKEN` + `SLACK_APP_TOKEN` in `gateway.systemd.env`
- Slack channel IDs: replace `PLACEHOLDER_*_CHANNEL_ID` in `openclaw.json` bindings and cron job delivery targets
- Tavily API key: replace PLACEHOLDER in `gateway.systemd.env`
- Firecrawl API key: replace PLACEHOLDER in `gateway.systemd.env`
- Composio API key + OAuth: for Google Search Console MCP (Optimizer agent)
- Device re-pairing: run `openclaw pair` to re-pair control UI and any other clients
- Education agent: set course repo + populate `review-queue.json` before enabling cron

---

## 2026-05-05 — Initial audit

**What**: First exploration of the server. No changes made.

**Found**:
- OpenClaw 2026.3.30 running on Ubuntu 24.04 (`openclaw-ironhack`) via Docker Compose
- Gateway container healthy (ports 18789-18790); CLI container dead since initial deploy (2026-04-01, exit code 1)
- Primary model: ZAI/GLM-5-turbo with GLM-4.7 fallback
- Telegram channel active; DuckDuckGo search; AWS + GitHub access configured
- Custom workspace with full IronClaw persona (SOUL.md, IDENTITY.md, MEMORY.md) and two custom skills: `course-reviewer`, `competitor-watch`
- Bug: `.env` has `OPENAI_API_KEU` typo — should be `OPENAI_API_KEY`

**Decision**: Replace Docker with a bare-metal systemd install. See README.md for migration checklist.

**Committed**: `README.md` with full server documentation.
