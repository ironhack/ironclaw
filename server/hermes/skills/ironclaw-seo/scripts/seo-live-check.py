#!/usr/bin/env python3
"""seo-live-check.py - deterministic live metadata check of the key Ironhack pages.

Checks the 5 market homepages and the course pages per market: HTTP status, title
(+length), meta description length, canonical, OG tag count, hreflang count + x-default,
schema types, robots meta. Emits JSON with a list of pages and a list of human-readable
issues (title too short/long/duplicate, missing description, OG missing, hreflang missing,
non-200 course page).

Usage: python3 seo-live-check.py [--out live-check.json] [--courses web-development,data-analytics,...]
"""
import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter

MARKETS = {"esp": "es-en", "deu": "de-en", "fra": "fr-en", "nld": "nl-en", "prt": "pt-en"}
CODES = {"esp": "ES", "deu": "DE", "fra": "FR", "nld": "NL", "prt": "PT"}
DEFAULT_COURSES = ["web-development", "data-analytics", "ux-ui-design", "cybersecurity", "ai-engineering"]
SITE = "https://www.ironhack.com"


def fetch(url):
    r = subprocess.run(["curl", "-sL", "-A", "Mozilla/5.0 (compatible; IronclawSEO/1.0)", "-o", "-",
                        "-w", "\n__STATUS__:%{http_code}", url], capture_output=True, text=True, timeout=25)
    out = r.stdout
    m = re.search(r"__STATUS__:(\d+)\s*$", out)
    status = int(m.group(1)) if m else 0
    return status, out[: m.start()] if m else out


def check(url, market, kind):
    try:
        status, html = fetch(url)
    except Exception as e:  # noqa
        return {"market": CODES[market], "kind": kind, "url": url, "path": url.replace(SITE, ""), "status": 0, "error": str(e)}
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    title = re.sub(r"\s+", " ", m.group(1)).strip() if m else None
    m = re.search(r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']*)["\']', html, re.I)
    desc = m.group(1) if m else None
    m = re.search(r'<link\s+rel=["\']canonical["\']\s+href=["\']([^"\']*)["\']', html, re.I)
    canonical = m.group(1) if m else None
    ogs = re.findall(r'<meta\s+property=["\']og:([^"\']+)["\']\s+content=["\']([^"\']*)["\']', html, re.I)
    hl = re.findall(r'<link\s+rel=["\']alternate["\']\s+hreflang=["\']([^"\']+)["\']', html, re.I)
    schema = sorted(set(re.findall(r'"@type"\s*:\s*"([^"]+)"', html)))
    m = re.search(r'<meta\s+name=["\']robots["\']\s+content=["\']([^"\']*)["\']', html, re.I)
    robots = m.group(1) if m else None
    canon_ok = bool(canonical) and canonical.rstrip("/") == url.rstrip("/")
    return {
        "market": CODES[market], "kind": kind, "url": url, "path": url.replace(SITE, ""), "status": status,
        "title": title, "title_len": len(title or ""), "desc_len": len(desc or ""), "desc": (desc or "")[:160],
        "canonical": canonical, "canonical_ok": canon_ok, "og_count": len(ogs),
        "og_keys": sorted(set(k.lower() for k, _ in ogs)), "hreflang_count": len(hl),
        "x_default": any(h.lower() == "x-default" for h in hl), "schema": schema, "robots": robots,
    }


REDIRECT_MAPS = {
    "wd": os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "references", "wd-redirect-map.json"),
    "ux": os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "references", "ux-redirect-map.json"),
}


def norm(u):
    return (u or "").rstrip("/").lower()


