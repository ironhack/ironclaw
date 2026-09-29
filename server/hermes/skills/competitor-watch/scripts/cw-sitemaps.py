#!/usr/bin/env python3
"""cw-sitemaps.py - competitor site activity from sitemaps (the news proxy that actually works).

Fetches robots.txt -> sitemap(s) (or /sitemap.xml) for every competitor, stores the URL set for the
week, and diffs against the previous stored set: new URLs are grouped by section (programs / blog /
other). New program-like URLs are the earliest public signal of a launch; blog/news URLs show content
activity. Writes sitemaps/DATE/<key>.json and sitemaps/DATE/new-urls.json, prints a digest.

Usage: python3 cw-sitemaps.py [--date YYYY-MM-DD]
"""
import argparse
import gzip
import os
import re
import sys
import urllib.request
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cw_common import *  # noqa

UA = "Mozilla/5.0 (compatible; IronclawWatch/2.0; +https://www.ironhack.com)"
PROGRAM_HINTS = ["bootcamp", "program", "programme", "course", "curso", "cours", "formation", "master", "kurs", "career", "learn", "track", "academy", "ausbildung"]
CONTENT_HINTS = ["blog", "news", "press", "presse", "actualit", "article", "magazine", "event", "webinar", "ressources", "resources"]


def get(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
        if url.endswith(".gz") or r.headers.get("Content-Encoding") == "gzip" or data[:2] == b"\x1f\x8b":
            try:
                data = gzip.decompress(data)
            except OSError:
                pass
        return data.decode("utf-8", "ignore")


def sitemap_urls(site):
    """Return (list of sitemap urls tried, set of page urls)."""
    tried, urls = [], set()
    candidates = []
    try:
        robots = get(site.rstrip("/") + "/robots.txt", 15)
        candidates += re.findall(r"(?im)^\s*sitemap:\s*(\S+)", robots)
    except Exception:
        pass
    if not candidates:
        candidates = [site.rstrip("/") + "/sitemap.xml", site.rstrip("/") + "/sitemap_index.xml", site.rstrip("/") + "/sitemap-index.xml"]
    seen = set()
    queue = list(dict.fromkeys(candidates))
    while queue and len(seen) < 30:
        sm = queue.pop(0)
        if sm in seen:
            continue
        seen.add(sm)
        tried.append(sm)
        try:
            xml = get(sm)
        except Exception as e:  # noqa
            tried[-1] = f"{sm} (error: {str(e)[:60]})"
            continue
        subs = re.findall(r"<sitemap>.*?<loc>\s*(.*?)\s*</loc>", xml, re.S | re.I)
        if subs:
            queue += [s.strip() for s in subs]
        for loc in re.findall(r"<url>.*?<loc>\s*(.*?)\s*</loc>", xml, re.S | re.I):
            urls.add(loc.strip())
        if not subs and not urls and "<loc>" in xml:
            urls.update(l.strip() for l in re.findall(r"<loc>\s*(.*?)\s*</loc>", xml, re.S | re.I))
    return tried, urls


def classify(url):
    p = urlparse(url).path.lower()
    if any(h in p for h in CONTENT_HINTS):
        return "content"
    if any(h in p for h in PROGRAM_HINTS):
        return "program"
    depth = len([s for s in p.split("/") if s])
    return "other" if depth > 1 else "top"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=today())
    a = ap.parse_args()
    ensure_dirs()
    out_dir = os.path.join(SITEMAP_DIR, a.date)
    os.makedirs(out_dir, exist_ok=True)
    prev_dates = sorted(d for d in os.listdir(SITEMAP_DIR) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) and d < a.date)
    prev_dir = os.path.join(SITEMAP_DIR, prev_dates[-1]) if prev_dates else None
    summary = {"date": a.date, "previous": prev_dates[-1] if prev_dates else None, "competitors": {}}
    digest = [f"# Site activity (sitemaps) {a.date}" + (f" vs {prev_dates[-1]}" if prev_dates else " (first run, no diff)")]
    for key, comp in COMPETITORS.items():
        tried, urls = sitemap_urls(comp["site"])
        rec = {"name": comp["name"], "sitemaps": tried, "url_count": len(urls), "urls": sorted(urls)}
        save_json(os.path.join(out_dir, f"{key}.json"), rec)
        new, gone = [], []
        if prev_dir:
            old = set((load_json(os.path.join(prev_dir, f"{key}.json"), {}) or {}).get("urls", []))
            if old and urls:
                new = sorted(urls - old)
                gone = sorted(old - urls)
        groups = {}
        for u in new:
            groups.setdefault(classify(u), []).append(u)
        summary["competitors"][key] = {"url_count": len(urls), "new": new, "gone": gone, "new_by_type": groups,
                                       "error": None if urls else "no sitemap urls"}
        if not urls:
            digest.append(f"- {comp['name']}: no sitemap found ({tried[-1] if tried else 'nothing tried'})")
            continue
        line = f"- {comp['name']}: {len(urls)} URLs"
        if prev_dir:
            line += f", {len(new)} new, {len(gone)} gone"
            for t in ("program", "top", "content", "other"):
                if groups.get(t):
                    line += f"; new {t}: " + ", ".join(urlparse(u).path for u in groups[t][:5]) + (" ..." if len(groups[t]) > 5 else "")
        digest.append(line)
    save_json(os.path.join(out_dir, "new-urls.json"), summary)
    print("\n".join(digest))


if __name__ == "__main__":
    main()
