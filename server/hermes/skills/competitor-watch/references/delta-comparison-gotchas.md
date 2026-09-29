# Delta Comparison Gotchas

Known edge cases encountered during weekly competitor-watch runs.

## Empty Previous Snapshot Directory

The Phase 1 fetch script creates a `YYYY-MM-DD/` directory, writes `manifest.json`,
then writes individual competitor `*.json` files. If Phase 1 crashed partway through
or was interrupted, the directory may exist but contain only `manifest.json` with
zero data files.

**Observed 2026-06-19:** The `2026-06-18` directory existed but was empty (0 data
files). Fallback was to `2026-06-15` for Le Wagon and `2026-05-25` for all others.

**Impact on delta:** The comparison spans 25+ days instead of 1 week. Changes are
more likely to be cumulative (multiple changes bundled together). Flag the delta as
"Medium" confidence.

## Snapshot Format Changes

The competitor JSON files have changed internal structure between runs:

- **Previous format** (2026-05-25): Used a `variants` key with structured fields per
  language/region variant.
- **Current format** (2026-06-15+): Uses a `pages` key with `{url, text, text_len}` per
  page key.

When the schema differs, field-level diffing is impossible. Compare by content/text
parsing instead. Note the format change in the report so readers know delta was done
at content level.

## Missing Competitor Snapshots

If a competitor's `*.json` file is missing from today's directory, the Phase 1
fetch may have hit a timeout or CAPTCHA. For that competitor:

1. Note in report: "Competitor X was not fetched today — no delta available."
2. Keep the previous snapshot data for reference in the Product Catalog section.
3. Do not fabricate course data for the missing competitor.

## Persistent 404 Pages Across Weeks

When a course page returns 404 once, it might be a transient issue. When the
**same pages return 404 for 3+ consecutive weeks**, the URLs have been
intentionally removed or restructured — they are not coming back.

**Observed 2026-06-29 through 2026-07-27:** Neue Fische had the same 5 course
pages return 404 every week (data-science, ai-ml, cloud-computing,
ai-data-strategy, bootcamps listing at `/bootcamp`).

### Pitfall: Both-Sides-404 Detection

The delta comparison script's 404 detection used to only check today's text
for 404 indicators. For **persistent** 404s where BOTH this week's and last
week's pages are 404 templates, the similarity ratio could fall below 0.85 due
to dynamic content in the 404 page's navigation (changing course start dates,
promoted courses, etc.) — causing persistent 404s to be misclassified as
"changed" rather than "404_pages_removed."

**Fix (applied 2026-07-27):** The comparison script now checks BOTH today's
and previous page text for 404 phrases. If both contain 404 language,
classify as `404_pages_removed` regardless of the similarity ratio.

```python
t_is_404 = any(phrase in t_text[:500].lower() for phrase in not_found_phrases)
p_is_404 = any(phrase in p_text[:500].lower() for phrase in not_found_phrases)

if t_is_404 and p_is_404:
    # Both sides are 404 templates — persistent removal
    result["404_pages_removed"].append(key)
```

**Observed impact:** On 2026-07-27, Neue Fische's 5 persistent 404 pages were
misclassified as "changed" before this fix. After the fix, they correctly land
in `404_pages_removed`.

**What to do with persistent 404s:**
- Week 1: Report as "removed (404)" in delta section — first detection
- Week 2: Report as "still 404 (unchanged)" — note the persistence
- Week 3+: Include a consolidated note: "X course URLs have been 404 for N
  consecutive weeks — likely intentional restructuring." Check the competitor's
  home page or programs listing for replacement URLs, and compare the course
  catalog manually rather than relying on difflib for pages that never change.

## Combined Camoufox + Curl Failure (JS SPA Detection)

When both Phase 1 (Camoufox) and Phase 2 curl fallback return empty content
(0 chars or <200 chars), the page is almost certainly a **client-side rendered
JavaScript SPA** (React, Vue, Angular) that curl cannot render.

**Observed 2026-07-20:** 4Geeks Academy Spanish homepage (`/es`) returned empty
text from both Camoufox (timeout) and curl (0 chars). The English homepage
(`/`) returned 15K+ chars via Camoufox. The Spanish page is a React SPA that
needs a full browser engine.

**Decision for unrecoverable pages:**
- Note the competitor's missing localised page in the report's Data Quality section
- Use the competitor's main-market page data as a proxy (e.g., 4Geeks EN page for
  ES market, noting that pricing/messaging may differ)
- Do not fabricate data or use prior-week data without explicitly flagging it
- These pages rarely resolve — consider removing them from the Phase 1 fetch URL
  list if they consistently fail for 4+ weeks

## Manifest.json as Canary

Before starting Phase 2 work, check `manifest.json`:

- If `manifest.json` is missing → Phase 1 did not run at all. Abort or run
  Camoufox fetches manually for each competitor.
