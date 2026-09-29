# Delta Comparison Script Template

Full working delta comparison script. Compares today's snapshots against
the previous week, detects 404 pages, content changes, new/removed pages,
and saves structured JSON output.

## Script

Save to a file and run (do NOT use `python3 -c` or heredocs with `&`
in strings — shell backgrounding detection triggers on `&` even inside
quoted strings):

```python
import json, os, difflib

today_dir = "/home/openclaw/ironclaw-data/workspace/competitor-snapshots/YYYY-MM-DD"
prev_dir = "/home/openclaw/ironclaw-data/workspace/competitor-snapshots/YYYY-MM-DD"  # previous week

competitors = ["lewagon", "nuclio", "neuefische", "spiced", "fourgeeks", "masterschool", "liora"]

delta_report = {"comparison": f"{prev_dir.split('/')[-1]} vs {today_dir.split('/')[-1]}", "deltas": {}}

for comp in competitors:
    today_path = os.path.join(today_dir, f"{comp}.json")
    prev_path = os.path.join(prev_dir, f"{comp}.json")

    if not os.path.exists(today_path):
        delta_report["deltas"][comp] = {"error": "missing from today", "new_pages": [], "removed_pages": [], "changed_pages": [], "unchanged_pages": [], "404_pages_removed": [], "empty_pages_change": []}
        continue
    if not os.path.exists(prev_path):
        delta_report["deltas"][comp] = {"error": "no previous data", "new_pages": [], "removed_pages": [], "changed_pages": [], "unchanged_pages": [], "404_pages_removed": [], "empty_pages_change": []}
        continue

    with open(today_path) as f:
        today_data = json.load(f)
    with open(prev_path) as f:
        prev_data = json.load(f)

    today_pages = today_data.get("pages", {})
    prev_pages = prev_data.get("pages", {})

    result = {"new_pages": [], "removed_pages": [], "changed_pages": [], "unchanged_pages": [], "404_pages_removed": [], "empty_pages_change": []}

    # New pages
    for key in set(today_pages) - set(prev_pages):
        result["new_pages"].append(key)

    # Removed pages
    for key in set(prev_pages) - set(today_pages):
        result["removed_pages"].append(key)

    # Compare shared pages
    for key in set(today_pages) & set(prev_pages):
        t_text = today_pages[key].get("text", "")
        p_text = prev_pages[key].get("text", "")

        # Empty page handling
        if not t_text and p_text:
            result["empty_pages_change"].append(key)
            continue
        if t_text and not p_text:
            result["changed_pages"].append(key)
            continue
        if not t_text and not p_text:
            result["unchanged_pages"].append(key)
            continue

        s = difflib.SequenceMatcher(None, p_text, t_text, autojunk=False)
        ratio = s.ratio()

        not_found_phrases = [
            'cannot be found', 'not found', 'nicht gefunden', 'page not found',
            'seite kann nicht gefunden', '404', 'no encontrado', 'non trouve',
            'nicht gefunden werden'
        ]
        t_is_404 = any(phrase in t_text[:500].lower() for phrase in not_found_phrases)
        p_is_404 = any(phrase in p_text[:500].lower() for phrase in not_found_phrases)

        if t_is_404 and p_is_404:
            # Both sides are 404 — persistent removal. 404 templates often contain
            # dynamic content (course start dates, nav listings) that varies week to
            # week, pushing similarity below 0.85. Check both sides to catch this.
            result["404_pages_removed"].append(key)
        elif t_is_404 and (0.70 <= ratio <= 0.85 or len(t_text) < 0.3 * max(len(p_text), 1)):
            # First-time 404 detection: today's page turned to 404. The 70-80% band
            # catches 404 templates that still mirror the old page (nav+footer
            # boilerplate). But a SHORT 404 template (e.g. uniform 1411 chars vs a
            # 13K-27K original, or a 37-char "Page not found" stub) drops ratio far
            # below 0.70 and falls through to "changed_pages". The length-disparity
            # check catches those: 404 text + today <30% of last week's length =
            # removal. Observed 2026-08-10: neuefische 5 course pages (uniform
            # 1411-char 404 templates) and spiced course-cyber-security (37 chars)
            # were misclassified as "changed" without this branch.
            result["404_pages_removed"].append(key)
        elif ratio < 0.85:
            result["changed_pages"].append(key)
        else:
            result["unchanged_pages"].append(key)

    delta_report["deltas"][comp] = result

# Save
output_path = os.path.join(today_dir, "delta-analysis.json")
with open(output_path, 'w') as f:
    json.dump(delta_report, f, indent=2)

print(f"Delta report saved to {output_path}")
for comp in competitors:
    d = delta_report["deltas"].get(comp, {})
    changed = len(d.get("changed_pages", []))
    new = len(d.get("new_pages", []))
    removed = len(d.get("removed_pages", [])) + len(d.get("404_pages_removed", []))
    if changed or new or removed:
        print(f"  {comp}: {changed} changed, {new} new, {removed} removed")
```

