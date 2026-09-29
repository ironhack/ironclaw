#!/bin/bash
# SEO Data Fetch (v2, 2026-09-25) - no_agent cron job, Mon + Thu 10:00 UTC.
# Pulls EVERYTHING the report needs and pre-computes all numbers, so the LLM job only
# interprets. stdout = the digest (injected into "SEO: Intel & Audit" via context_from).
#
#   1. GSC 28-day trend (query,country,date)  -> recent / previous 7d derived from it
#   2. GSC page-level, recent + previous 7d
#   3. GA4 all + organic, recent + previous 7d
#   4. legacy analyze-gsc.py text (kept for ad-hoc questions)
#   5. PR impact (merged, 30d) + open SEO PRs
#   6. live site check, news headlines
#   7. fix outcomes (resolved backlog items vs baseline)
#   8. seo-analyze.py -> seo-data-DATE.json + seo-digest-DATE.md  (printed)
set -uo pipefail

WORKSPACE="/home/openclaw/ironclaw-data/workspace-ironclaw-seo"
SKILL_DIR="/home/openclaw/.hermes/skills/ironhack/ironclaw-seo/scripts"
MEMORY="$WORKSPACE/memory"
mkdir -p "$MEMORY"

END=$(date -d '4 days ago' +%Y-%m-%d)
RECENT_START=$(date -d "$END - 6 days" +%Y-%m-%d)
PREV_END=$(date -d "$RECENT_START - 1 day" +%Y-%m-%d)
PREV_START=$(date -d "$PREV_END - 6 days" +%Y-%m-%d)
TREND_START=$(date -d "$END - 27 days" +%Y-%m-%d)
TODAY=$(date +%Y-%m-%d)
COUNTRIES="esp,fra,deu,prt,nld"
LOG="$MEMORY/fetch-$TODAY.log"
: > "$LOG"

step() { echo "[$(date +%H:%M:%S)] $*" >> "$LOG"; }
run() {  # run "label" cmd... ; never aborts the whole fetch
  local label="$1"; shift
  local t0=$(date +%s)
  if "$@" 2>> "$LOG"; then step "OK   $label ($(( $(date +%s) - t0 ))s)"; else step "FAIL $label (exit $?) - see log"; fi
}

step "SEO Data Fetch $TODAY | recent=$RECENT_START..$END prev=$PREV_START..$PREV_END trend=$TREND_START..$END"

# 1. GSC 28-day trend, then derive the two 7-day files (identical to direct queries, verified 2026-09-25)
run "gsc trend28" bash -c "python3 '$SKILL_DIR/gsc-query.py' '$TREND_START' '$END' '$COUNTRIES' > '$MEMORY/gsc-trend28-$TODAY.json'"
run "gsc split 7d" python3 - "$MEMORY" "$TODAY" "$RECENT_START" "$END" "$PREV_START" "$PREV_END" <<'PY'
import json, sys
mem, today, rs, re_, ps, pe = sys.argv[1:7]
d = json.load(open(f"{mem}/gsc-trend28-{today}.json"))
rows = d["rows"]
for name, lo, hi in (("recent", rs, re_), ("previous", ps, pe)):
    sub = [r for r in rows if lo <= r["keys"][2] <= hi]
    json.dump({"rows": sub, "total_fetched": len(sub), "total_filtered": len(sub), "start_date": lo, "end_date": hi,
               "derived_from": f"gsc-trend28-{today}.json"}, open(f"{mem}/gsc-{name}-{today}.json", "w"))
print("split ok", file=sys.stderr)
PY

# 2. GSC page-level (recent + previous)
run "gsc pages recent" bash -c "python3 '$SKILL_DIR/gsc-query.py' '$RECENT_START' '$END' '$COUNTRIES' --dims page,country > '$MEMORY/gsc-pages-$TODAY.json'"
run "gsc pages prev"   bash -c "python3 '$SKILL_DIR/gsc-query.py' '$PREV_START' '$PREV_END' '$COUNTRIES' --dims page,country > '$MEMORY/gsc-pages-prev-$TODAY.json'"

