#!/usr/bin/env python3
"""Shared helpers for the Ironhack SEO pipeline (GSC auth/query, constants, small utils).

Import from sibling scripts with:
    import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from seo_common import *
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta

WORKSPACE = "/home/openclaw/ironclaw-data/workspace-ironclaw-seo"
MEMORY_DIR = os.path.join(WORKSPACE, "memory")
BACKLOG_PATH = os.path.join(WORKSPACE, "seo-backlog.json")
JOURNAL_PATH = os.path.join(WORKSPACE, "seo-journal.md")
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REFERENCES_DIR = os.path.join(SKILL_DIR, "references")
ARTIFACTS_PATH = os.path.join(REFERENCES_DIR, "artifact-pages.json")

SITE = "https://www.ironhack.com"
SITE_ENCODED = "https%3A%2F%2Fwww.ironhack.com%2F"
GSC_LAG_DAYS = 4          # data fetch uses today-4 as end date (GSC lags ~3 days)
COUNTRIES = ["esp", "fra", "deu", "prt", "nld"]
COUNTRY_CODES = {"esp": "ES", "fra": "FR", "deu": "DE", "prt": "PT", "nld": "NL"}
COUNTRY_NAMES = {"esp": "Spain", "fra": "France", "deu": "Germany", "prt": "Portugal", "nld": "Netherlands"}
GA4_NAMES = {"esp": "Spain", "fra": "France", "deu": "Germany", "prt": "Portugal", "nld": "Netherlands"}

AIO_MIN_IMPRESSIONS = 5000
AIO_MAX_CTR = 0.005          # 0.5%
HEAD_TERM_MIN_IMPRESSIONS = 5000


# ── auth + GSC ────────────────────────────────────────────────────────
def gsc_creds():
    import google.auth.transport.requests
    from google.oauth2 import service_account
    sa_key = os.environ.get("GOOGLE_SA_KEY_PATH", "/home/openclaw/ironclaw-data/gsc-service-account.json")
    imp = os.environ.get("GOOGLE_IMPERSONATE_EMAIL", "rodolfo.puglia@ironhack.com")
    creds = service_account.Credentials.from_service_account_file(
        sa_key, scopes=["https://www.googleapis.com/auth/webmasters.readonly",
                        "https://www.googleapis.com/auth/analytics.readonly"], subject=imp)
    creds.refresh(google.auth.transport.requests.Request())
    return creds


def gsc_query(start, end, dimensions, creds=None, filters=None, countries=None, row_limit=25000):
    """Run a Search Analytics query with pagination. Returns list of rows.
    filters: list of {dimension, operator, expression} (single AND group)."""
    creds = creds or gsc_creds()
    url = f"https://searchconsole.googleapis.com/webmasters/v3/sites/{SITE_ENCODED}/searchAnalytics/query"
    rows, start_row = [], 0
    while True:
        body = {"startDate": str(start), "endDate": str(end), "dimensions": dimensions,
                "rowLimit": row_limit, "startRow": start_row}
        if filters:
            body["dimensionFilterGroups"] = [{"filters": filters}]
        req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                     headers={"Authorization": "Bearer " + creds.token,
                                              "Content-Type": "application/json"})
        try:
            resp = json.loads(urllib.request.urlopen(req, timeout=120).read())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"GSC HTTP {e.code}: {e.read().decode()[:300]}")
        batch = resp.get("rows", [])
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < row_limit:
            break
        start_row += row_limit
    if countries is not None and "country" in dimensions:
        ci = dimensions.index("country")
        rows = [r for r in rows if r["keys"][ci] in countries]
    return rows


# ── small utils ───────────────────────────────────────────────────────
def is_brand(query):
    q = (query or "").lower()
    return "ironhack" in q or "iron hack" in q


def path_of(url):
    p = url.replace(SITE, "")
    return p or "/"


def pct(new, old):
    if not old:
        return None if not new else float("inf")
    return (new - old) / old * 100.0


def fmt_int(n):
    return f"{int(round(n)):,}"


def fmt_pct(v, digits=1):
    if v is None:
        return "n/a"
    if v == float("inf"):
        return "new"
    return f"{'+' if v > 0 else ''}{v:.{digits}f}%"


def load_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def load_artifacts():
    """Known bot/automated-volume pages to exclude from AIO analysis."""
    d = load_json(ARTIFACTS_PATH, {"pages": []})
    return d.get("pages", [])


def artifact_match(page_url, artifacts):
    p = path_of(page_url)
    for a in artifacts:
        pat = a.get("path_regex") or re.escape(a.get("path", ""))
        if pat and re.search(pat, p):
            return a
    return None


def clean_text(s):
    """No em/en dashes in report output (house style)."""
    return (s or "").replace("—", " - ").replace("–", "-")


def date_windows(end=None):
    """Standard windows. end defaults to today - GSC_LAG_DAYS."""
    end = end or (date.today() - timedelta(days=GSC_LAG_DAYS))
    recent = (end - timedelta(days=6), end)
    previous = (recent[0] - timedelta(days=7), recent[0] - timedelta(days=1))
    trend = (end - timedelta(days=27), end)
    return {"end": end, "recent": recent, "previous": previous, "trend": trend}


def week_label(start, end):
    """'Sep 14-20' or 'Aug 31-Sep 6'."""
    s = date.fromisoformat(str(start)); e = date.fromisoformat(str(end))
    if s.month == e.month:
        return f"{s.strftime('%b')} {s.day}-{e.day}"
    return f"{s.strftime('%b')} {s.day}-{e.strftime('%b')} {e.day}"
