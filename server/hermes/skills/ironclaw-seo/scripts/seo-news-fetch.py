#!/usr/bin/env python3
"""seo-news-fetch.py - pull SEO / Google Search news headlines from Google News RSS.

Deterministic research input for the agent: it selects and interprets, it does not search.
Usage: python3 seo-news-fetch.py [--days 10] [--out news.json]
"""
import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

QUERIES = [
    "Google algorithm update SEO",
    "Google core update ranking volatility",
    "AI Overviews SEO traffic",
    "AI Mode Google search publishers",
    "generative engine optimization GEO",
    "Google Search Console",
]
PREFERRED = ["searchengineland", "seroundtable", "searchenginejournal", "blog.google", "developers.google",
             "thekeyword", "searchengineroundtable", "semrush", "ahrefs", "moz.com", "ppc.land"]


def fetch(q):
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": q, "hl": "en-US", "gl": "US", "ceid": "US:en"})
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (IronclawSEO)"})
    xml = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")
    items = []
    for it in re.findall(r"<item>(.*?)</item>", xml, re.S):
        def g(tag):
            m = re.search(rf"<{tag}>(.*?)</{tag}>", it, re.S)
            return (m.group(1) if m else "").strip()
        title = re.sub(r"<!\[CDATA\[|\]\]>", "", g("title"))
        src = re.sub(r"<[^>]+>", "", re.search(r"<source[^>]*>(.*?)</source>", it, re.S).group(1)) if "<source" in it else ""
        link = g("link")
        try:
            dt = parsedate_to_datetime(g("pubDate"))
        except Exception:  # noqa
            dt = None
        # Google News titles end with " - Source"
        title = re.sub(r"\s+-\s+[^-]+$", "", title) if src and title.endswith(src) else title
        items.append({"title": title, "source": src, "link": link, "date": dt.isoformat() if dt else "", "query": q})
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=10)
    ap.add_argument("--out", default="-")
    a = ap.parse_args()
    cutoff = datetime.now(timezone.utc) - timedelta(days=a.days)
    seen, out = set(), []
    for q in QUERIES:
        try:
            for it in fetch(q):
                key = re.sub(r"\W+", " ", it["title"].lower()).strip()[:80]
                if key in seen or not it["title"]:
                    continue
                if it["date"]:
                    try:
                        if datetime.fromisoformat(it["date"]) < cutoff:
                            continue
                    except ValueError:
                        pass
                seen.add(key)
                it["preferred"] = any(p in (it["source"] or "").lower() or p in it["link"].lower() for p in PREFERRED)
                out.append(it)
        except Exception as e:  # noqa
            print(f"news: query failed '{q}': {e}", file=sys.stderr)
    out.sort(key=lambda x: (not x["preferred"], x["date"]), reverse=False)
    out.sort(key=lambda x: (0 if x["preferred"] else 1, -(datetime.fromisoformat(x["date"]).timestamp() if x["date"] else 0)))
    out = out[:40]
    s = json.dumps(out, indent=2, ensure_ascii=False)
    if a.out == "-":
        print(s)
    else:
        with open(a.out, "w") as f:
            f.write(s)
        print(f"news: {len(out)} headlines", file=sys.stderr)


if __name__ == "__main__":
    main()
