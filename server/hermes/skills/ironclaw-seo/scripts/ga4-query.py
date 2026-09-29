#!/usr/bin/env python3
"""GA4 query script for Ironhack SEO — pulls traffic data per market.

Usage:
  python3 ga4-query.py <start-date> <end-date> [--organic-only]

Same auth as gsc-query.py: service account impersonating rodolfo.puglia@ironhack.com
Property ID: 256164398 (GA4 - Production)
"""
import sys, os, json, urllib.request
import google.auth.transport.requests
from google.oauth2 import service_account

SA_KEY = os.environ.get('GOOGLE_SA_KEY_PATH', '/home/openclaw/ironclaw-data/gsc-service-account.json')
IMPERSONATE = os.environ.get('GOOGLE_IMPERSONATE_EMAIL', 'rodolfo.puglia@ironhack.com')
PROPERTY_ID = '256164398'
COUNTRIES = ['Germany', 'Spain', 'France', 'Netherlands', 'Portugal']

start_date = sys.argv[1] if len(sys.argv) > 1 else '2026-04-21'
end_date   = sys.argv[2] if len(sys.argv) > 2 else '2026-04-27'
organic_only = '--organic-only' in sys.argv

creds = service_account.Credentials.from_service_account_file(
    SA_KEY,
    scopes=['https://www.googleapis.com/auth/analytics.readonly'],
    subject=IMPERSONATE
)
creds.refresh(google.auth.transport.requests.Request())

url = f'https://analyticsdata.googleapis.com/v1beta/properties/{PROPERTY_ID}:runReport'

if organic_only:
    body = {
        'dateRanges': [{'startDate': start_date, 'endDate': end_date}],
        'dimensions': [{'name': 'country'}],
        'metrics': [
            {'name': 'sessions'},
            {'name': 'activeUsers'},
            {'name': 'screenPageViews'},
            {'name': 'bounceRate'},
            {'name': 'averageSessionDuration'},
        ],
        'dimensionFilter': {
            'andGroup': {
                'expressions': [
                    {'filter': {'fieldName': 'country', 'inListFilter': {'values': COUNTRIES}}},
                    {'filter': {'fieldName': 'sessionDefaultChannelGroup', 'inListFilter': {'values': ['Organic Search']}}},
                ]
            }
        }
    }
else:
    body = {
        'dateRanges': [{'startDate': start_date, 'endDate': end_date}],
        'dimensions': [{'name': 'country'}],
        'metrics': [
            {'name': 'sessions'},
            {'name': 'activeUsers'},
            {'name': 'screenPageViews'},
            {'name': 'bounceRate'},
            {'name': 'averageSessionDuration'},
            {'name': 'eventCount'},
        ],
        'dimensionFilter': {
            'filter': {'fieldName': 'country', 'inListFilter': {'values': COUNTRIES}}
        }
    }

req = urllib.request.Request(url, data=json.dumps(body).encode(),
    headers={'Authorization': 'Bearer ' + creds.token, 'Content-Type': 'application/json'})

try:
    resp = json.loads(urllib.request.urlopen(req, timeout=15).read())
except urllib.error.HTTPError as e:
    print(json.dumps({'error': e.read().decode()[:500]}))
    sys.exit(1)

COUNTRY_MAP = {
    'Germany': 'deu', 'Spain': 'esp', 'France': 'fra',
    'Netherlands': 'nld', 'Portugal': 'prt'
}

out = {'rows': [], 'organic_only': organic_only, 'start_date': start_date, 'end_date': end_date}
for row in resp.get('rows', []):
    country = row['dimensionValues'][0]['value']
    metrics = [m['value'] for m in row['metricValues']]
    out['rows'].append({
        'country': COUNTRY_MAP.get(country, country),
        'country_name': country,
        'sessions': int(metrics[0]),
        'active_users': int(metrics[1]),
        'page_views': int(metrics[2]),
        'bounce_rate': float(metrics[3]),
        'avg_session_duration': float(metrics[4]),
    })

print(json.dumps(out))
