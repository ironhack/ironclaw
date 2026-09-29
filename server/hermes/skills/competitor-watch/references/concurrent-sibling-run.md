# Concurrent Sibling Phase 2 Run — Playbook

Validated 2026-08-17: a second Phase 2 cron execution of competitor-watch
ran CONCURRENTLY with the current session, start to finish. It was not a
crashed leftover (see SKILL.md's stale-artifacts pitfall) — it was ALIVE
and writing while this session worked.

## Detection Signals (any of these while YOUR session is running)

1. **Snapshot file mtimes advancing during your session.** On 2026-08-17
   the snapshot dir's `*.json` files were all rewritten at 15:07, then
   `delta-analysis.json` at 15:08, `news-journal.json` at 15:09 — minutes
   apart and AFTER this session had already taken its first inventory
   (which showed liora with no pages). A crashed leftover's files sit
   BETWEEN `manifest.json` and your session start; a live sibling's files
   are NEWER than your session start and keep moving.
2. **Write-collision warnings on shared paths.** Attempting to write
   `/tmp/parse_news.py` returned: "modified by sibling subagent
   '55838705-...' but this agent never read it". The sibling was using
   the same conventional filenames from the same skill. Treat any such
   warning as proof a sibling is mid-run.
3. **Sibling artifacts appearing mid-session:** `tmp/YYYY-MM-DD_competitor-watch.html`
   and the S3 object `s3://ih-ironclaw/watch/YYYY-MM-DD/competitor-watch-report.html`
   appear while you are still working.
4. **`ps aux | grep competitor` shows NOTHING** — this check is
   insufficient. The sibling runs as an LLM session inside the hermes
   gateway process (e.g. `/home/openclaw/ironclaw-venv/bin/python -m hermes_cli.main gateway run`), invisible to ps greps on
   script names.
5. **BUT the sibling's SHELL COMMANDS are visible in `ps aux`**
   (validated 2026-08-31). The sibling's terminal-driven recovery runs
   as a bash process executing a `/tmp/hermes-snap-<id>.sh` wrapper, and
   the full command line — including its curl fetch list with URLs — is
   visible. Detection:
   `ps aux | grep -E "hermes-snap|curl" | grep -v grep`
   This catches the sibling during its recovery phase and is better than
   a generic grep: it reveals WHICH pages the sibling is recovering, so
   you know exactly what not to duplicate. On 2026-08-31 it showed the
   sibling curl-fetching nuclio_home/masters, fourgeeks_home/home_es/dsm,
   lewagon_home_es, liora_home_fr, masterschool_programs,
   neuefische_bootcamps — a one-to-one match with the pages Phase 1 had
   failed. Caveat: the sibling is only visible this way WHILE its
   recovery commands run; once it moves to LLM-only phases (delta, news,
   HTML) it drops out of ps again — pair this grep with the mtime checks
   to keep tracking it.

## False-Positive "Sibling Subagent" Warnings (Spurious)

Observed 2026-08-24: `write_file` to conventional scratch filenames
(`parse_news.py`, `delta_compare.py`, `extract.py` in
`/tmp/competitor-fetches/`) triggered "modified by sibling subagent
`<id>` but this agent never read it" warnings — yet NO live sibling was
running (no advancing mtimes, no tmp/ HTML, no delta/news files in the
snapshot dir, `ps aux` clean). Cause: those filenames already existed
from PRIOR weeks' sessions in the shared scratch dir, and the
file-watcher's ownership check labels the prior session as a "sibling
subagent."

Distinguish a spurious warning from a real live sibling:
- `ls -la --time-style=full-iso` the warned file. A prior-week date
  (not advancing during your session) = spurious, proceed normally. An
  mtime advancing minutes apart during your session = live sibling,
  follow the playbook below.
- The "sibling subagent" IDs differ per file (each is a different prior
  session's owner). Two or three different IDs on different files are
  NOT evidence of multiple live siblings — they are independent prior
  owners of pre-existing scratch files.

Do not panic on a lone write-warning. Correlate it against the three
hard signals in "Detection Signals" (advancing mtimes, tmp/ HTML
appearing, snapshot-dir artifacts appearing) before treating it as a
concurrent run.

## Handling Sequence

1. **Stop writing shared files** (snapshot JSONs, manifest, delta,
   news-journal) until you know the sibling's state. Your writes race its
   reads; its writes race yours. The one exception is the append-only
   `news-journal.jsonl` — independent lines are safe to append.
2. **Verify the sibling's recovery, don't redo it.** Read its competitor
   JSONs: page keys present, `text_len > 1000` for content pages, correct
   `url`/`source` fields. On 2026-08-17 the sibling's recovery was
   byte-equivalent in intent to this session's independent curl recovery
   (same new slugs, same sources) → its data was trustworthy. Reuse it.
3. **Independently re-run the delta** (same script params) and **redo the
   news scan** (Google News RSS, 30-day cutoff). Compare your outputs to
   the sibling's — disagreement is the trigger to investigate, agreement
   confirms the sibling's analysis. On 2026-08-24 the independent delta
   matched the sibling's output EXACTLY for all 7 competitors (same
   changed/new/removed/unchanged page lists) — write your delta script
   to a `/tmp` path (not the snapshot dir) so it cannot collide with the
   sibling's `delta-analysis.json` write.
4. **Check the sibling's deliverables:**
   - `tmp/YYYY-MM-DD_competitor-watch.html` exists and is complete
     (title, exec summary, catalog tables with links, delta, confidence,
     recovery notes, data-quality flags — no placeholders).
   - S3 object exists and is public: `curl -sI <public-url>` → HTTP 200
     with matching byte size. For byte-level proof the uploaded file is
     the sibling's report (not a stale object from an older run), diff
     MD5s: `curl -sL <public-url> -o /tmp/x.html && md5sum /tmp/x.html
     tmp/YYYY-MM-DD_competitor-watch.html` — matching hashes = the S3
     object IS the local report.
   - Fetch script root cause fixed: grep
     `/home/openclaw/.hermes/scripts/competitor-watch-fetch.py` for the
     correct slugs (e.g. `bootcamp/cyber-cloud-und-information-security`,
     `program/cloud-cyber-information-security`). On 2026-08-17 the
     sibling had already updated all 6 remapped URLs — verify, do not
     re-fix.
5. **Decision: deliver the sibling's verified report.** Regenerating and
   re-uploading creates a clobber race on the single S3 object path —
   last writer wins, and the Slack delivery comes from YOUR final
   response either way. One coherent, verified report is better than two
   racing ones. Only regenerate if the sibling's report is missing,
   incomplete, or factually wrong (e.g. invented prices).

## Mid-Pipeline Sibling: Detect, Verify, Wait, Re-Check (2026-08-24)

The sibling may still be WORKING when you detect it — recovery + delta +
news done, but HTML report and S3 upload not yet produced. Detection
signals are the same, plus: the `tmp/YYYY-MM-DD_competitor-watch.html`
and the S3 object are ABSENT while `delta-analysis.json` and
`news-journal.json` already exist with fresh mtimes.

Handling — treat the gap as productive waiting time, then re-check:

1. Do NOT start generating your own HTML yet. The sibling is ahead of
   you in the pipeline and will likely finish.
2. While it works, complete the independent verification (steps 2–3
   above): verify recovery, re-run delta to your own `/tmp` path, redo
   the news scan from fresh RSS files (don't trust the sibling's
   `news-journal.json` until your scan agrees — on 2026-08-24 both came
   back all-empty with the same listicle-only feeds, confirming it).
   Spot-verify the sibling's key factual claims against snapshot text
   (prices, tuition tables, employability stats, accreditation names) —
   a section-complete report can still contain a wrong number.
3. After your verification is done, RE-CHECK the deliverables (step 4).
   On 2026-08-24 the sibling finished mid-session: the HTML appeared and
   the S3 object returned HTTP 200 with an MD5 identical to the local
   tmp file, all while this session was verifying. Deliver it — do not
   regenerate (step 5).
4. Only if the sibling has still not produced HTML/S3 after your
   verification completes should you generate and upload your own report
   (you have verified recovery + delta + news, so your report is ready
   to build). This keeps regeneration as a fallback, not the default.

## Headline Fact-Check Before Delivery — Data Agreement ≠ Correct Claims (2026-09-07)

The 2026-09-07 run: the sibling finished its full pipeline (recovery → delta →
news → HTML → S3 upload; HTTP 200, MD5 matched the local tmp file). Its
recovery was consistent with this session's (all pages present), its delta
page-lists matched an independent re-run exactly, and its news journal
(all-empty) matched an independent RSS scan. **Yet its Executive Summary and
Delta sections contained materially wrong headline claims** — only a
claim-by-claim grep against the PREVIOUS week's snapshot texts exposed them:

- "neue fische catalog expanded… adding Agentic ML Engineering, Data
  Engineering, Java Development with AI, UX/UI" → all four appear in last
  week's homepage text (prev-week grep counts > 0). Only **AI Architect** was
  genuinely new (prev x0, today x2). The sibling compared against an implicit
  "7 tracked course pages" baseline instead of the real prior catalog.
- "IHK-Zertifikat added to Data Science & AI (previously only Java)" → the
  identical "✔ Neu: … mit IHK-Zertifikat" line exists in prev week's
  home-de/home-en. Not an addition.
- "Masterschool added EU AI Act Practitioner + €500 referral; menu expanded" →
  masterschool pages were *unchanged* (its own delta section said "no change"
  — the exec summary contradicted its own delta).
- "Spiced now lists ~24 programs (expanded)" → programs page actually has 18
  rows; the real change was one swap (Advanced Software Development with AI →
  AI Architect Bootcamp).
- "4Geeks full rebrand, pivot from four career programs to three AI programs"
  → OVERSTATED: its own catalog table listed the same 4 career programs + AI
  Flex + AI Fluency (exec contradicted its own table). BUT the underlying
  migration was TRUE: `curl -sIL https://www.4geeksacademy.com` returns a 301
  to 4geeks.com, and the site is client-rendered again. Do NOT dismiss a bold
  sibling claim just because no snapshot text mentions it — verify
  domain/redirect claims with a 2-second curl HEAD before judging.

**Process when a sibling's report exists and looks complete:**
1. Extract every NEW/new/added/expanded/removed/renamed/rebrand/pivot/launched
   phrase from its exec summary AND delta section.
2. Grep each named item (program, cert, promo, price, domain) in the PREVIOUS
   week's snapshot texts. Found in prev → the sibling's "this week" framing is
   wrong regardless of how confident the prose is.
3. Check internal consistency: exec summary vs the sibling's own catalog
   tables and delta section. Contradictions (e.g. "pivot to three programs"
   beside a 6-row table of the same 4 career programs) are red flags.
4. Verify domain/redirect/infrastructure claims independently (curl HEAD).
5. If headline claims fail spot-checks, REGENERATE + re-upload your own
   corrected report (last-writer-wins is safe once the sibling has finished —
   confirm no new file mtimes for a few minutes first) and record in the
   report's Data Quality section which sibling claims were rejected and why.
   A complete-but-misleading report is worse than regenerating.

Also from the same run: **the sibling's delta may predate its own
integration.** mtimes showed its delta-analysis.json written ~10s BEFORE its
competitor-JSON integration — its page lists were computed against
pre-restore data (nuclio /masters read as the fuller capture, then its own
partial capture overwrote the file AFTER the delta ran). And a Camoufox retry
can yield a PARTIAL lazy-render: the sibling's nuclio /masters retry returned
6.1K chars on a page curl captures fully at 11.5K (last week's capture was
also 11.5K). When you hold a fuller capture, restore it (update `source`),
then re-run the delta yourself on the final data.

## Notes

- The sibling may complete its pipeline AFTER you start yours; the
  `tmp/` + S3 check in step 4 should be done as late as possible — and
  re-checked once more right before you commit to regenerating.
- If the sibling crashes mid-run (the 2026-08-03 precedent), its partial
  files become the ordinary stale-artifacts case — handle per SKILL.md.
- News-journal consistency check: if `news-journal.json` is all-empty but
  the jsonl scan record reports per-competitor article counts > 0, the
  log was written before final filtering — redo the scan before trusting
  the "no news" conclusion.
- Revisit old "unrecoverable" pages: 4Geeks `/es` was listed as an
  unrecoverable React SPA for weeks, then fetched fine via curl on
  2026-08-24 (site now server-renders it). Don't treat past
  unrecoverability as permanent — a curl retry costs seconds, and a
  site-side change can make a previously dead page scrapeable.
- Exec-summary count precision: a sibling bullet like "4 pages recovered"
  may actually mean 4 COMPETITORS / 6 pages. Check bullet claims against
  the Recovery Notes section before echoing them in your delivery — the
  notes are usually the accurate count.
- **Prefer the richer recovery when both runs recovered the same page**
  (observed 2026-09-07): the sibling and this session independently
  recovered the same failed pages with DIFFERENT methods and got DIFFERENT
  yields — e.g. nuclio /masters: this session's curl-fallback = 11,551 chars
  vs the sibling's camoufox-retry = 6,117 chars (the sibling's delta had even
  read the richer pre-restore file). A Camoufox retry can return a PARTIAL
  lazy-render on long pages — check `text_len` against last week's capture
  and against any curl yield you have, then restore the fullest text (with a
  matching `source` field) and re-run the delta on the final data.

