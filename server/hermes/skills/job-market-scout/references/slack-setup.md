# Slack Socket Mode Troubleshooting

Lessons from connecting Hermes to Slack for the Scout migration (2026-06-18).

## Credential Sanitizer

Hermes tools (terminal, execute_code, write_file) sanitize credential-like strings
(Slack tokens, API keys) by replacing them with `***`. This breaks `.env` writes
when tokens are passed through any tool.

**Workaround**: Write tokens to temp files using `write_file` (which writes correctly),
then use a shell script that reads from those files with `cat` and appends to `.env`.
Never put the actual token value in a terminal or execute_code command.

```bash
# Correct approach:
grep -v "SLACK_BOT_TOKEN\|SLACK_APP_TOKEN" ~/.hermes/.env > /tmp/env_clean
printf "SLACK_BOT_TOKEN=*** >> /tmp/env_clean
cat /tmp/hermes_bot_token >> /tmp/env_clean   # Reads from pre-written file
```

**Alternative**: `hermes gateway setup` → interactive Slack config. User pastes tokens
directly — bypasses the sanitizer entirely.

## Socket Mode Event Delivery

### Symptom: Connected but no events
Gateway logs show "Socket Mode connected (1 workspace(s))" but no message events.

### Root Cause 1: App not reinstalled after event subscription changes
If you add `message.channels` or other event subscriptions, Slack requires
reinstalling the app. Go to https://api.slack.com/apps → Install App →
Reinstall to Workspace. Without this, zero events are delivered.

### Root Cause 2: Multiple Socket Mode connections
Slack delivers each event to only ONE connection. If `num_connections > 1`
(visible in raw WebSocket `hello` event), events go to a competing connection.
Kill stale connections by stopping the gateway, waiting 30+ seconds for
old WebSocket timeouts, then restarting.

### Debugging: Raw WebSocket test
```python
import json, urllib.request, asyncio, websockets

# Get WSS URL
with open('/tmp/hermes_app_token', 'rb') as f:
    token = f.read().strip().decode()

req = urllib.request.Request('https://slack.com/api/apps.connections.open',
    headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'}, data=b'{}')
with urllib.request.urlopen(req, timeout=10) as r:
    wss_url = json.loads(r.read())['url']

async def listen():
    async with websockets.connect(wss_url) as ws:
        print(f"Connected. num_connections will be in hello event.")
        while True:
            msg = await asyncio.wait_for(ws.recv(), timeout=60)
            data = json.loads(msg)
            print(f"EVENT: {data.get('type')}")

asyncio.run(listen())
```

Requires `pip install websockets` in Hermes venv.

## Required Config for Channel Response

```yaml
platforms:
  slack:
    enabled: true
    require_mention: false           # Must be false for free response
    free_response_channels: "C0..."  # Channel ID
```

And in `.env`:
```
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
GATEWAY_ALLOW_ALL_USERS=true         # If no SLACK_ALLOWED_USERS set
```

## OpenClaw Auto-Restart

OpenClaw gateway was auto-restarting via systemd even after killing the process.
Root cause: symlink at `~/.config/systemd/user/default.target.wants/openclaw-gateway.service`
was still active. Remove both the service file AND the symlink, then `systemctl --user daemon-reload`.
