# Extraction schema (one JSON per competitor per week)

Path: `competitor-watch/extractions/DATE/<key>.json`, written by the agent from `competitor-watch/prepared/DATE/<key>.txt`. `cw-reconcile.py` validates it and turns it into state + change log. Rules:

- Every program, claim and promotion needs an `evidence` string of at least 20 characters copied **verbatim** from the prepared text (same page). The reconciler checks it; items whose evidence is not found are marked unverified and ignored for change detection.
- Only real offerings: bootcamps, masters, courses, short courses, subscriptions. Not navigation items, blog posts, events, generic CTAs.
- `null` when a field is not on the page. Never estimate prices or durations.
- Keep names as the site writes them (the reconciler normalises for matching).
- `page` is the page label from the prepared file (e.g. `course-ai-architect`).

```json
{
  "competitor": "spiced",
  "date": "2026-09-21",
  "programs": [
    {
      "name": "AI Architect Bootcamp",
      "type": "bootcamp | master | short-course | subscription | other",
      "duration": "16 weeks",
      "format": "full-time remote | part-time | hybrid Berlin | online self-paced ...",
      "language": "EN | DE | ES | FR | PT | NL | multi",
      "price": "€5,750 | null",
      "financing": ["Bildungsgutschein", "installments 48 months"],
      "markets": ["DE"],
      "next_start": "2027-01-18 | null",
      "url": "https://www.spiced-academy.com/en/program/ai-architect",
      "page": "course-ai-architect",
      "evidence": "AI Architect Bootcamp 16 weeks full-time remote English starts 18 Jan 2027"
    }
  ],
  "claims": [
    {"kind": "placement | accreditation | guarantee | alumni | rating | partnership | other",
     "text": "86% employability", "page": "home", "evidence": "86% de empleabilidad ..."}
  ],
  "promotions": [
    {"text": "€500 referral bonus", "page": "home", "evidence": "...", "ends": "2026-10-31 | null"}
  ],
  "positioning": "one sentence: the main message the site leads with",
  "notes": "anything unusual: broken pages, thin captures, language mismatches"
}
```

Reconciler behaviour (so the agent knows what the state will do with the extraction):
- program matching by normalised name; a close match (ratio >= 0.85) with a different name is recorded as `program_renamed`.
- a program missing from the extraction is only marked `removed` after **two consecutive** weeks missing **and** only when the competitor's capture quality that week is `ok` or `partial`. One miss sets `status: unconfirmed`.
- price / duration / format / next_start changes are recorded field by field (`next_start` moves are low signal: `cohort_moved`).
- claims and promotions match by normalised text; new ones -> `claim_added` / `promo_started`, gone for two weeks -> `claim_removed` / `promo_ended`.
- `positioning` is compared with the stored sentence; a similarity below 0.6 records `positioning_changed`.
