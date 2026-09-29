# CLAUDE.md — IronClaw repo guide

Ironhack's scheduled intelligence agents run on **Hermes Agent** on `openclaw-server`. This repo is the ops
log, the documentation, and a read-only mirror of the live code. The server is the source of truth for
code; Rudy commits and pushes this repo manually.

---

## What this repo is for

- **CHANGELOG.md** — ops log of every server session, most recent first. Update it at the end of every session.
- **README.md** — current state of the server. Keep it accurate after any structural change.
- **server/hermes/** — mirror of the live scripts, skills and the cron inventory. Refresh with
  `./scripts/sync-from-server.sh` after changing anything on the server. Never edit the mirror by hand.
- **archive/openclaw/** — the OpenClaw era (removed from the server 2026-09-25). History only.

## What this repo is NOT for

- Secrets. They live only in `~/.hermes/.env` and `~/.hermes/profiles/*/.env` on the server.
- Data. Snapshots, states and reports live in `/home/openclaw/ironclaw-data/` and on S3.
- Deploying. There is no push script anymore: edit on the server (back up first), test, then sync back here.

---

## How to work on the server

```bash
ssh openclaw-server                       # user openclaw; sudo password in memory (reference_server_access)
HERMES="HERMES_HOME=$HOME/.hermes $HOME/.local/bin/hermes"        # since the 2026-09-29 update
cd ~/.hermes && eval $HERMES cron list | edit <id> --prompt "$(cat file)" | run <id> | pause <id> | doctor
# argos profile: cd ~/.hermes/profiles/argos && HERMES_HOME=$PWD ~/.local/bin/hermes --profile argos cron ...
# pipeline python (google-ads, camoufox, playwright): /home/openclaw/ironclaw-venv/bin/python
systemctl --user restart hermes-gateway            # the ONE host gateway: restarts every profile's bots + cron (no per-profile units since 2026-09-29)
journalctl --user -u hermes-gateway -n 50
```

Rules that have bitten before:

- **Back up before editing** a live script or skill (`cp -n file .bak-YYYY-MM-DD/`), then `py_compile` /
  `bash -n`, then test with a preview flag (`--preview`, `--local`, `--to <DM id>`) before the real path.
- **Cron job prompts** are edited with `hermes cron edit --prompt`, never by editing `cron/jobs.json` by hand
  (the scheduler rewrites it). `context_from` cannot be set from the CLI; pass data through files instead.
- **Cron mode constraints for agent jobs**: no `execute_code`, no pipe-to-interpreter, no `&` backgrounding,
  no Unicode emoji in commands (Slack `:shortcodes:` only), no heredocs. Write scripts to files and run them.
- **Never `pkill -f <pattern>` from an ssh one-liner** whose command line contains the pattern: it kills the
  ssh session itself (exit 255). Put such logic in a script file.
- **Cron `.py` script jobs ignore shebangs** and run on Hermes's own Python 3.14 runtime unless the job has
  `--interpreter`. Anything needing google-ads / Camoufox must use `/home/openclaw/ironclaw-venv/bin/python`
  (Argos jobs carry the interpreter field; shell wrappers set the path explicitly).
- **Hermes updates**: `hermes update --plan` first; export `CC=gcc CXX=g++ LDSHARED="gcc -shared"
  LDCXXSHARED="g++ -shared"` (the managed Python wants clang); back up `~/.hermes` and the checkout first.
- **Max ~3 headless browsers at once** on this 4-core / 8 GB box.
- **`.env` files cannot be `source`d** (unquoted JSON values); parse them line by line in Python.
- `~/.openclaw` is a symlink to `ironclaw-data`; code should reference `/home/openclaw/ironclaw-data/`.

## Design principles (established 2026-09-25, keep them)

1. **Scripts own the numbers, the model owns the narrative.** Fetch/prepare jobs pre-compute everything into
   JSON + a digest; the agent reads the digest, writes a small narrative JSON, runs the generator.
2. **Every claim is verified against data.** Competitor items need verbatim page evidence; SEO fixes carry
   outcome definitions measured against a baseline and a market control; Slack numbers come from the same
   files as the HTML.
3. **State outlives the run.** Backlogs, competitor state, change logs and outcome verdicts are files that
   accumulate; reports are cumulative, not weekly rewrites.
4. **One post per run**, posted by the generator in the approved shape: headline sentence, status scorecard,
   verified changes / outcomes, watch-outs, actions, context line, buttons; details in a thread. Agent jobs
   deliver `local` with `failure-deliver` to the channel.

## Where things are (server)

| Pipeline | Code | Data | Docs |
|---|---|---|---|
| SEO assessment | `~/.hermes/skills/ironhack/ironclaw-seo/scripts/`, `~/.hermes/scripts/seo-data-fetch.sh` | `ironclaw-data/workspace-ironclaw-seo/` | `skills/ironhack/ironclaw-seo/SKILL.md` (v2), `references/cron-prompt-v2.txt`, `narrative-schema.md` |
| Competitor watch | `~/.hermes/skills/openclaw-imports/competitor-watch/scripts/cw-*.py`, `~/.hermes/scripts/competitor-watch-fetch.{py,sh}` | `ironclaw-data/workspace/competitor-{snapshots,watch}/` | that skill's `SKILL.md` (v2), `references/extraction-schema.md`, `cron-prompt-v2.txt` |
| Argos (Google Ads) | `~/.hermes/profiles/argos/scripts/argos/` (`performance_report.py`, `generate_performance_report.py`, `argos_slack.py`; daily: `sanity_check.py`, `generate_sanity_report.py`, `argos_sanity_slack.py`) | `/tmp/argos_perf_data.json`, `/tmp/argos_sanity_data.json` per run; `ironclaw-data/argos/sanity-state.json` | `profiles/argos/skills/marketing/argos-reports/`, `google-marketing-intelligence/` |
| Scout (jobs) | `~/.hermes/scripts/scout-*.py`, `skills/ironhack/job-market-scout/` | `ironclaw-data/workspace-ironclaw-jobs/jobs.db` | that skill's `SKILL.md` |

Job IDs, schedules and delivery targets: `server/hermes/cron-jobs.md` (regenerated by the sync script).

## Slack

| Channel | ID | Posted by |
|---|---|---|
| #ironclaw-seo | `C0B1MLM0L3X` | Hermes (default profile) |
| #ironclaw-watch | `C0B1MM39P8D` | Hermes (default profile) |
| #ironclaw-jobs | `C0B1KDU4Q8P` | Hermes (default profile) |
| #argos-home | `C0BFMA3117F` | Argos (ih-argos app `A0BFQG5MBRQ`) |

Rudy: `U02MV9VPGV6` (use as `--to` target for DM previews). The OpenClaw app `ironclaw2` (`A0B19LV97DM`) is dead.

## Current priorities / open work

1. Watch the first v2 runs (Mon 2026-09-28): SEO 14:00 Rome, competitor watch 14:00, Argos 10:00. Check the
   model followed the evidence / narrative rules; the validators and failure alerts will show if not.
2. Uninstall the `ironclaw2` Slack app; drop the `~/.openclaw` symlink after two clean weeks.
3. Check the first v2 daily sanity post (Wed 2026-09-30 09:00 Rome): one post, new / day-N markers correct.
4. Competitor watchlist gaps (PT, NL) and the Liora catalog URL; Liora home mega-menu did not render on 09-28.
5. Watch digest should print the tracked page count per competitor; neuefische.de block recurrence.
