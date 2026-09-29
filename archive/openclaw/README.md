# OpenClaw era (archived 2026-09-25)

Everything in this folder describes the OpenClaw-based setup that ran on the server from March to
June 2026. OpenClaw was removed from the server on 2026-09-25 (software uninstalled, OpenClaw-only state
archived under `~/archive/` on the server). Kept here for history only; nothing in this folder is deployed.

- `server/workspace-*` — the OpenClaw agent workspaces (SOUL/AGENTS/TOOLS/MEMORY) that were rsync-ed to the
  server. The `workspace-ironclaw-jobs` files carry uncommitted edits from the last OpenClaw Scout iteration.
- `deploy-workspaces.sh` — the push script for those workspaces.
- `slack-app/manifest.json`, `dot-slack/` — the OpenClaw Slack app (`ironclaw2`, A0B19LV97DM), no longer installed.

The live setup (Hermes) is documented in the repo README and mirrored under `server/hermes/`.
