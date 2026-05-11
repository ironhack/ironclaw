#!/bin/bash
# Deploy agent workspace files to the server.
# Run from the repo root: ./scripts/deploy-workspaces.sh

set -e

SERVER="openclaw-server"
REMOTE_BASE="/home/openclaw/.openclaw"
LOCAL_BASE="$(dirname "$0")/../server"

echo "Deploying ironclaw-seo workspace..."
rsync -av --progress "$LOCAL_BASE/workspace-ironclaw-seo/" "$SERVER:$REMOTE_BASE/workspace-ironclaw-seo/"

echo "Deploying ironclaw-edu workspace..."
rsync -av --progress "$LOCAL_BASE/workspace-ironclaw-edu/" "$SERVER:$REMOTE_BASE/workspace-ironclaw-edu/"

echo "Deploying ironclaw-jobs workspace..."
rsync -av --progress "$LOCAL_BASE/workspace-ironclaw-jobs/" "$SERVER:$REMOTE_BASE/workspace-ironclaw-jobs/"

echo "Done. Restart the gateway if needed:"
echo "  ssh $SERVER 'systemctl --user restart openclaw-gateway'"
