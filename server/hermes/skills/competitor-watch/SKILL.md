---
name: competitor-watch
description: >
  Weekly competitor intelligence for Ironhack (7 competitors, ES/PT/FR/NL/DE). v2 (2026-09-25):
  scripts scrape, prepare, keep a structured state per competitor and an append-only change log;
  the agent extracts catalog/claims/promotions with verbatim evidence and writes the narrative.
  Use when asked to run competitor watch, competitor scan, or competitive intelligence.
category: openclaw-imports
version: 2.0.0
---

# Competitor Watch v2

## Why v2

v1 re-derived every competitor's catalog from raw page text every week and diffed raw text, so
"new" claims contradicted each other between runs, capture-method noise produced false changes,
and there was no memory beyond snapshots. v2 keeps a **structured state** and a **change log**
(the long-lasting context), validates every extracted item against the page text, and only ever
reports changes the reconciler could verify. One agent job runs (the duplicate report job was
removed on 2026-09-25).

## Pipeline

| Job | When (UTC) | Type | What |
|---|---|---|---|
| `545d0f187758` Weekly Watch: Fetch | Mon 09:00 | no_agent `~/.hermes/scripts/competitor-watch-fetch.sh` | Camoufox scrape → `competitor-snapshots/DATE/`, then `cw-sitemaps.py` (site activity) and `cw-prepare.py` (capture quality + prepared texts). stdout = digest |
| `77bf232bfcb5` Weekly Watch: Report | Mon 12:00 | LLM, context_from Fetch, deliver local, failure-deliver Slack | extract → `cw-reconcile.py apply` → narrative → `cw-build-report.py --post` |

Storage (`/home/openclaw/ironclaw-data/workspace/competitor-watch/`):
```
state/<key>.json          current programs / claims / promotions / positioning, first_seen, last_seen, status, history
changes.jsonl             append-only change log (date, competitor, type, severity, item, before, after, evidence, url)
changes/DATE.json         this week's changes
extractions/DATE/<key>.json   agent output (schema: references/extraction-schema.md)
prepared/DATE/<key>.txt   boilerplate-stripped page texts + index.json (capture quality per page)
sitemaps/DATE/<key>.json  URL sets, new-urls.json (diff vs previous week)
captures.json             page length history (drives the degraded/empty flags)
```
Raw snapshots stay in `~/ironclaw-data/workspace/competitor-snapshots/DATE/` (Phase 1 output).

Reports: `https://ih-ironclaw.s3.eu-west-1.amazonaws.com/watch/DATE/competitor-watch-report.html`, latest at `watch/latest/report.html`, preview at `watch/preview/report.html`.

## Workflow v2 (what the agent does in the Report job)

1. Read the injected digest (capture status per competitor, new site URLs).
2. For each competitor read `prepared/DATE/<key>.txt` and write `extractions/DATE/<key>.json` per
   `references/extraction-schema.md`. Verbatim evidence (>= 20 chars) for every item; null when not stated.
3. `python3 scripts/cw-reconcile.py apply --date DATE` → verified changes + unverified items. Fix real
   unverified items by correcting the quote, re-run. Never force an item the page does not support.
4. Write `/tmp/cw-narrative.json` (headline, actions, change_notes by change id, competitor_notes, watch_next).
5. `python3 scripts/cw-build-report.py --date DATE --narrative /tmp/cw-narrative.json --post` → S3 + Slack.
6. Final response: one line with the URL and Slack ts.

Full prompt: `references/cron-prompt-v2.txt`.

## Change detection rules (cw-reconcile.py)

- Programs match by normalised name; ratio >= 0.85 with a different name = `program_renamed`.
- A program missing from an extraction is `unconfirmed` after one week and `removed` after two
  consecutive weeks, and only when that week's capture quality is ok/partial. Bad captures never remove.
- Field changes recorded per field: `price_changed`, `duration_changed`, `format_changed` (format /
  language / markets), `cohort_moved` (next_start, low signal).
- Claims and promotions: `claim_added` / `claim_changed` (same claim, different numbers) /
  `claim_removed`, `promo_started` / `promo_ended`, same two-miss rule.
- `positioning_changed` when the lead sentence similarity drops below 0.6.
- First extraction week records everything as `baseline` (not reported as changes); `cw-reconcile.py
  backfill` then sets `first_seen` from the earliest snapshot containing the program name and writes
  historical `program_added` entries (`backfilled: true`).

## Capture quality (cw-prepare.py)