## Output Format

```json
{
  "comparison": "2026-06-29 vs 2026-07-06",
  "deltas": {
    "lewagon": {
      "new_pages": [],
      "removed_pages": [],
      "changed_pages": ["home-fr"],
      "unchanged_pages": ["home", "home-es", ...],
      "404_pages_removed": [],
      "empty_pages_change": []
    },
    ...
  }
}
```

## Enriched Delta Output — separate verified changes from capture noise

The basic `deltas` lists alone will mislead the report generator: on a
method-drift week the char-level pass flags 10+ pages "changed" when zero
real changes occurred. After running the hunk-diff verification, rewrite
`delta-analysis.json` with three extra top-level keys so the distinction
survives to the report and to future weeks (observed 2026-09-14):

```json
{
  "comparison": "2026-09-07 vs 2026-09-14",
  "deltas": { "spiced": { "changed_pages": [...], "unchanged_pages": [...] } },
  "verified_real_changes": {
    "spiced": ["course-ai-architect: language added (English) + first cohort 18 Jan 2027"],
    "liora": ["homepage promo banner swapped to live Q&A on Cybersecurity/Cloud/Dev"]
  },
  "rejected_as_capture_artifacts": {
    "note": "flagged changed by char-level diff but verified UNCHANGED via method-matched re-fetch + word-level hunk diff",
    "lewagon": ["business", "home", "home-fr"],
    "masterschool": ["programs"],
    "nuclio": ["masters"]
  },
  "method_note": "SequenceMatcher autojunk=False; word-stream hunk diffs; method-matched re-fetches for cross-week source drift"
}
```

`verified_real_changes` is the ONLY thing the report's Delta section should
narrate. `rejected_as_capture_artifacts` is what the report cites when it
says "flagged changed but confirmed unchanged". A delta-analysis.json that
carries these keys is auditable; one that only carries `deltas` invites a
misleading "N pages changed" headline next week.

## CRITICAL BUG FIXED 2026-09-14 — `autojunk=True` produces garbage ratios

`difflib.SequenceMatcher` defaults to `autojunk=True`, which treats any
character appearing in more than 1% of a sequence longer than 200 chars
as "popular" junk and ignores it. On multi-thousand-char page text this
destroys the ratio: the most common characters (space, `e`, `a`, `n`)
are all discarded, so two *nearly identical* pages can score far below
the 0.85 threshold and be reported as "changed".

Observed 2026-09-14: spiced `programs` page scored **0.156** while being
byte-for-byte identical apart from one cohort date; spiced `home-de`
scored 0.696 at identical length (9,569 vs 9,570 chars). Seven
competitors' pages were falsely flagged "changed" on this basis, and
the false flags survived into a first draft of the delta narrative.
The skill's script template shipped with `autojunk=True` (i.e. the
default) and has now been fixed to `autojunk=False`.

**Always pass `autojunk=False`** for the char-level pass. Then confirm
every surviving flag with the word-level hunk diff
(`scripts/hunk-diff.py`, which already uses `autojunk=False`).

## Capture-Method Drift — the dominant false-positive source

Char-ratio deltas are only meaningful when both weeks were captured by
the SAME method. Phase 1 flips between `camoufox` and `curl-fallback`
depending on which pages fail, and Camoufox yields materially less on
some pages. Observed 2026-09-14: last week was curl-heavy, this week
Camoufox-heavy, and 13 shared pages showed 0.37–0.84 char ratios that
were pure method artefacts (e.g. liora `home-fr` 30,293 → 7,566).

**Mandatory step before asserting any change:** for every flagged page
whose `source` field differs between the two snapshot dirs, re-fetch it
with LAST week's method (usually `curl` + HTML strip, matching
`Accept-Language`), then word-diff that fresh text against last week's
stored text. Yields within ~3% and word-ratio >0.98 mean unchanged.
On 2026-09-14 this rejected 14 of 15 flagged pages; the only real
findings were a promo-banner swap (Liora) and cohort/language edits
(Spiced).

## Pitfall: Shell Backgrounding Detection

Do NOT run this script inline with `python3 -c "..."` or `python3 << 'PYEOF'`
if it contains the `&` character (e.g., in `non trouvé`). The shell detects
`&` as a backgrounding operator even inside quoted strings in some contexts.
Always write the script to a file first with `write_file`, then run it with
`python3 /path/to/script.py`.
