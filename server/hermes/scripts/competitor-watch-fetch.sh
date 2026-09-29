#!/bin/bash
# Competitor Watch v2 - Phase 1 (no_agent cron, Mon 09:00 UTC).
#   1. competitor-watch-fetch.py  (Camoufox scrape -> competitor-snapshots/DATE/*.json)
#   2. cw-sitemaps.py             (site activity: new URLs vs last week)
#   3. cw-prepare.py              (capture quality + extraction-ready texts)
# stdout = digest for the Phase 2 agent (context_from). Never aborts on one step failing.
set -uo pipefail
SK="/home/openclaw/.hermes/skills/openclaw-imports/competitor-watch/scripts"
PY="${HERMES_PY:-/home/openclaw/.hermes/hermes-agent/venv/bin/python}"
D=$(date +%Y-%m-%d)
LOG="/home/openclaw/ironclaw-data/workspace/competitor-watch/fetch-$D.log"
mkdir -p "$(dirname "$LOG")"; : > "$LOG"
step() { echo "[$(date +%H:%M:%S)] $*" >> "$LOG"; }

step "fetch start"
# 3 browsers at a time (4-core / 8 GB VPS), 800 s scrape budget inside the 1200 s cron script limit (cron.script_timeout_seconds)
COMPETITOR_WATCH_CONCURRENCY=${COMPETITOR_WATCH_CONCURRENCY:-3} COMPETITOR_WATCH_BUDGET=${COMPETITOR_WATCH_BUDGET:-800} \
  "$PY" /home/openclaw/.hermes/scripts/competitor-watch-fetch.py >> "$LOG" 2>&1 \
  && step "fetch ok" || step "fetch FAILED (exit $?)"
python3 "$SK/cw-sitemaps.py" --date "$D" > /tmp/cw-sitemaps-digest.txt 2>> "$LOG" && step "sitemaps ok" || step "sitemaps FAILED"
python3 "$SK/cw-prepare.py" --date "$D" > /tmp/cw-prepare-digest.txt 2>> "$LOG" && step "prepare ok" || step "prepare FAILED"

DIGEST="/home/openclaw/ironclaw-data/workspace/competitor-watch/digest-$D.md"
{
  cat /tmp/cw-prepare-digest.txt 2>/dev/null
  echo
  cat /tmp/cw-sitemaps-digest.txt 2>/dev/null
  echo
  echo "## Fetch log"; grep -E "^\[" "$LOG"
  grep -E "TIMEOUT|FAIL|Done\." "$LOG" | tail -12
} > "$DIGEST"
ln -sf "digest-$D.md" /home/openclaw/ironclaw-data/workspace/competitor-watch/digest-LATEST.md
cat "$DIGEST"