def check_redirect(track, src):
    """Does the legacy URL still 301/308 to its expected destination? (no -L: we want the first hop)"""
    url, expected = src["url"], src.get("destination", "")
    try:
        r = subprocess.run(["curl", "-s", "-o", "/dev/null", "-A", "Mozilla/5.0 (compatible; IronclawSEO/1.0)",
                            "-w", "%{http_code} %{redirect_url}", url], capture_output=True, text=True, timeout=20)
        code, _, loc = r.stdout.strip().partition(" ")
        code = int(code or 0)
    except Exception as e:  # noqa
        return {"track": track, "source": url, "expected": expected, "status": 0, "location": "", "ok": False, "error": str(e)}
    ok = code in (301, 308) and (not expected or norm(loc) == norm(expected))
    return {"track": track, "source": url, "expected": expected, "status": code, "location": loc, "ok": ok}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="-")
    ap.add_argument("--courses", default=",".join(DEFAULT_COURSES))
    ap.add_argument("--no-redirects", action="store_true", help="skip the legacy-URL redirect checks")
    a = ap.parse_args()
    courses = [c for c in a.courses.split(",") if c]
    pages = []
    for mk, seg in MARKETS.items():
        pages.append(check(f"{SITE}/{seg}", mk, "homepage"))
        for c in courses:
            pages.append(check(f"{SITE}/{seg}/{c}", mk, f"course:{c}"))

    redirects = []
    if not a.no_redirects:
        for track, path in REDIRECT_MAPS.items():
            try:
                m = json.load(open(path))
            except (OSError, json.JSONDecodeError):
                continue
            for src in m.get("sources", []):
                redirects.append(check_redirect(track, src))

    issues = []
    for rd in redirects:
        if not rd["ok"]:
            issues.append(f"REDIRECT BROKEN ({rd['track'].upper()}): {rd['source'].replace(SITE, '')} -> HTTP {rd['status']} "
                          f"{(rd['location'] or 'no Location').replace(SITE, '')} (expected {rd['expected'].replace(SITE, '')})")
    for p in pages:
        tag = f"{p['market']} {p['path']}"
        if p["status"] != 200:
            issues.append(f"{tag}: HTTP {p['status']}")
            continue
        if not p.get("title"):
            issues.append(f"{tag}: title MISSING")
        elif p["title_len"] < 30:
            issues.append(f"{tag}: title too short ({p['title_len']}c) \"{p['title']}\"")
        elif p["title_len"] > 65:
            issues.append(f"{tag}: title too long ({p['title_len']}c)")
        if p["desc_len"] == 0:
            issues.append(f"{tag}: meta description MISSING")
        elif p["desc_len"] < 70:
            issues.append(f"{tag}: meta description short ({p['desc_len']}c)")
        if p["og_count"] == 0:
            issues.append(f"{tag}: no OG tags")
        elif not {"title", "description", "image"} <= set(p["og_keys"]):
            issues.append(f"{tag}: OG incomplete ({', '.join(p['og_keys'])})")
        if p["hreflang_count"] == 0:
            issues.append(f"{tag}: no hreflang")
        elif not p["x_default"]:
            issues.append(f"{tag}: hreflang without x-default")
        if not p["canonical_ok"]:
            issues.append(f"{tag}: canonical {'missing' if not p['canonical'] else 'differs: ' + p['canonical']}")
        if p["robots"] and "noindex" in p["robots"].lower():
            issues.append(f"{tag}: robots {p['robots']}")
    # duplicate titles across markets, per kind
    for kind in set(p["kind"] for p in pages):
        titles = Counter(p["title"] for p in pages if p["kind"] == kind and p.get("title") and p["status"] == 200)
        for t, n in titles.items():
            if n > 1:
                mk = [p["market"] for p in pages if p["kind"] == kind and p.get("title") == t]
                issues.append(f"duplicate {kind} title across {', '.join(mk)}: \"{t[:70]}\"")

    out = {"pages": pages, "issues": issues, "redirects": redirects,
           "summary": {"pages": len(pages), "non_200": len([p for p in pages if p['status'] != 200]),
                       "no_og": len([p for p in pages if p.get('og_count') == 0 and p['status'] == 200]),
                       "redirects_checked": len(redirects), "redirects_broken": len([r for r in redirects if not r["ok"]]),
                       "issues": len(issues)}}
    s = json.dumps(out, indent=2, ensure_ascii=False)
    if a.out == "-":
        print(s)
    else:
        with open(a.out, "w") as f:
            f.write(s)
        print(f"live check: {out['summary']}", file=sys.stderr)


if __name__ == "__main__":
    main()