- If `manifest.json` exists but all competitors show `pages_ok: 0` → Phase 1
  ran but every page fetch failed. Run targeted Camoufox fetches.
- If `manifest.json` shows some competitors with `pages_ok > 0` but others
  with 0 → Partial failure. Use available data + targeted fetches for gaps.

## 404 Pages Produce Misleading Delta Similarity

When a course detail page starts returning 404 (page removed or URL changed),
the 404 template often includes the site's full footer/navigation with course
listings. This causes `difflib.SequenceMatcher` to report similarity around
70-75% — well above the 0.85 "no change" threshold, so it flags as "changed"
rather than "empty" or "missing."

**Observed 2026-06-29:** Neue Fische had 5 course pages return 404
(Data Science, AI/ML, Cloud Computing, AI Strategy, Bootcamps listing).
All showed 74.1% similarity because the 404 template footer listed all
courses. Detection: check if pages with similarity in the 70-80% range
have `text_len` under ~3000 chars on one side but much larger on the other,
or if both contain the phrase "cannot be found" / "nicht gefunden werden."

**Detection heuristic for 404 pages:**
```python
if 0.70 <= ratio <= 0.80:
    # Check for common 404 indicators
    is_404 = any(phrase in today_text[:500].lower() for phrase in 
                 ['cannot be found', 'not found', 'nicht gefunden', 'page not found',
                  'seite kann nicht gefunden', '404'])
    if is_404:
        # This is a missing page, not a content change
        changes['missing_pages'].append(key)
        continue
```

Report 404 pages separately from genuine content changes in the delta
section — label them as "REMOVED (404)" rather than "changed."

## 404 Pages BELOW the 70% Similarity Band

The standard 404 detection only fires for pages with similarity in the
70-80% band (where the 404 template's nav/footer partially matches the
old rich page). When the old page had **very rich content** (10K+ chars
of course descriptions, curriculum, testimonials) and the 404 template
is **very sparse** (~800 chars of nav+footer only), the similarity can
fall **below 70%** — entirely bypassing the 404 detection.

This produces false "changed" classifications for pages that are actually
just 404.

**Observed 2026-07-27:** Neue Fische's 5 dead course pages (data-science,
ai-ml, cloud-computing, ai-strategy, bootcamps) were classified as
"changed" with similarity well below 0.70 because the previous week's
pages had 10K-25K chars of course content while today's 404 templates
had only ~800 chars of nav/footer. They never entered the 70-80% band.

**Fix — add a post-hoc 404 check outside the band:**
After the main comparison loop, scan any page classified as "changed"
that has text under the 404-template threshold:

```python
# Post-hoc: check "changed" pages for 404 even below 70% band
not_found_phrases = [
    'cannot be found', 'not found', 'nicht gefunden', 'page not found',
    'seite kann nicht gefunden', '404', 'no encontrado', 'non trouve',
    'nicht gefunden werden', 'seite nicht gefunden'
]
for key in list(result["changed_pages"]):
    t_text = today_pages[key].get("text", "")
    if len(t_text) < 3000:  # 404 template threshold
        is_404 = any(phrase in t_text[:500].lower() for phrase in not_found_phrases)
        if is_404:
            result["changed_pages"].remove(key)
            result["404_pages_removed"].append(key)
```

**Decision rule:** If a page's current text is under 3000 chars AND
contains 404 text, it's a dead page regardless of similarity ratio.
Move it from `changed_pages` to `404_pages_removed`.

**What this looks like in the report:** Instead of "5 pages changed"
for Neue Fische, the report says "5 pages now return 404 — possible
URL restructuring." This is more actionable: the agent knows to look
for replacement URLs on the homepage rather than trying to diff
the changed content.

## Extraction-Method Variance Inflates "Changed" Flags

When a page was recovered via `curl-fallback` this week but was captured
by Camoufox last week (or vice versa), `difflib` often reports < 0.85
similarity and flags the page "changed" even when nothing substantive
changed — the two extraction paths produce different text (curl's
html.parser output vs Camoufox's `inner_text`, and curl often captures
MORE of a page than a partial Camoufox capture, or a different amount of
nav/footer boilerplate). **Observed 2026-08-17:** lewagon home-fr/home-es,
nuclio home, fourgeeks 3 course pages, and spiced home-de all flagged
"changed" purely from recovery-method variance (e.g. nuclio home: 5.6K
chars via Camoufox last week vs 17.6K via curl this week).

**How to handle in the report:**
- Before reporting a "changed" page as a genuine finding, compare the two
  pages' `source` fields. If they differ (`curl-fallback` vs `camoufox` /
  `camoufox-retry`), the change is likely an extraction artifact — do NOT
  headline it as a real content change.
