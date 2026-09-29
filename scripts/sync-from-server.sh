#!/bin/bash
# Pull the live Hermes scripts, skills and cron job definitions from the server into server/hermes/.
# The server is the source of truth for code; this repo mirrors it for version control and review.
# Run from the repo root: ./scripts/sync-from-server.sh   (then commit)
set -euo pipefail
SERVER="openclaw-server"
DEST="$(cd "$(dirname "$0")/.." && pwd)/server/hermes"
EXCL=(--exclude '__pycache__' --exclude '*.pyc' --exclude '.bak-*' --exclude '.curator_backups' --exclude '.archive'
      --exclude '.usage.json*' --exclude '.hub' --exclude '.bundled_manifest' --exclude '*.v2-copy' --exclude '.env')
mkdir -p "$DEST"/{scripts,skills,argos}

echo "== scripts (default profile)"
rsync -a --delete "${EXCL[@]}" --include '*.py' --include '*.sh' --exclude '*' "$SERVER:/home/openclaw/.hermes/scripts/" "$DEST/scripts/"

echo "== skills (default profile)"
rsync -a --delete "${EXCL[@]}" "$SERVER:/home/openclaw/.hermes/skills/ironhack/ironclaw-seo/" "$DEST/skills/ironclaw-seo/"
rsync -a --delete "${EXCL[@]}" "$SERVER:/home/openclaw/.hermes/skills/ironhack/job-market-scout/" "$DEST/skills/job-market-scout/"
rsync -a --delete "${EXCL[@]}" "$SERVER:/home/openclaw/.hermes/skills/openclaw-imports/competitor-watch/" "$DEST/skills/competitor-watch/"

echo "== argos profile"
rsync -a --delete "${EXCL[@]}" "$SERVER:/home/openclaw/.hermes/profiles/argos/scripts/argos/" "$DEST/argos/scripts/"
rsync -a --delete "${EXCL[@]}" "$SERVER:/home/openclaw/.hermes/profiles/argos/skills/marketing/argos-reports/" "$DEST/argos/skills/argos-reports/"
rsync -a --delete "${EXCL[@]}" "$SERVER:/home/openclaw/.hermes/profiles/argos/skills/marketing/google-marketing-intelligence/" "$DEST/argos/skills/google-marketing-intelligence/"
rsync -a "$SERVER:/home/openclaw/.hermes/profiles/argos/SOUL.md" "$DEST/argos/SOUL.md"

echo "== cron job inventory"
ssh "$SERVER" 'python3 - <<EOF
import json, glob
rows = []
for path in ["/home/openclaw/.hermes/cron/jobs.json"] + sorted(glob.glob("/home/openclaw/.hermes/profiles/*/cron/jobs.json")):
    prof = "default" if "/profiles/" not in path else path.split("/profiles/")[1].split("/")[0]
    try:
        jobs = json.load(open(path))["jobs"]
    except Exception:
        continue
    for j in jobs:
        rows.append((prof, j["id"], j.get("name"), j.get("schedule_display") or "", "script" if j.get("no_agent") else "agent",
                     j.get("script") or "", j.get("deliver") or "", j.get("failure_deliver") or "", "yes" if j.get("enabled") else "PAUSED"))
print("# Hermes cron jobs (exported by scripts/sync-from-server.sh)\n")
print("| Profile | ID | Name | Schedule (UTC) | Type | Script | Deliver | Failure → | Enabled |")
print("|---|---|---|---|---|---|---|---|---|")
for r in rows:
    print("| " + " | ".join(str(x) for x in r) + " |")
print()
print("Prompts of agent jobs live in the skill folders (references/cron-prompt-v2.txt) and in the job store on the server.")
EOF' > "$DEST/cron-jobs.md"

echo "== done: $(find "$DEST" -type f | wc -l) files under server/hermes"
