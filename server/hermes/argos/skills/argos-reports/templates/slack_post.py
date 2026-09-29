#!/usr/bin/env python3
"""Argos Slack poster — known-good template (verified 2026-08-13).

Copy to /tmp/slack_post.py, replace the `blocks` list with your message,
and run `python3 /tmp/slack_post.py`. Uses :emoji_name: syntax only (never
Unicode emoji — variation selectors trip the cron security scanner).

Token is read line-by-line from the profile .env (NOT sourced in bash —
multiline JSON values break `source`). requests + slack_sdk are both
available in the agent env; this uses requests for a transparent ok-check.
"""
import os
import sys
import requests

_home = os.path.expanduser("~")
# In cron mode, HOME points at the profile's `home/` subdir, NOT the profile root.
# The .env lives at the profile root — the parent of that home dir. Try candidates
# so this works in both interactive (~ == real user home) and cron (~ == profile home).
_candidates = [
    os.path.join(_home, ".hermes", "profiles", "argos", ".env"),
    os.path.join(os.path.dirname(_home), ".env"),
    "/home/openclaw/.hermes/profiles/argos/.env",
]
ENV_PATH = next((p for p in _candidates if os.path.exists(p)), _candidates[0])
token = None
with open(ENV_PATH) as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip().strip('"').strip("'") == "SLACK_BOT_TOKEN":
            token = v.strip().strip('"').strip("'")
            break

if not token:
    print("ERROR: SLACK_BOT_TOKEN not found", file=sys.stderr)
    sys.exit(1)

CHANNEL = "C0BFMA3117F"  # SLACK_HOME_CHANNEL
S3_URL = "https://ih-ironclaw.s3.eu-west-1.amazonaws.com/ironclaw/argos/shared/performance.html"

# Replace with your blocks. Header + summary + divider + sections + link.
blocks = [
    {"type": "header", "text": {"type": "plain_text", "text": "Argos Performance Report — YYYY-MM-DD", "emoji": True}},
    {"type": "section", "text": {"type": "mrkdwn", "text": ":red_circle: *Lead insight first*\n• bullet"}},
    {"type": "divider"},
    {"type": "section", "text": {"type": "mrkdwn", "text": f":bar_chart: <{S3_URL}|View Full HTML Report>"}},
]

resp = requests.post(
    "https://slack.com/api/chat.postMessage",
    headers={"Authorization": f"Bearer {token}"},
    json={"channel": CHANNEL, "blocks": blocks, "text": "Argos report"},  # `text` = fallback/notification
    timeout=30,
)
data = resp.json()
print("HTTP", resp.status_code, "| ok:", data.get("ok"))
if not data.get("ok"):
    print("error:", data.get("error"))
    sys.exit(1)
print("ts:", data.get("ts"))