- State the honest framing once in the Delta section (e.g. "most 'changed'
  flags reflect recovery-method differences, not substantive changes") and
  reserve the delta narrative for genuine signals (404→recovered pages,
  new/removed pages, real URL remaps).
- Same method on the same URL both weeks (e.g. curl vs curl on a remapped
  new slug) → the similarity ratio IS a reliable change signal. Observed
  2026-08-17: neuefische course-cyber-security (27,271→17,654 chars) and
  course-cloud (13,523→16,808) changed genuinely; the 5 remapped course
  pages compared curl-vs-curl and their 0.98+ ratios correctly showed
  "unchanged".
- Length-inversion check: when a page's length shifts a lot AND the fetch
  method changed between weeks, read the first ~300 chars of both sides
  before writing the finding — a big length jump with a method change is
  usually capture-depth, not content change.

### Validation 2026-08-31: method cross-check discriminates within one competitor

4Geeks flagged ALL 6 pages "changed" — but the source-field cross-check
split them cleanly: the 3 pages fetched camoufox-vs-camoufox both weeks
were REAL changes (full-stack 7.8K→11.3K and renamed to "AI-Native Full
Stack Program"; ai-engineering 2.5K→15K with new Job-or-Refund
positioning; cybersecurity 7.8K→10.5K at 0.85 ratio), while the 3 pages
comparing curl-vs-camoufox (home, home-es, dsm) were artifacts that
needed first-300-char spot-checks to classify (home-es at 0.82 with
identical hero text = no real change; home 0.70 with a new Bahamas
partnership banner = real addition). Same lesson applies to nuclio
masters (camoufox 6.1K vs curl 11.5K — looked like growth, was actually
a real catalog restructure confirmed by reading the new program list)
and liora formations (curl 33.7K vs camoufox 10.2K — looked like
shrinkage, contained a genuinely new FNE-financing article).
Takeaway: never report a per-competitor "N pages changed" headline
without first partitioning the flags by source-field parity.

### Confirm novelty before calling something "new"

When an apparent addition surfaces (a new banner, claim, course, or price),
grep the SAME page's text across the prior 2-3 weeks before reporting it as
new this week. A substring can be present for weeks while the page-level diff
still flags a change for unrelated reasons. Observed 2026-08-31: 4Geeks'
"Bahamas alongside Harvard/Oxford/Columbia" banner was initially read as a
fresh addition (and is mis-recorded as such in the Validation note above) but
a substring check showed it had been in `home` since 2026-08-10; neuefische's
`/bootcamp` 404 was likewise persistent since ~08-10 rather than a new removal
this week. A one-line `"<phrase>" in text` check against each prior week's JSON
disambiguates "new this week" from "new to the diff" — do it before writing any
"competitor X added Y" bullet into the exec summary.

## Small Content Swaps Masquerade as "Unchanged" (inverse of the 404 traps)

The 404 pitfalls above are false-"changed". The inverse also bites: a REAL
catalog change small enough to keep the whole-page difflib ratio ≥ 0.85 gets
flagged "unchanged". Observed 2026-09-07: Spiced home-de/home-en (9.5K chars)
had one program card swapped (Advanced Software Development with AI → AI
Architect Bootcamp, ~230 chars in / ~290 out, net −63 chars) — ratio ≈ 0.985
→ "unchanged", yet it was the week's most material finding. The same swap on
the /program listing page DID flag "changed" (larger relative diff), which is
what tipped the investigation.

Detection and handling:
- Near-identical char counts are NOT identity. When the narrative suspects a
  catalog shift (a program name shows up in today's home/listing text that the
  delta didn't flag), run targeted `prev_text.count("<name>")` vs
  `today_text.count("<name>")` per page — never trust the ratio alone.
- When a change is confirmed on one page, diff that page's STRUCTURAL rows
  (extract name + duration/format lines, e.g. `Online\s?<Name>` cards) rather
  than raw text — row-level diff surfaces one-for-one replacements cleanly.
- Shared-codebase pairs (spiced/neuefische): when a change is found on one
  site, grep the sister site for the same item in the same run.
- Byte-identical `text_len` between weeks = no change; a NEARLY identical
  length (±100 chars) with a changed program card is exactly this trap.

## Hunk-Level Word Diff for Judging "Changed" Flags

Page-level difflib (char ratio) cannot separate real content changes from
capture noise — alumni/testimonial carousel rotation, lazy-loaded sections
appearing/disappearing between renders, nav reorder, title-case changes. On
2026-09-07 the raw delta flagged lewagon 7/9, fourgeeks 6/6 and neuefische
9/10 pages "changed", almost all noise; the one true finding (spiced swap) was
confirmed and everything else dismissed by printing word-level diff hunks.
Reusable script: `scripts/hunk-diff.py` — `python3 hunk-diff.py <prev_dir>
<today_dir>`. It diffs whitespace-split word streams per shared page, prints
only non-equal opcodes (ADD/DEL/REP, capped per page), and skips <4-word
replace hunks as formatting shuffle. A page with 25 hunks of pure alumni-name
churn is visibly noise; a 2-hunk page with a program-card swap is visibly
real. Run it before writing any per-competitor "N pages changed" delta
narrative.
