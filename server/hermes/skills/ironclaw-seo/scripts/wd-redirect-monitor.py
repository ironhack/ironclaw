#!/usr/bin/env python3
"""
wd-redirect-monitor.py -- WD page consolidation monitor.

Usage: python3 wd-redirect-monitor.py <start-date> <end-date>
  Dates: YYYY-MM-DD. Use a 7-day window ending 3 days ago to account for GSC lag.

Output: JSON to stdout with three sections:
  redirect_checks  -- HTTP 301 health for every source URL
  gsc_sources      -- GSC performance for source (merging) URLs (should trend to zero)
  gsc_destinations -- GSC performance for destination (course) URLs (should grow)
"""

import sys, os, json, urllib.request, urllib.error
from collections import defaultdict
import google.auth.transport.requests
from google.oauth2 import service_account

WORKSPACE  = os.path.dirname(os.path.abspath(__file__))
MAP_FILE   = os.environ.get('MAP_FILE', os.path.join(WORKSPACE, 'wd-redirect-map.json'))
SA_KEY     = os.environ.get('GOOGLE_SA_KEY_PATH', '/home/openclaw/ironclaw-data/gsc-service-account.json')
IMPERSONATE = os.environ.get('GOOGLE_IMPERSONATE_EMAIL', 'rodolfo.puglia@ironhack.com')
SITE_ENCODED = 'https%3A%2F%2Fwww.ironhack.com%2F'
GSC_URL    = f'https://searchconsole.googleapis.com/webmasters/v3/sites/{SITE_ENCODED}/searchAnalytics/query'

if len(sys.argv) < 3:
    print('Usage: python3 wd-redirect-monitor.py <start-date> <end-date>', file=sys.stderr)
    sys.exit(1)

start_date, end_date = sys.argv[1], sys.argv[2]

with open(MAP_FILE) as f:
    url_map = json.load(f)

sources      = url_map['sources']
destinations = url_map['destinations']
tracked_urls = set(s['url'] for s in sources) | set(d['url'] for d in destinations)


# ---------------------------------------------------------------------------
# PART 1: HTTP redirect checks
# ---------------------------------------------------------------------------

class _NoRedirect(urllib.request.HTTPErrorProcessor):
    def http_response(self, request, response):
        return response
    https_response = http_response

_opener = urllib.request.build_opener(_NoRedirect())

def check_redirect(source_url, expected_dest):
    try:
        req = urllib.request.Request(
            source_url,
            headers={'User-Agent': 'Mozilla/5.0 (compatible; IronclawBot/1.0)'}
        )
        resp = _opener.open(req, timeout=10)
        status   = resp.status
        location = resp.headers.get('Location') or ''
        # normalize trailing slash
        actual   = location.rstrip('/')
        expected = expected_dest.rstrip('/')
        ok       = (status == 301) and (actual == expected)
        issue    = None
        if status != 301:
            issue = f'Expected 301, got {status}'
        elif not location:
            issue = 'No Location header in response'
        elif actual != expected:
            issue = f'Wrong destination: got {location}, expected {expected_dest}'
        return {'http_status': status, 'actual_destination': location, 'ok': ok, 'issue': issue}
    except Exception as e:
        return {'http_status': None, 'actual_destination': None, 'ok': False, 'issue': str(e)}

redirect_checks = []
for s in sources:
    result = check_redirect(s['url'], s['destination'])
    redirect_checks.append({
        'source_url':          s['url'],
        'type':                s['type'],
        'country':             s['country'],
        'language':            s['language'],
        'expected_destination': s['destination'],
        **result
    })


# ---------------------------------------------------------------------------
# PART 2: GSC page-level performance
# ---------------------------------------------------------------------------

creds = service_account.Credentials.from_service_account_file(
    SA_KEY,
    scopes=['https://www.googleapis.com/auth/webmasters.readonly'],
    subject=IMPERSONATE
)

def _refresh_token():
    creds.refresh(google.auth.transport.requests.Request())

def gsc_fetch(dimensions):
    """Fetch all rows for given dimensions over the configured date range."""
    _refresh_token()
    all_rows, start_row, page_size = [], 0, 25000
    while True:
        body = json.dumps({
            'startDate':  start_date,
            'endDate':    end_date,
            'dimensions': dimensions,
            'rowLimit':   page_size,
            'startRow':   start_row
        }).encode()
        req = urllib.request.Request(
            GSC_URL, data=body,
            headers={'Authorization': 'Bearer ' + creds.token, 'Content-Type': 'application/json'}
        )
        try:
            resp = json.loads(urllib.request.urlopen(req).read())
        except urllib.error.HTTPError as e:
            print(json.dumps({'error': e.read().decode()}), file=sys.stderr)
            break
        rows = resp.get('rows', [])
        if not rows:
            break
        all_rows.extend(rows)
        if len(rows) < page_size:
            break
        start_row += page_size
    return all_rows

# Page totals: dimensions = ['page']
totals_raw = gsc_fetch(['page'])
page_totals = {r['keys'][0]: r for r in totals_raw if r['keys'][0] in tracked_urls}

# Top queries per page: dimensions = ['page', 'query']
queries_raw = gsc_fetch(['page', 'query'])
page_queries = defaultdict(list)
for r in queries_raw:
    page = r['keys'][0]
    if page not in tracked_urls:
        continue
    page_queries[page].append({
        'query':       r['keys'][1],
        'clicks':      r['clicks'],
        'impressions': r['impressions'],
        'ctr':         round(r['ctr'], 4),
        'position':    round(r['position'], 1)
    })
# Sort by impressions desc, keep top 10
for page in page_queries:
    page_queries[page].sort(key=lambda x: x['impressions'], reverse=True)
    page_queries[page] = page_queries[page][:10]

def build_stats(url_info):
    u = url_info['url']
    t = page_totals.get(u, {})
    return {
        **url_info,
        'clicks':      t.get('clicks', 0),
        'impressions': t.get('impressions', 0),
        'ctr':         round(t.get('ctr', 0), 4),
        'position':    round(t.get('position', 0), 1),
        'top_queries': page_queries.get(u, [])
    }

gsc_sources      = [build_stats(s) for s in sources]
gsc_destinations = [build_stats(d) for d in destinations]


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

print(json.dumps({
    'period':           {'start': start_date, 'end': end_date},
    'redirect_checks':  redirect_checks,
    'gsc_sources':      gsc_sources,
    'gsc_destinations': gsc_destinations
}, indent=2))