# 3. GA4 (recent + previous, all + organic)
run "ga4 all"          bash -c "python3 '$SKILL_DIR/ga4-query.py' '$RECENT_START' '$END' > '$MEMORY/ga4-all-$TODAY.json'"
run "ga4 organic"      bash -c "python3 '$SKILL_DIR/ga4-query.py' '$RECENT_START' '$END' --organic-only > '$MEMORY/ga4-organic-$TODAY.json'"
run "ga4 all prev"     bash -c "python3 '$SKILL_DIR/ga4-query.py' '$PREV_START' '$PREV_END' > '$MEMORY/ga4-all-prev-$TODAY.json'"
run "ga4 organic prev" bash -c "python3 '$SKILL_DIR/ga4-query.py' '$PREV_START' '$PREV_END' --organic-only > '$MEMORY/ga4-organic-prev-$TODAY.json'"

# 4. legacy text analysis (ad-hoc questions in Slack still read it)
run "analyze-gsc txt"  bash -c "python3 '$SKILL_DIR/analyze-gsc.py' '$MEMORY/gsc-recent-$TODAY.json' '$MEMORY/gsc-previous-$TODAY.json' '$MEMORY/gsc-trend28-$TODAY.json' '$MEMORY/gsc-pages-$TODAY.json' > '$MEMORY/gsc-analysis-$TODAY.txt'"

# 5. PRs
run "pr impact"        bash -c "cd '$SKILL_DIR' && python3 pr-impact.py 30 --json '$MEMORY/pr-impact-$TODAY.json' > '$MEMORY/pr-impact-$TODAY.txt'"
run "pr open"          bash -c "cd '$SKILL_DIR' && python3 pr-correlations.py 30 --json '$MEMORY/pr-open-$TODAY.json' > '$MEMORY/pr-correlations-$TODAY.txt'"

# 6. live site + news
run "live check"       python3 "$SKILL_DIR/seo-live-check.py" --out "$MEMORY/live-check-$TODAY.json"
run "news"             python3 "$SKILL_DIR/seo-news-fetch.py" --days 10 --out "$MEMORY/news-$TODAY.json"

# 7. fix outcomes
run "outcomes"         python3 "$SKILL_DIR/seo-outcomes.py" --date "$TODAY" --out "$MEMORY/outcomes-$TODAY.json"

# 8. analysis -> data + digest
run "analyze"          python3 "$SKILL_DIR/seo-analyze.py" --date "$TODAY" --memory "$MEMORY"

# summary + LATEST symlinks
cat > "$MEMORY/gsc-summary-$TODAY.txt" << EOF
SEO Data Fetch — $TODAY
Windows: $RECENT_START to $END (recent), $PREV_START to $PREV_END (previous), $TREND_START to $END (trend)
DATE_WINDOWS: recent_start=$RECENT_START recent_end=$END prev_start=$PREV_START prev_end=$PREV_END
EOF
for f in gsc-summary-$TODAY.txt gsc-recent-$TODAY.json gsc-previous-$TODAY.json gsc-trend28-$TODAY.json \
         gsc-pages-$TODAY.json gsc-pages-prev-$TODAY.json ga4-all-$TODAY.json ga4-organic-$TODAY.json \
         ga4-all-prev-$TODAY.json ga4-organic-prev-$TODAY.json gsc-analysis-$TODAY.txt \
         seo-data-$TODAY.json seo-digest-$TODAY.md live-check-$TODAY.json news-$TODAY.json outcomes-$TODAY.json \
         pr-impact-$TODAY.json pr-open-$TODAY.json; do
  [ -e "$MEMORY/$f" ] && ln -sf "$f" "$MEMORY/${f/$TODAY/LATEST}"
done

# prune raw files older than 60 days (keep seo-data/digest/outcomes history)
find "$MEMORY" -maxdepth 1 -type f \( -name 'gsc-*.json' -o -name 'ga4-*.json' -o -name 'gsc-*.txt' -o -name 'news-*.json' -o -name 'live-check-*.json' -o -name 'fetch-*.log' \) -mtime +60 -delete 2>/dev/null

# stdout = digest (goes to the agent job)
if [ -s "$MEMORY/seo-digest-$TODAY.md" ]; then
  cat "$MEMORY/seo-digest-$TODAY.md"
else
  echo "SEO Data Fetch $TODAY FAILED to produce a digest. Log:"; cat "$LOG"
  exit 1
fi
echo
echo "## Fetch log"
grep -E "^\[" "$LOG"
