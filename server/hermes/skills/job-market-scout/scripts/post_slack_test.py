"""Post a test message to a Slack channel using Hermes bot token."""
import json, urllib.request

CHANNEL = "C0B1KDU4Q8P"  # #ironclaw-jobs

with open('/tmp/hermes_bot_token', 'rb') as f:
    token = f.read().strip().decode()

body = json.dumps({
    "channel": CHANNEL,
    "text": input("Message: ") or "Test message from Hermes"
}).encode()

req = urllib.request.Request('https://slack.com/api/chat.postMessage',
    data=body,
    headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
with urllib.request.urlopen(req, timeout=10) as r:
    print(json.dumps(json.loads(r.read()), indent=2))
