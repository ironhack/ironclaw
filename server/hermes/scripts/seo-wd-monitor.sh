#!/bin/bash
# SEO: WD Redirect Monitor — no_agent cron job
# Checks redirect health + GSC query volume for WD page consolidation
# Extensible to other tracks (UX next) by passing a track name
set -euo pipefail

WORKSPACE="/home/openclaw/ironclaw-data/workspace-ironclaw-seo"
SKILL_DIR="/home/openclaw/.hermes/skills/ironhack/ironclaw-seo/scripts"
TRACK="${1:-wd}"
MONITOR_DIR="$WORKSPACE/${TRACK}-monitor"
MAP_SRC="$SKILL_DIR/../references/${TRACK}-redirect-map.json"
MAP_DST="$SKILL_DIR/${TRACK}-redirect-map.json"

# Copy the track-specific map into place (wd-redirect-monitor.py reads MAP_FILE env var)
cp "$MAP_SRC" "$MAP_DST"
export MAP_FILE="$MAP_DST"

mkdir -p "$MONITOR_DIR"

END=$(date -d '3 days ago' +%Y-%m-%d)
START=$(date -d "$END - 6 days" +%Y-%m-%d)
TODAY=$(date +%Y-%m-%d)

# All progress goes to stderr — only summary goes to stdout (delivered to Slack)
python3 "$SKILL_DIR/wd-redirect-monitor.py" "$START" "$END" > "/tmp/${TRACK}-snapshot-$TODAY.json" 2>&2
cp "/tmp/${TRACK}-snapshot-$TODAY.json" "$MONITOR_DIR/${TODAY}.json"

PREV=$(ls -1 "$MONITOR_DIR"/*.json 2>/dev/null | grep -v '_baseline' | grep -v "$TODAY" | sort -r | head -1 || true)

if [ -n "$PREV" ]; then
    python3 "$SKILL_DIR/wd-report.py" "$MONITOR_DIR/${TODAY}.json" "$PREV" > "/tmp/${TRACK}-report-$TODAY.html" 2>&2
else
    python3 "$SKILL_DIR/wd-report.py" "$MONITOR_DIR/${TODAY}.json" > "/tmp/${TRACK}-report-$TODAY.html" 2>&2
fi

aws s3 cp "/tmp/${TRACK}-report-$TODAY.html" \
    "s3://ih-ironclaw/seo/${TRACK}-monitor/${TODAY}.html" \
    --region eu-west-1 >/dev/null 2>&2

# Only stdout = Slack message
REDIRECT_OK=$(python3 -c "
import json
d=json.load(open('/tmp/${TRACK}-snapshot-$TODAY.json'))
checks=d.get('redirect_checks',[])
print(f'{sum(1 for c in checks if c.get(\"ok\"))}/{len(checks)}')
")
SRC_IMPS=$(python3 -c "
import json
d=json.load(open('/tmp/${TRACK}-snapshot-$TODAY.json'))
srcs=d.get('gsc_sources',[])
print(int(sum(s.get('impressions',0) for s in srcs)))
")
DST_IMPS=$(python3 -c "
import json
d=json.load(open('/tmp/${TRACK}-snapshot-$TODAY.json'))
dsts=d.get('gsc_destinations',[])
print(int(sum(d.get('impressions',0) for d in dsts)))
")

echo "${TRACK^^} Redirect Monitor — $TODAY"
echo "Redirects: $REDIRECT_OK OK | Source impressions fading: $SRC_IMPS | Destination growing: $DST_IMPS"
echo "Report: https://ih-ironclaw.s3.eu-west-1.amazonaws.com/seo/${TRACK}-monitor/${TODAY}.html"
