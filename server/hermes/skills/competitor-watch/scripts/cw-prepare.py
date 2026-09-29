#!/usr/bin/env python3
"""cw-prepare.py - turn today's raw snapshot into extraction-ready text + capture quality flags.

For every competitor:
  * capture quality per page: compares text length with the page's median over the last 4 captures;
    empty  = no text; degraded = < 40% of median (method drift / partial render); ok otherwise
  * boilerplate stripping: lines that appear on >= 60% of the competitor's pages (nav, footer, cookie
    banner) are removed once and listed separately, so the extractor reads content, not chrome
  * writes prepared/DATE/<key>.txt (headed by page label + URL, capped per page) and prepared/DATE/index.json
  * updates captures.json (history of lengths) and prints a digest for the agent

Usage: python3 cw-prepare.py [--date YYYY-MM-DD] [--cap 7000]
"""
import argparse
import os
import re
import statistics
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cw_common import *  # noqa


def split_lines(text):
    return [re.sub(r"\s+", " ", l).strip() for l in text.splitlines()]


def prepare(date_str, cap, budget=60000):
    ensure_dirs()
    captures = load_json(CAPTURES_PATH, {}) or {}
    out_dir = os.path.join(PREPARED_DIR, date_str)
    os.makedirs(out_dir, exist_ok=True)
    index = {"date": date_str, "competitors": {}}
    digest = [f"# Competitor watch capture digest {date_str}"]
    prev = previous_snapshot(date_str)
    for key, comp in COMPETITORS.items():
        pages = snapshot_texts(date_str, key)
        raw = load_json(os.path.join(SNAPSHOT_DIR, date_str, f"{key}.json"), {}) or {}
        urls = {label: (pg.get("url") if isinstance(pg, dict) else "") for label, pg in (raw.get("pages") or {}).items()}
        hist = captures.setdefault(key, {})
        quality = {}
        for label in set(pages) | set(urls):
            text = pages.get(label, "")
            n = len(text)
            past = [h.get(label, 0) for d, h in sorted(hist.items())[-4:] if d != date_str]
            past = [p for p in past if p > 0]
            med = statistics.median(past) if past else 0
            if n == 0:
                q = "empty"
            elif med and n < 0.4 * med:
                q = "degraded"
            elif med and n > 2.5 * med:
                q = "grown"
            else:
                q = "ok"
            quality[label] = {"len": n, "median": int(med), "quality": q, "url": urls.get(label, "")}
        hist[date_str] = {label: v["len"] for label, v in quality.items()}
        # boilerplate: lines on >= 60% of pages (min 3 pages)
        good = {l: t for l, t in pages.items() if t}
        line_counts = Counter()
        for t in good.values():
            for l in set(x for x in split_lines(t) if len(x) >= 4):
                line_counts[l] += 1
        boiler = set()
        if len(good) >= 3:
            boiler = {l for l, c in line_counts.items() if c >= max(2, int(0.6 * len(good)))}
        # write prepared text
        parts = [f"# {comp['name']} ({key}) - snapshot {date_str}", f"Site: {comp['site']}  Markets: {', '.join(comp['markets'])}", ""]
        if boiler:
            parts.append("## Shared page chrome (nav/footer/cookie text present on most pages, shown once)")
            parts.append(" | ".join(sorted(boiler, key=lambda s: -len(s))[:60])[:3000])
            parts.append("")
        total_kept = 0
        # adaptive cap: a competitor with few pages gets longer pages (budget / pages, never below cap)
        page_cap = max(cap, budget // max(1, len(good)))
        for label, text in sorted(good.items()):
            kept = [l for l in split_lines(text) if l and l not in boiler]
            body = "\n".join(kept)
            body = re.sub(r"\n{3,}", "\n\n", body)
            if len(body) > page_cap:
                body = body[:page_cap] + f"\n[... truncated, {len(body) - page_cap} more chars]"
            total_kept += len(body)
            parts.append(f"## page: {label}  ({quality[label]['url']})  quality={quality[label]['quality']} chars={len(text)}")
            parts.append(body)
            parts.append("")
        with open(os.path.join(out_dir, f"{key}.txt"), "w") as f:
            f.write("\n".join(parts))
        n_ok = sum(1 for v in quality.values() if v["quality"] in ("ok", "grown"))
        n_deg = sum(1 for v in quality.values() if v["quality"] == "degraded")
        n_empty = sum(1 for v in quality.values() if v["quality"] == "empty")
        if not quality:
            comp_quality = "bad"          # no file / no pages at all: the scrape did not reach this competitor
        else:
            comp_quality = "ok" if n_empty + n_deg == 0 else ("partial" if n_ok >= max(1, len(quality) // 2) else "bad")
        index["competitors"][key] = {"name": comp["name"], "pages": quality, "pages_ok": n_ok, "pages_degraded": n_deg,
                                     "pages_empty": n_empty, "quality": comp_quality, "prepared_chars": total_kept,
                                     "boilerplate_lines": len(boiler)}
        flag = {"ok": ":large_green_circle:", "partial": ":large_yellow_circle:", "bad": ":red_circle:"}[comp_quality]
        bad_pages = [f"{l} ({v['quality']})" for l, v in quality.items() if v["quality"] in ("empty", "degraded")]
        digest.append(f"- {comp['name']}: {n_ok}/{len(quality)} pages ok, {total_kept:,} prepared chars, capture {comp_quality}"
                      + (" - NO CAPTURE (scrape did not write a file)" if not quality else "")
                      + (f" - {', '.join(bad_pages[:6])}" if bad_pages else ""))
    save_json(os.path.join(out_dir, "index.json"), index)
    save_json(CAPTURES_PATH, captures)
    digest.append(f"Previous snapshot: {prev or 'none'}. Prepared texts: {out_dir}/<key>.txt")
    print("\n".join(digest))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=today())
    ap.add_argument("--cap", type=int, default=7000, help="minimum per-page cap after boilerplate stripping")
    ap.add_argument("--budget", type=int, default=60000, help="chars per competitor; per-page cap = max(cap, budget/pages)")
    a = ap.parse_args()
    prepare(a.date, a.cap, a.budget)
