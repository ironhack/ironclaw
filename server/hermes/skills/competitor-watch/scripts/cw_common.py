#!/usr/bin/env python3
"""Shared helpers for Competitor Watch v2 (state, change log, paths, normalisation)."""
import json
import os
import re
from datetime import date, datetime, timezone

SNAPSHOT_DIR = "/home/openclaw/ironclaw-data/workspace/competitor-snapshots"
WATCH_DIR = "/home/openclaw/ironclaw-data/workspace/competitor-watch"
STATE_DIR = os.path.join(WATCH_DIR, "state")
PREPARED_DIR = os.path.join(WATCH_DIR, "prepared")
EXTRACT_DIR = os.path.join(WATCH_DIR, "extractions")
SITEMAP_DIR = os.path.join(WATCH_DIR, "sitemaps")
CHANGES_PATH = os.path.join(WATCH_DIR, "changes.jsonl")
CAPTURES_PATH = os.path.join(WATCH_DIR, "captures.json")
S3_PREFIX = "watch"
PUBLIC = "https://ih-ironclaw.s3.eu-west-1.amazonaws.com"

COMPETITORS = {
    "lewagon": {"name": "Le Wagon", "site": "https://www.lewagon.com", "markets": ["ES", "PT", "FR", "NL", "DE"]},
    "nuclio": {"name": "Nuclio School", "site": "https://nuclio.school", "markets": ["ES"]},
    "neuefische": {"name": "neue fische", "site": "https://www.neuefische.de", "markets": ["DE"]},
    "spiced": {"name": "Spiced Academy", "site": "https://www.spiced-academy.com", "markets": ["DE"]},
    "fourgeeks": {"name": "4Geeks Academy", "site": "https://4geeks.com", "markets": ["ES"]},
    "masterschool": {"name": "Masterschool (MSIT)", "site": "https://joinmsit.de", "markets": ["DE"]},
    "liora": {"name": "Liora (ex-DataScientest)", "site": "https://liora.io", "markets": ["FR", "DE", "NL"]},
}

CHANGE_TYPES = {
    "program_added": ("high", ":new:"), "program_removed": ("high", ":x:"), "program_renamed": ("medium", ":label:"),
    "price_changed": ("high", ":moneybag:"), "duration_changed": ("medium", ":hourglass:"), "format_changed": ("low", ":gear:"),
    "cohort_moved": ("low", ":calendar:"), "promo_started": ("medium", ":tada:"), "promo_ended": ("low", ":tada:"),
    "claim_added": ("medium", ":speech_balloon:"), "claim_changed": ("medium", ":speech_balloon:"), "claim_removed": ("low", ":speech_balloon:"),
    "positioning_changed": ("medium", ":dart:"), "new_urls": ("low", ":link:"),
}


def ensure_dirs():
    for d in (WATCH_DIR, STATE_DIR, PREPARED_DIR, EXTRACT_DIR, SITEMAP_DIR):
        os.makedirs(d, exist_ok=True)


def load_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def append_jsonl(path, obj):
    with open(path, "a") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def read_jsonl(path):
    out = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    except OSError:
        pass
    return out


def snapshot_dates():
    try:
        return sorted(d for d in os.listdir(SNAPSHOT_DIR) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d))
    except OSError:
        return []


def previous_snapshot(date_str):
    ds = [d for d in snapshot_dates() if d < date_str]
    return ds[-1] if ds else None


def snapshot_texts(date_str, key):
    """All page texts of one competitor in one snapshot, as {label: text}. Tolerates old file layouts."""
    d = os.path.join(SNAPSHOT_DIR, date_str)
    candidates = [f"{key}.json", f"{key}-raw.json"]
    alias = {"fourgeeks": ["4geeks.json"], "lewagon": ["le-wagon.json"], "nuclio": ["nuclioschool.json"],
             "spiced": ["spicedacademy.json"]}
    candidates += alias.get(key, [])
    for c in candidates:
        p = os.path.join(d, c)
        data = load_json(p)
        if not data:
            continue
        out = {}
        pages = data.get("pages") if isinstance(data, dict) else None
        if isinstance(pages, dict):
            for label, pg in pages.items():
                if isinstance(pg, dict):
                    t = pg.get("text") or ""
                    if t:
                        out[label] = t
                elif isinstance(pg, str):
                    out[label] = pg
            return out
        # old formats (v1 OpenClaw era, structured extractions with `variants`, `short_courses` ...):
        # collect "text" strings if any, otherwise use the whole JSON as one searchable blob so program
        # names can still be found by the backfill.
        def walk(o, prefix="p"):
            if isinstance(o, dict):
                for k, v in o.items():
                    if k == "text" and isinstance(v, str) and v:
                        out[f"{prefix}"] = v
                    else:
                        walk(v, f"{prefix}.{k}")
            elif isinstance(o, list):
                for i, v in enumerate(o):
                    walk(v, f"{prefix}[{i}]")
        walk(data)
        if not out:
            out["structured"] = json.dumps(data, ensure_ascii=False)
        return out
    return {}


def norm_name(s):
    s = (s or "").lower()
    s = s.replace("&", " and ")
    s = re.sub(r"[\(\)\[\]\"'“”‘’:,\.\-/|]", " ", s)
    s = re.sub(r"\b(bootcamp|bootcamps|program|programme|programm|course|curso|cours|master|máster|masters|en|in|de|with|mit|the|a|el|la|le|la|des|of|track)\b", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def norm_text(s):
    s = (s or "").lower()
    s = re.sub(r"[\s ]+", " ", s)
    s = re.sub(r"[“”\"'‘’`´]", "", s)
    return s.strip()


def similar(a, b):
    import difflib
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def today():
    return date.today().isoformat()


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def week_label(d):
    dt = date.fromisoformat(d)
    return f"{dt.strftime('%b')} {dt.day}"
