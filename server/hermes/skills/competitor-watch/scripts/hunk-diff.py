#!/usr/bin/env python3
"""Word-level hunk diff between two competitor-watch snapshot dirs.

Separates REAL content changes from capture noise (alumni-carousel rotation,
lazy-loaded sections, nav reorder, title-case changes) that page-level char
ratios cannot distinguish.

Usage:
    python3 hunk-diff.py <prev_dir> <today_dir> [competitor1 competitor2 ...]

Reads <dir>/<competitor>.json files (pages.<key>.text), compares prev vs today
per shared page with a whitespace word-stream SequenceMatcher, and prints only
non-equal opcodes. Replace hunks shorter than 4 words on each side are skipped
as formatting shuffle. Output capped at 14 hunks per page.

2026-09-07 validation: lewagon 7/9 + fourgeeks 6/6 + neuefische 9/10 pages
flagged "changed" by the char-level delta were almost all noise; the single
true finding (spiced program-card swap) surfaced as a clean 2-hunk REP while
noise pages showed 10-25 hunks of alumni-name/case churn.
"""
import json, difflib, os, sys


def words(t):
    return t.split()


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    prev_dir, today_dir = sys.argv[1], sys.argv[2]
    competitors = sys.argv[3:] or [
        "lewagon", "nuclio", "neuefische", "spiced", "fourgeeks",
        "masterschool", "liora",
    ]

    for comp in competitors:
        tp = os.path.join(today_dir, f"{comp}.json")
        pp = os.path.join(prev_dir, f"{comp}.json")
        if not (os.path.exists(tp) and os.path.exists(pp)):
            continue
        t = json.load(open(tp)).get("pages", {})
        p = json.load(open(pp)).get("pages", {})
        for key in sorted(set(t) & set(p)):
            tt = t[key].get("text", "")
            pt = p[key].get("text", "")
            if not tt or not pt:
                continue
            if difflib.SequenceMatcher(None, pt, tt).ratio() >= 0.85:
                continue
            tw, pw = words(tt), words(pt)
            sm = difflib.SequenceMatcher(None, pw, tw, autojunk=False)
            real = []
            for tag, i1, i2, j1, j2 in sm.get_opcodes():
                if tag == "equal":
                    continue
                removed = " ".join(pw[i1:i2])
                added = " ".join(tw[j1:j2])
                if tag == "replace" and len(pw[i1:i2]) < 4 and len(tw[j1:j2]) < 4:
                    continue  # formatting shuffle
                real.append((tag, removed[:180], added[:180]))
            if real:
                print(f"\n##### {comp} / {key}  (word-ratio {sm.ratio():.2f}, {len(real)} hunks)")
                for tag, rm, ad in real[:14]:
                    if tag == "insert":
                        print(f"  + ADD: {ad}")
                    elif tag == "delete":
                        print(f"  - DEL: {rm}")
                    else:
                        print(f"  ~ REP: '{rm}' -> '{ad}'")
                if len(real) > 14:
                    print(f"  ... ({len(real) - 14} more hunks)")


if __name__ == "__main__":
    main()
