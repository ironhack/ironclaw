# CLAUDE.md — IronClaw repo guide

This repo is the source of truth for IronClaw's configuration, infrastructure decisions, and ops history. The actual running system is on a remote server (`openclaw-server`). This repo does NOT auto-deploy — Rudy commits and pushes manually.

---

## What this repo is for

- **CHANGELOG.md** — ops log of every server session. Update at the end of every session, most recent first.
- **README.md** — current state of the server. Keep it accurate after any structural change.
- **server/** — workspace files for ironclaw-seo, ironclaw-edu, and ironclaw-jobs agents, ready to deploy.
- **slack-app/manifest.json** — Slack app manifest. Update if scopes or events change.
- **scripts/deploy-workspaces.sh** — rsync the `server/workspace-*` dirs to the server.

## What this repo is NOT for

- The ironclaw (main) agent's workspace lives entirely on the server (`/home/openclaw/.openclaw/workspace/`). Edit it directly over SSH, not here.
- Secrets are never committed. They live in `gateway.systemd.env` and `.env` on the server.

---

## How to work on the server

```bash
ssh openclaw-server
systemctl --user restart openclaw-gateway   # after config changes
journalctl --user -u openclaw-gateway -n 50 # logs
openclaw sessions --all-agents --active 60  # recent sessions
```

Config file: `/home/openclaw/.openclaw/openclaw.json`
Secrets: `/home/openclaw/.openclaw/gateway.systemd.env`
Sudo password: in memory (`reference_server_access.md`)

## Agent workspace paths (on server)

| Agent | Workspace |
|---|---|
| ironclaw | `/home/openclaw/.openclaw/workspace/` |
| ironclaw-seo | `/home/openclaw/.openclaw/workspace-ironclaw-seo/` |
| ironclaw-edu | `/home/openclaw/.openclaw/workspace-ironclaw-edu/` |
| ironclaw-jobs | `/home/openclaw/.openclaw/workspace-ironclaw-jobs/` |

---

## Current priorities / open work

1. **Firecrawl API key** — still PLACEHOLDER in `gateway.systemd.env`. Get from firecrawl.dev, then `sed -i` and restart gateway.
2. **Education agent bootstrap** — populate `review-queue.json` on the server before enabling the daily cron.
3. **Composio + GSC** — SEO agent needs Google Search Console access via Composio.
4. **S3 bucket policy** — add `jobs/*` to the `ih-ironclaw` bucket's public-read policy (via AWS console; IAM user lacks `s3:GetBucketPolicy`). Add `arn:aws:s3:::ih-ironclaw/jobs/*` alongside existing `seo/*`, `edu/*`, `ironclaw/*`, `watch/*`.

---

## Architecture decisions (why things are the way they are)

- **4 agents**: ironclaw (router + competitive intelligence), ironclaw-seo (SEO analyst), ironclaw-edu (curriculum QA), ironclaw-jobs (German job market research for caseworker reports).
- **`#ironclaw-watch` is both delivery and chat**: the weekly cron digest posts there AND Rudy can chat with ironclaw there. A channel-level `systemPrompt` in `openclaw.json` primes ironclaw to expect competitive questions from that channel.
- **No Telegram**: removed 2026-05-05. Slack only.
- **`requireMention: false` for all Slack channels**: default OpenClaw behavior requires @mention in channels. Disabled so the bot responds to all messages in its channels.
- **DMs via pairing, not binding**: ironclaw responds to Rudy's DMs via the pairing mechanism (command owner), not a catch-all binding. This avoids the bot responding to everyone's DMs.
- **Bare-metal over Docker**: Docker CLI container was broken from day 1. Bare-metal systemd is simpler and more maintainable.

---

## Slack app

- App ID: `A0B19LV97DM` (recreated 2026-05-05; previous was `A0B1NSXT18W`)
- Bot user: `ironclaw2` / `U0B1JP65HJ7`
- Manifest: `slack-app/manifest.json`
- Socket Mode — no public URL needed
- Command owner (paired): Rudy `U02MV9VPGV6`

Channel IDs:
| Channel | ID |
|---|---|
| `#ironclaw-watch` | `C0B1MM39P8D` |
| `#ironclaw-seo` | `C0B1MLM0L3X` |
| `#ironclaw-edu` | `C0B1R3DKJBU` |
| `#ironclaw-jobs` | `C0B1KDU4Q8P` |