Per page: `empty` (no text), `degraded` (< 40% of the page's median length over the last 4 captures),
`grown` (> 2.5x), `ok`. Competitor quality: `ok` / `partial` / `bad`. Lines present on >= 60% of a
competitor's pages (nav, footer, cookie banner) are stripped and shown once at the top of the prepared
text. Pages are capped at 7,000 chars each after stripping.

## Site activity (cw-sitemaps.py)

robots.txt → sitemap(s) → URL set per competitor per week; new URLs grouped as program / top / content /
other. New program-type URLs are the earliest public signal of a launch (they precede the page being
linked from the catalog). This replaces the Google News RSS scan, which returned zero genuine items for
six consecutive weeks (name collisions: "neue fische" = fish stocks, "Masterschool" = Berlin concerts).

## Slack post (cw-build-report.py)

Header "Competitor watch · week of <date>", headline sentence, one status pill per competitor
(orange = changed, white = quiet N wk, red = capture bad), "What changed (verified against the pages)"
with evidence links, "Worth acting on" (narrative), "Site activity", "Watch next week", context line,
buttons (report, timeline). Thread reply: per-competitor status, previous 4 weeks of changes, capture
details. Quiet weeks post a short version, never "[SILENT]".

## Competitors

Defined in `scripts/cw_common.py` (`COMPETITORS`, names/markets) and in the fetch script
(`~/.hermes/scripts/competitor-watch-fetch.py`, `COMPETITORS` dict with the tracked page URLs).
Change both when adding or removing a competitor.

| Key | Competitor | Site | Markets |
|---|---|---|---|
| lewagon | Le Wagon | lewagon.com | ES, PT, FR, NL, DE |
| nuclio | Nuclio School | nuclio.school | ES |
| neuefische | neue fische | neuefische.de | DE |
| spiced | Spiced Academy | spiced-academy.com | DE |
| fourgeeks | 4Geeks Academy | 4geeks.com | ES |
| masterschool | Masterschool (MSIT) | joinmsit.de | DE |
| liora | Liora (ex-DataScientest) | liora.io | FR, DE, NL |

neuefische.de and spiced-academy.com share a codebase; Nuclio `/masters` may 403 to curl.

**Fetch script behaviour (2026-09-25):** competitors run through a pool of `COMPETITOR_WATCH_CONCURRENCY`
(default 3) browser processes (7 in parallel starved the 4-core VPS: every `page.goto` timed out); each
worker writes its JSON after every page so a timeout keeps partial results; per-competitor timeout
`COMPETITOR_WATCH_COMPETITOR_TIMEOUT` (420 s) inside the overall `COMPETITOR_WATCH_BUDGET` (500 s);
any worker still alive at finalization is killed. `--only key1,key2` restricts a run. **4geeks.com**
crashes the Playwright driver in-process ("Connection closed while reading from the driver"), so it is
flagged `"per_page": True`: every page is fetched in its own OS process (`--fetch-one URL`, 75 s hard
timeout, one retry). Expect 4Geeks captures to stay partial and to vary week to week; the reconciler never
removes programs on a bad capture, so its catalog just goes `unconfirmed` until a page renders again.

## Cron-mode constraints (still true)

`execute_code` is blocked; pipe-to-interpreter (`curl | python3`) and `&` backgrounding are blocked;
write scripts with `write_file`, run with `terminal`. No Unicode emoji in commands. The fetch script runs
inside the Hermes venv (`camoufox` installed there); `cron.script_timeout_seconds` is 600 and the fetch
wrapper budgets 420 s for the scrape so the sitemap/prepare steps always run.

## Manual runs

```
bash ~/.hermes/scripts/competitor-watch-fetch.sh                        # Phase 1 now (prints the digest)
python3 scripts/cw-prepare.py --date DATE                                # re-prepare a snapshot
python3 scripts/cw-reconcile.py apply --date DATE --dry-run              # see what would change
python3 scripts/cw-reconcile.py status | backfill
python3 scripts/cw-build-report.py --date DATE --preview [--post --to U02MV9VPGV6]   # preview report / DM
```

## Legacy material

`references/` still holds the v1 recovery, delta and sibling-run notes (camoufox-patterns, curl-fallback,
delta-comparison-*, concurrent-sibling-run, url-restructure-recovery, after-recovery-patterns,
report-generation-patterns, news-rss-gotchas) and `scripts/hunk-diff.py`, `scripts/recover_subprocess_per_page.py`.
They are not part of the v2 workflow; use `references/camoufox-patterns.md` only when fixing the fetch script.
