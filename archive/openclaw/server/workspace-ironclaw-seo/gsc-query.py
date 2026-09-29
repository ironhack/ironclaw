#!/usr/bin/env python3
import sys, os, json, urllib.request
import google.auth.transport.requests
from google.oauth2 import service_account

SA_KEY = os.environ.get('GOOGLE_SA_KEY_PATH', '/home/openclaw/.openclaw/gsc-service-account.json')
IMPERSONATE = os.environ.get('GOOGLE_IMPERSONATE_EMAIL', 'rodolfo.puglia@ironhack.com')
SITE_ENCODED = 'https%3A%2F%2Fwww.ironhack.com%2F'

start_date = sys.argv[1] if len(sys.argv) > 1 else '2026-04-21'
end_date   = sys.argv[2] if len(sys.argv) > 2 else '2026-04-27'
countries  = set(sys.argv[3].split(',')) if len(sys.argv) > 3 else {'esp','fra','deu','prt','nld'}

creds = service_account.Credentials.from_service_account_file(
    SA_KEY, scopes=['https://www.googleapis.com/auth/webmasters.readonly'], subject=IMPERSONATE
)
creds.refresh(google.auth.transport.requests.Request())

url = f'https://searchconsole.googleapis.com/webmasters/v3/sites/{SITE_ENCODED}/searchAnalytics/query'
all_rows, start_row, page_size = [], 0, 25000

while True:
    body = json.dumps({'startDate': start_date, 'endDate': end_date,
        'dimensions': ['query','country','date'], 'rowLimit': page_size, 'startRow': start_row}).encode()
    req = urllib.request.Request(url, data=body,
        headers={'Authorization': 'Bearer ' + creds.token, 'Content-Type': 'application/json'})
    try:
        resp = json.loads(urllib.request.urlopen(req).read())
    except urllib.error.HTTPError as e:
        print(json.dumps({'error': e.read().decode()})); sys.exit(1)
    rows = resp.get('rows', [])
    if not rows: break
    all_rows.extend(rows)
    if len(rows) < page_size: break
    start_row += page_size

filtered = [r for r in all_rows if r['keys'][1] in countries]
print(json.dumps({'rows': filtered, 'total_fetched': len(all_rows), 'total_filtered': len(filtered)}))
