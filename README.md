# ironclaw

Configuration and infrastructure for **IronClaw**, Ironhack's internal AI assistant running on a self-hosted [OpenClaw](https://github.com/openclaw/openclaw) server.

---

## Quick reference

| Item | Value |
|---|---|
| SSH alias | `openclaw-server` |
| Server hostname | `openclaw-ironhack` |
| OS | Ubuntu 24.04.4 LTS |
| OpenClaw version | 2026.5.4 |
| Gateway port | 18789 |
| Service | `openclaw-gateway.service` (user systemd, `openclaw` user) |

**Useful commands:**
```bash
systemctl --user status openclaw-gateway
systemctl --user restart openclaw-gateway
journalctl --user -u openclaw-gateway -n 50
openclaw sessions --all-agents --active 60
```

---

## Agents

Three agents, all running in the same gateway process:

| Agent | Channel | Purpose |
|---|---|---|
| `ironclaw` | DMs + `#ironclaw-watch` | Router, leadership ops, competitive intelligence |
| `ironclaw-seo` | `#ironclaw-seo` | SEO analyst |
| `ironclaw-edu` | `#ironclaw-edu` | Education content QA |

- **`#ironclaw-watch`** routes to `ironclaw` with a channel-level system prompt that primes it for competitive analysis. Also receives the Monday 07:00 Rome cron digest.
- DMs go to `ironclaw` via pairing (no binding needed). Command owner: Rudy (`slack:U02MV9VPGV6`).

Workspace files live in `server/workspace-ironclaw-*/` in this repo. Deploy with `./scripts/deploy-workspaces.sh`.

---

## Cron jobs

| Job | Agent | Schedule | Delivery |
|---|---|---|---|
| Weekly Competitor Watch | ironclaw | Mon 07:00 Rome | `#ironclaw-watch` |
| Weekly SEO Report | ironclaw-seo | Mon 08:00 Rome | `#ironclaw-seo` |
| Course Content Review | ironclaw-edu | Daily 06:00 Rome | `#ironclaw-edu` |

---

## Server layout

```
/home/openclaw/.openclaw/
  openclaw.json               # Main config (agents, bindings, channels, plugins)
  gateway.systemd.env         # All secrets (loaded by systemd)
  .env                        # Legacy secrets file (AWS keys; keep in sync)
  agents/
    ironclaw/
      agent/                  # Auth profiles, model overrides
      sessions/               # Session history
    ironclaw-seo/
    ironclaw-edu/
  workspace/                  # ironclaw agent workspace
    SOUL.md                   # Core persona
    AGENTS.md                 # Session startup rules
    TOOLS.md                  # Environment-specific notes (Playwright, S3)
    MEMORY.md                 # Long-term curated memory
    USER.md                   # User profile
    COMPETITORS.md            # Competitor tracking list
    skills/
      competitor-watch/       # Competitor scan + report skill
      course-reviewer/        # Course QA skill
    competitor-snapshots/     # Weekly JSON snapshots (delta source)
    memory/                   # Daily session logs
  workspace-ironclaw-seo/     # ironclaw-seo workspace (deploy from repo)
  workspace-ironclaw-edu/     # ironclaw-edu workspace (deploy from repo)
  cron/
    jobs.json                 # Cron job definitions
  credentials/                # Channel credentials (pairing, allowlists)
```

---

## Stack

| Component | Detail |
|---|---|
| Model | ZAI GLM-5.1 (thinking=medium) + GLM-5-turbo / GLM-4.7 fallbacks |
| Memory | OpenAI embeddings (vector search) |
| Search | Tavily (primary) + DuckDuckGo (fallback) |
| Web fetch | Firecrawl (key pending) |
| Browser | Playwright-core + Chromium 1217 (`/home/openclaw/.cache/ms-playwright/`) |
| S3 | `ih-ironclaw` bucket, eu-west-1 |
| Slack | Socket Mode, App ID `A0B19LV97DM` |
| Telegram | Disabled |

---

## Secrets (not committed)

All secrets in `/home/openclaw/.openclaw/gateway.systemd.env`:

| Variable | Status |
|---|---|
| `OPENCLAW_GATEWAY_TOKEN` | Set |
| `OPENAI_API_KEY` | Set (used for memory embeddings) |
| `SLACK_BOT_TOKEN` / `SLACK_APP_TOKEN` | Set (App `A0B19LV97DM`) |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | Set |
| `AWS_DEFAULT_REGION` | `eu-west-1` |
| `TAVILY_API_KEY` | Set |
| `FIRECRAWL_API_KEY` | **PLACEHOLDER** — get from firecrawl.dev |
| `COMPOSIO_API_KEY` | **PLACEHOLDER** — needed for GSC integration |
| `GOG_KEYRING_PASSWORD` | Set |

---

## Pending

- [ ] **Deploy SEO + EDU workspaces** — run `./scripts/deploy-workspaces.sh` once classifier allows rsync
- [ ] **Firecrawl API key** — replace PLACEHOLDER in `gateway.systemd.env`, restart gateway
- [ ] **Education agent bootstrap** — populate `review-queue.json` before enabling daily cron
- [ ] **Composio + GSC** — needed for SEO agent's Search Console access
