# Changelog

Ops log for the IronClaw server. Most recent entry first.

---

## 2026-09-29 — Argos daily sanity converted to the generator-posts pattern

Rudy flagged that the 09:00 sanity post in #argos-home was still the old format and double-posted (Block Kit
message plus the cron wrapper with the model's re-summary); the transcript also showed the model deleting
and re-posting a message after getting the headline count wrong. Converted like the performance report on
2026-09-25 (backups in `scripts/argos/.bak-2026-09-29/`):

- `sanity_check.py` now writes the full dataset to `/tmp/argos_sanity_data.json` (`--out`) and prints a
  compact classified summary for the agent (`--full-stdout` keeps the old behaviour).
- New `argos_sanity_slack.py`: deterministic flags per serving campaign (over budget + 0 conversions,
  over budget + ROAS < 1, capped + 0 conversions, capped but efficient = raise candidate, near cap, ok),
  disapproved ads, enabled-but-ended campaigns grouped by pattern (experiments / legacy RMTEU / seasonal /
  other), market scorecard BER AMS MAD LIS PAR; Block Kit post in the approved shape (headline, scorecard,
  needs-a-hand list, raise candidates, cleared items, watch-outs, actions, context line, buttons, details
  thread). State file `ironclaw-data/argos/sanity-state.json` tracks first_seen / last_seen per issue so
  the post marks `:new:`, `(day N)` and "cleared since last check" instead of re-listing 40 items daily.
  Seeded with today's 42 issues.
- `generate_sanity_report.py`: `--narrative`, `--post`, `--to`, `--preview`, `--local`, `--blocks-out`.
- Job `de090919d14d`: prompt `references/cron-prompt-sanity-v2.txt`, `--deliver local`,
  `--failure-deliver slack:C0BFMA3117F`; the prompt forbids deleting or re-posting messages.
- Docs: `slack-sanity-template.md` rewritten (v2 shape + flag table), `narrative-schema.md` "Daily sanity"
  section, SKILL.md note. DM preview sent to Rudy from today's data (preview HTML at
  `ironclaw/argos/shared/sanity-preview.html`). Rudy asked for a run today: triggered at 10:59 Rome, one post + thread in #argos-home, agent response one line, no deletes. Next scheduled run: Wed 2026-09-30 09:00 Rome.
- First-run guard: with no earlier tracked run the post says "issue history starts today" instead of marking every item new.

## 2026-09-28 — Competitor watch: first v2 Monday, fetch timed out at 600 s (fixed, re-run)

**What happened**: `Weekly Watch: Fetch` posted its failure alert at 11:11 Rome (as designed). The scrape
alone took 502 s (neue fische hung in-process and was killed at 420 s with 4/19 pages; 4Geeks' per-page
retries held a pool slot for the whole run; 29/53 pages), so the sitemap step was killed at the 600 s
`cron.script_timeout_seconds` limit and no digest / prepared texts were written.

**Fix**: `cron.script_timeout_seconds` 600 → 1200 (`hermes config set`, default-profile gateway
restarted); wrapper scrape budget 500 → 800 s; per-competitor timeout 420 → 600 s; neue fische now runs in
per-page (crash-isolated) mode like 4Geeks. Phase 1 re-run manually at 12:03 Rome (726 s, digest written)
so the 14:00 report job had today's digest. First real sitemap diff: 2 new pages at 4Geeks (AI-engineer
interview content), 2 at Masterschool (`/weiterbildung-im-job/`).

**Open**: neuefische.de now drops TCP connections from the VPS entirely (HTTP 000 after 20 s on every
URL and the sitemap; instant 200 from a laptop). Thursday 19/19 → Monday 09:00 4/19 → 12:00 0/19: a
progressive block, most likely triggered by the scraping. neue fische's tracked pages cut from 19 to 10 to
reduce the footprint; the report marks its capture as failed and removes nothing. Re-check next Monday; if
the block persists, the fetch needs a different egress for that site.

**Also found today**: three Hermes gateways (argos, helios, athena) were stuck in a hot Slack socket-mode
reconnect loop (`RuntimeError: Session is closed`, slack_bolt 1.30 / slack_sdk 3.43, hundreds of retries a
minute). helios and athena since 00:00 UTC, argos since the 08:00 cron fire. The default gateway was fine.
Cron jobs still ran and the Argos v2 post landed at 08:04 UTC because the generators post over HTTP, not
socket mode, but the profiles could not answer Slack mentions. Fixed by `systemctl --user restart` of the
three units. If it recurs, add a journal check + auto-restart timer (Helios is the natural owner).

**neue fische re-fetch (13:51 Rome)**: the site answered the server again (HTTP 200 in 0.2 s), so the
report job was paused for 3 minutes, neue fische re-fetched alone (`--only neuefische`, 10/10 pages in
97 s, sitemap 1,270 URLs, 0 new), manifest merged, sitemaps + prepare + digest rebuilt, job resumed for
its normal 12:00 UTC slot. Script: `/tmp/cw_refetch_nf.sh` (ad hoc, not kept).

**v2 first-run verification (all three pipelines, one post each, agent response = one line)**:
- Argos performance 10:04 Rome: Block Kit post + thread in #argos-home, correct shape.
- SEO Intel & Audit 14:04 Rome: headline (GA4 +10.9% vs GSC −7.8%, DE the only real decline), market
  scorecard, 6 fix outcomes (de-cybersecurity-title regressed, wd/ux consolidation confirmed / beat
  market, nl-homepage measuring), 4 watch-outs with owners, 3 ship-next items, 2 new backlog items
  (gmb-utm-source-cleanup, ai-engineering-title-not-localized). Narrative numbers match the digest.
- Weekly Watch 14:18 Rome: quiet week, 9 verified cohort_moved changes (neue fische 5, Spiced 4) with
  evidence, Masterschool `/weiterbildung-im-job/` flagged as the lead to watch, 4Geeks new AI-engineer
  interview content noted from the sitemap diff. Reconciler removed nothing: 4Geeks capture bad,
  Liora 27 programs unconfirmed (home mega-menu did not render this week), neue fische 1 unconfirmed.

Follow-ups from the first runs:
- The watch digest should state the *tracked* page count per competitor; the model read the old
  timeout lines in the appended fetch log and wrote "neue fische dropped to 10 pages (fetch timeout)"
  and "confirm coverage recovers (~19 pages)", but 10 is now the configured list.
- Liora programs come from the home mega-menu; if it fails to render again next week, add the
  `formations` catalog page to the fetch list (also the open Liora catalog URL item).

---

## 2026-09-25 — OpenClaw software removed; `~/.openclaw` kept as the Hermes data home

**Context**: the OpenClaw gateway had not run for months (no process, no systemd unit); all four agents
now run on Hermes (default profile: SEO, competitor watch, Scout; argos profile: Google Ads). The
`~/.openclaw/` directory, however, is still where the Hermes pipelines keep their data (~130 path
references), so only the software and the OpenClaw-only state were removed.

**Removed** (archived first under `~/archive/`): global npm package `openclaw@2026.5.22` and
`/usr/bin/openclaw`; source checkout `~/openclaw` (500 MB) and `~/openclaw-backup-20260505`
(`openclaw-software-2026-09-25.tar.gz`, 441 MB); OpenClaw-only subdirectories of `~/.openclaw`
(agents, memory, extensions, plugins, credentials, identity, cron, logs, trajectory-exports,
workspace-ironclaw-edu, openclaw.json + backups, gateway.systemd.env, ...)
(`openclaw-data-only-2026-09-25.tar.gz`, 49 MB).

**Kept** in `~/.openclaw/`: `workspace/` (competitor-snapshots + competitor-watch), `workspace-ironclaw-seo/`,
`workspace-ironclaw-jobs/` (Scout + the logo Argos embeds), `gsc-service-account.json`, `.env`.
Verified afterwards: SEO backlog CLI, competitor-watch state, Argos logo loader all fine.

**Phase 2 (same day)**: `~/.openclaw` moved to **`/home/openclaw/ironclaw-data`**; a symlink
`~/.openclaw -> ironclaw-data` is kept for safety. 42 live files repointed (Hermes scripts, skill
scripts and docs, `~/.hermes/.env` `GOOGLE_SA_KEY_PATH`, `config.yaml`), plus the prompts of the 5 cron
jobs that named the path (3 Scout, SEO Intel & Audit, Weekly Watch Report) via `hermes cron edit`.
Verified with the symlink hidden: watch state, SEO backlog CLI, Argos logo loader all resolve the new path.
Historical copies under `~/.hermes/migration/` and `pastes/` were left untouched.

**Phase 3 (same day, repo)**: README.md and CLAUDE.md rewritten for the Hermes setup (profiles, pipelines,
data home, design principles, gotchas). OpenClaw-era material moved to `archive/openclaw/` (the three
`server/workspace-*` mirrors incl. the uncommitted Scout edits, `deploy-workspaces.sh`, the Slack app
manifest and `.slack/`). New `scripts/sync-from-server.sh` pulls the live Hermes scripts, skills and a
generated cron inventory into `server/hermes/` (read-only mirror; the server stays the source of truth).
Stray untracked file with a newline in its name removed; `.gitignore` added.

**Still to do**: uninstall the dead `ironclaw2` Slack app (A0B19LV97DM); drop the `~/.openclaw` symlink
once a couple of Monday runs have passed cleanly.

---

## 2026-09-25 — Competitor Watch v2: structured state + change log, one agent, evidence-verified changes

**Context**: Rudy's assessment request. v1 re-derived every catalog from raw page text weekly and
diffed raw text (capture-method noise), had no memory beyond snapshots, ran TWO report jobs in
parallel (created 19 and 22 June) that contradicted each other in #ironclaw-watch, scanned Google
News RSS with zero genuine hits for 6+ weeks, and reported scraper plumbing as intelligence.

**What changed** (skill `~/.hermes/skills/openclaw-imports/competitor-watch/`, v2.0.0; backups in
`.bak-2026-09-25/`):

1. **State + change log** under `~/.openclaw/workspace/competitor-watch/`: `state/<key>.json` (programs,
   claims, promotions, positioning with first_seen / last_seen / status / history) and append-only
   `changes.jsonl` (type, severity, before/after, verbatim evidence, url). `cw-reconcile.py apply`
   validates every extracted item against the prepared page text (evidence must appear verbatim),
   matches by normalised name (renames at ratio >= 0.85), removes only after two consecutive misses on
   a usable capture, records field-level changes. `cw-reconcile.py backfill` sets first_seen from the
   28 historical snapshots and writes historical program_added entries.
2. **Fetch wrapper** `~/.hermes/scripts/competitor-watch-fetch.sh`: Camoufox scrape (420 s budget) →
   `cw-sitemaps.py` (URL sets per competitor, new-URL diff = the news proxy; all 7 sites expose
   sitemaps) → `cw-prepare.py` (per-page capture quality vs 4-week median, boilerplate stripping,
   7,000-char cap, extraction-ready texts + digest).
3. **Report job** prompt v2 (`references/cron-prompt-v2.txt`): extract per competitor into
   `extractions/DATE/<key>.json` (schema `references/extraction-schema.md`) → reconcile → narrative JSON
   → `cw-build-report.py --post`. Cumulative HTML (verified changes with evidence, site activity,
   competitor cards with first-seen dates, 12-week timeline, capture quality) to `watch/DATE/` and
   `watch/latest/`; Block Kit Slack post in the approved shape (headline, status pills, verified changes
   with page links, worth acting on, site activity, watch next, buttons) + details thread.
4. **Jobs**: duplicate `a8883a580e66` removed; `77bf232bfcb5` now Mon 12:00 UTC, deliver local,
   failure-deliver Slack, default model; `545d0f187758` runs the wrapper with failure-deliver Slack.
5. Initial extraction for 2026-09-21 done by Claude subagents (7 competitors, 102 programs, every item
   with a verbatim quote), history backfilled to 2026-03-31 (older structured snapshots searched as text).
6. **Fetch script concurrency capped** (`COMPETITOR_WATCH_CONCURRENCY=3`): the end-to-end test showed
   7 parallel Camoufox browsers starving each other on the 4-core / 8 GB VPS (load 18, every page.goto
   timing out, 22/53 pages). Wrapper budget 500 s inside the 600 s cron limit. Bounded rerun: 45/53 pages
   in 7 min with zero page timeouts. Workers now write after every page (a kill keeps partial results),
   per-competitor timeout 420 s, surviving workers killed at finalization, `--only` flag for tests.
   4geeks.com crashes the driver in-process, so it runs in per-page subprocess mode (75 s each, one
   retry); its capture stays partial and varies, which the reconciler tolerates (no removals on bad captures).

---

## 2026-09-25 — SEO assessment v2: scripts do the numbers, model does the judgement, fix outcomes tracked

**Context**: the twice-weekly "SEO: Intel & Audit" job (Hermes default profile, not OpenClaw; the
OpenClaw gateway is not running and its SEO cron entries are dead) cost ~1.4M prompt tokens and ~9 min
per run because the model re-queried GSC and hand-wrote the whole HTML report. Rudy also asked for
proper measurement of deployed backlog fixes ("did the change we expected actually happen?").

**What changed** (skill `~/.hermes/skills/ironhack/ironclaw-seo/`, backups in `.bak-2026-09-25/`):

1. **Data Fetch job** (`~/.hermes/scripts/seo-data-fetch.sh`, no_agent, Mon/Thu 10:00 UTC, ~4 min) now
   pulls everything: one 28-day GSC query (7-day windows derived from it, verified identical to direct
   queries), page-level recent + previous, GA4 recent + previous, `pr-impact.py` + open SEO PRs,
   `seo-live-check.py` (30 pages), `seo-news-fetch.py`, `seo-outcomes.py`, then `seo-analyze.py`.
2. **`seo-analyze.py`** computes every number and every analyst rule (GSC-vs-GA4 divergence, zero-click
   head-term skew with adjusted position, artifact exclusion via `references/artifact-pages.json`,
   AIO-risk pages, UTM variants, brand moves, small-sample flag, 4-week trends, bot ratio) into
   `memory/seo-data-DATE.json` + a ~24 KB `seo-digest-DATE.md` that is what the agent gets injected.
3. **`seo-build-report.py`** renders the full HTML (12 sections incl. new "Fix Outcomes" and "Live Site
   Health") and a Slack draft with every number pre-filled, from the data JSON + an optional narrative
   JSON written by the agent (`references/narrative-schema.md`). Automatic fallback text for every section.
4. **Fix outcomes**: backlog items carry an `outcome` definition (metric, direction, pages regex, markets,
   fix date, hypothesis). `seo-outcomes.py` measures 14-day baseline vs complete post-fix weeks (fix + 3d),
   vs the whole market as control, with verdicts confirmed / beat_market / market_wide / measuring /
   no_effect / regressed / new / low_volume / not_measurable (final after 8 weeks). `seo-backlog.py` CLI replaces
   hand-editing the JSON and refuses to resolve an item without an outcome (or an explicit not-measurable
   reason). Seeded 5 measurable fixes (homepage titles ES/DE/FR, NL title, DE cybersecurity title, UTM
   redirect, AI Engineering routing); first run already flags the DE cybersecurity title change as
   regressed (CTR 0.87% -> 0.42% over 3 weeks) and UTM variant impressions rising, not fading.
5. **Cron prompt** of `0c0c1fddcd38` replaced (`references/cron-prompt-v2.txt`): read digest -> backlog
   audit via CLI -> narrative JSON -> build -> journal -> Slack. `gsc-query.py` gained `--dims`,
   `pr-correlations.py` gained `--json`. SKILL.md bumped to 2.0.0 with a "Cron workflow v2" section.

6. **Slack post redesigned** (`seo-build-report.py --post`): Block Kit message posted by the generator
   itself (no more "Cronjob Response ... To stop or manage this job" wrapper): headline sentence, market
   scorecard with green/yellow/red status (GA4-aware), "Did our fixes work?" with verdict icons,
   watch-outs, ship next, backlog line, buttons to the report / fix outcomes / backlog; the detailed
   per-market numbers, 4-week trend, movers, PR signals and all auto signals go into a thread reply.
   Job `0c0c1fddcd38` switched to `deliver: local` with `failure-deliver: slack:C0B1MLM0L3X`.

7. **WD / UX redirect monitors retired** (jobs `fa35fc5c66f3`, `15a123239d81` paused). They had posted
   the same "Source impressions fading: 0" line for 8-16 weeks, and "Destination growing" was just weekly
   impressions on the course pages (AIO-noise, actually trending down). Their two functions moved into the
   weekly assessment: `seo-live-check.py` now checks all 50 legacy URLs from the two redirect maps (a
   broken 301 becomes a high-severity signal / Slack watch-out), and the consolidations are tracked as fix
   outcomes on four resolved backlog items (`wd|ux-consolidation-source-fade`,
   `wd|ux-consolidation-destination-clicks`, fix dates 2026-04-28 and 2026-07-04). Snapshot history kept
   in `workspace/wd-monitor/` and `ux-monitor/`; note the 2026-06-30 to 07-14 WD snapshots are UX data
   (shared-map bug).

**Verified**: full fetch run 222 s; report built with and without narrative; preview published at
`https://ih-ironclaw.s3.eu-west-1.amazonaws.com/seo/preview/report.html`; Block Kit post test-sent to
Rudy's DM. Next scheduled run: Mon 2026-09-28.

---

## 2026-09-25 — Argos performance report: channel tabs, funnel stages, device split, ad group/keyword alerts

**Context**: Pablo Gomez's feedback from the 2026-09-21 "Argos Optimizations" call. Argos is a
Hermes profile (`~/.hermes/profiles/argos/`), not an OpenClaw agent — edited directly over SSH.

**What changed** (originals backed up in `scripts/argos/.bak-2026-09-25/`):

1. **Collector `scripts/argos/performance_report.py`** — rewritten.
   - Channel classification from campaign name, Pablo's rule: `brand` → brand, `pmax` → pmax,
     `generic` (not pmax) → generic, `display`/`youtube` → display. Stored as `channel` (+ `type`).
   - Conversions split by funnel stage (primary conversion actions `Zapier … | Apps/QApps/TI/SA/BST`)
     via `segments.conversion_action_name`, at all 4 levels.
   - Device split (`segments.device`) at all 4 levels, each device with its own funnel split.
   - 3 queries per level per account (base / device / stage) → ~70 API calls, ~2 min.
   - Writes the full dataset (~2 MB) to `/tmp/argos_perf_data.json` and prints a ~30 KB summary
     (`totals_7d`, `by_channel_7d`, `movers_7d` for campaigns / ad_groups / keywords) instead of
     dumping 1.2 MB into the agent prompt. `--full-stdout` restores the old behaviour.
2. **Generator `generate_performance_report.py` + template `performance-report.html`** — nested tabs
   (period × channel, 15 views, URL-hash deep links), funnel strip, By Channel table, Device Split
   table, funnel column on every row, expandable per-row device sub-rows, richer takeaways (funnel
   concentration, device-mix shift, conversion movers). `--preview` / `--local` flags for safe testing.
3. **Cron job `argos-performance-report` prompt** — agent now uses the pre-computed summary; Slack
   post adds channel split, funnel line, and ad-group + keyword movers (generic prioritised).
4. **Skill docs** — `argos-reports/SKILL.md`, `references/slack-performance-template.md`,
   `google-marketing-intelligence/SKILL.md` updated (classification table, funnel stages, JSON shape).

5. **Slack post redesigned** (same shape as the SEO weekly): `scripts/argos/argos_slack.py`, called by
   `generate_performance_report.py --post`, posts a Block Kit message (headline, channel + market
   scorecards with GA-style traffic lights, funnel line, campaign conversion movers, generic ad groups and
   keywords to look at, watch-outs, actions, totals, buttons to full / generic / brand / 30-day views)
   plus a details thread (by channel, by market, devices, movers by conversions and spend, ad group and
   keyword movers). Agent writes `/tmp/argos-narrative.json` (`references/narrative-schema.md`). Job
   `f69227a6569b` switched to `deliver: local` + `failure-deliver: slack:C0BFMA3117F`, ending the double
   post (Block Kit + "Cronjob Response" wrapper). Prompt in `references/cron-prompt-v2.txt`.

**Deployed**: report regenerated and published to the stable URL
(`…/ironclaw/argos/shared/performance.html`); Block Kit post test-sent to Rudy's DM. Next scheduled cron run: Mon 2026-09-28 08:00 UTC.
Note: `cron doctor` still flags the 2026-09-24 run as "interrupted by shutdown" (the agent had
already posted to Slack; the job record was cut off) — clears on the next successful run.

---

## 2026-05-19 — Scout Job D: report redesign, top-10 filter, PDF fix

**What**: Four improvements to the per-bootcamp branded HTML reports.

1. **Top-10 filter** — reports now show only the 10 best-fit listings per bootcamp.
   Hard-excludes `german_required`. Sorted: `english_only` > `german_b1` > `unknown`, then
   `junior` > `entry_level` > `internship` > other. `active_count` now reflects filtered count.
2. **Branding** — new dark hero section (`#0d1b2a` gradient) behind the bootcamp name and
   description; larger logo (48px); "Germany Job Market Report" label in Ironhack blue.
3. **Job link clarity** — job title is no longer a link. Each card has an explicit
   "View listing →" button (top-right corner) that opens the LinkedIn URL in a new tab.
4. **PDF button fix** — replaced `onclick="window.print()"` inline handler with a
   `<script>` block using `addEventListener`. Avoids inline-event CSP blocks from S3.
   Button label changed to "Print / Save as PDF" to clarify it opens the browser print dialog.

**Changes:**
- `template-branded.md` — full HTML/CSS/JS rewrite of the report shell and card template
- `AGENTS.md` — Job D step 3: replaced `All active listings, no LIMIT` with explicit
  SQL query (LIMIT 10 + ORDER BY language/experience priority)
- Both files redeployed to server

---

## 2026-05-18 — Scout: switched to LinkedIn guest API, dropped StepStone

**What**: Replaced all scraping with LinkedIn's unauthenticated guest API.
- `GET /jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=...&location=Germany` — returns job cards (ID, title, company, location), no auth
- `GET /jobs-guest/jobs/api/jobPosting/<id>` — returns full job description HTML, no auth
- Both endpoints work from VPS IPs, return 200, no Playwright needed
- StepStone removed permanently (Akamai IP-blocks all VPS ranges with 403)
- Google and DuckDuckGo also blocked (CAPTCHA) so the Google→LinkedIn workaround was dead too
- Tavily dev key was over quota; residential proxies would cost $50-100/mo
- Guest API sidesteps all of it: pure urllib, zero dependencies

**Changes:**
- TOOLS.md: replaced Playwright/StepStone/LinkedIn sections with guest API functions
- AGENTS.md: scrape workflow now LinkedIn-only, max 10 listings per bootcamp (was 5 per portal × 2)
- Both files redeployed to server

**Pipeline status:** Jobs 01 (ai-web-dev) and 02 (data-analytics) already ran with old code (10 DB entries). Job 03 (ai-consulting-integration) firing with new code to validate.

---

## 2026-05-18 — Scout: 14-job chain, one job per bootcamp

**What**: Redesigned pipeline to 14 sequential jobs — one per bootcamp (jobs 01-12) plus
staleness check (C) and report generation (D). Each bootcamp job scrapes both StepStone and
LinkedIn for that single bootcamp, capped at 5 listings per portal (10 max per session).

**Why**: Previous approaches failed — 12-bootcamp single session timed out at 30 min;
12 parallel subagents hit API rate limits and the parent session (`sessions_yield`) was reaped
by the cron scheduler before subagents completed.

**Each bootcamp job does:**
1. StepStone search → verify up to 5 URLs through integrity gate → store with LLM summary
2. LinkedIn search → verify up to 5 URLs → dedup against existing → store with LLM summary
3. Post brief status to #ironclaw-jobs
4. Trigger next job

**Job IDs (01–12):**
- 01 ai-web-development: `b3a1c2d4-e5f6-4789-a0b1-c2d3e4f50001` (scheduled Wed 14:30 Rome)
- 02 data-analytics: `9ce2b7a8-fbaf-41c6-bb86-f355ffa658c7`
- 03 ai-consulting-integration: `3acb0b8f-1828-45ec-bb9a-bb524a4ffe15`
- 04 ai-driven-ux-ui: `a2022597-e706-4136-bedb-76e5c8613c3e`
- 05 data-science-ml: `4d44d5eb-2f88-401b-bdf3-5462306c6cf9`
- 06 ai-engineering: `23375e7a-a083-46e8-a7fc-03117c37c645`
- 07 cloud-engineering: `6ea65326-7ce7-4281-9253-35aa1cdd2951`
- 08 data-engineering: `2734a449-3f36-43e0-b054-aed00d8b4e1b`
- 09 ai-driven-marketing: `9acc1b09-642c-4a8f-b2bc-6b99a3ec7eaf`
- 10 cybersecurity: `6b290887-3dda-475e-b757-bb13b5440076`
- 11 ai-product-management: `88bc0fa2-c82b-4fac-840a-418d3df74624`
- 12 devops: `d5deea80-1e09-47ba-94bc-08b69b28fc93`
- C staleness: `f2de03a2-c9db-4687-be37-0e9c13159646`
- D reports: `b7d82600-3935-4055-9de4-670126646234`

---

## 2026-05-18 — Scout: subagent parallelism for StepStone scrape

**What**: Replaced the sequential-per-bootcamp approach in Job A with parallel subagents.
Job A now spawns 12 isolated subagents simultaneously (one per bootcamp), calls `sessions_yield`,
then merges all 12 JSON result files into the DB after they complete. Wall time drops from
~80 min to ~2-3 min for the StepStone phase.

**Architecture:**
- Job A (orchestrator): spawns 12 subagents via `sessions_spawn`, each with `runTimeoutSeconds: 600`
- Each subagent: scrapes StepStone for one bootcamp, writes `/tmp/scout-results-<slug>.json`, exits
- Job A: resumes after `sessions_yield`, reads all 12 JSONs, bulk-upserts to DB, triggers B
- Jobs B/C/D unchanged (LinkedIn runs sequentially — bot-detection sensitive)

**Job IDs (final, correct):**
- A (StepStone Scrape, scheduled): `b3a1c2d4-e5f6-4789-a0b1-c2d3e4f50001`
- B (LinkedIn Scrape): `9ce2b7a8-fbaf-41c6-bb86-f355ffa658c7`
- C (Staleness Check): `f2de03a2-c9db-4687-be37-0e9c13159646`
- D (Report Generation): `b7d82600-3935-4055-9de4-670126646234`

**Also**: Fixed deploy script (`--exclude='*.db'`) to prevent overwriting production jobs.db
with the empty repo placeholder. jobs.db was wiped once in this session and re-initialized.

**Fired and confirmed running:** all 12 subagents observed live in `openclaw tasks list`.

---

## 2026-05-18 — Scout: 4-job chain with LinkedIn, 13-report system, LLM summaries

**What**: Rewired ironclaw-jobs into a 4-job chain matching the SEO pipeline pattern. Added LinkedIn as a second job board source. Each job runs in an isolated session with clean context to prevent the 203k overflow that was hitting single-session scrapes.

**Pipeline:**
```
A (scheduled Wed 14:30 Rome) → B → C → D
StepStone scrape → LinkedIn scrape → Staleness check → Report generation
```

Each job triggers the next with `openclaw cron run <uuid>` at the end of its session.
Jobs B, C, D are registered as disabled crons with dummy schedules — they only fire when triggered.

**Job IDs:**
- A (StepStone Scrape): `b3a1c2d4-e5f6-4789-a0b1-c2d3e4f50001` — scheduled
- B (LinkedIn Scrape): `5f02fe2a-a467-4959-8052-98f3681052ca` — disabled
- C (Staleness Check): `265d5501-52ac-47ef-9c9e-cba6e79e1929` — disabled
- D (Report Generation): `b3a1c2d4-e5f6-4789-a0b1-c2d3e4f50002` — disabled

**Also in this session:**
- Job D now generates 13 reports: 1 general (table format, monitoring) + 12 per-bootcamp branded (Ironhack logo, card layout, LLM summary per listing, PDF export button)
- LLM summaries generated at scrape time, stored in new `summary TEXT` column
- TOOLS.md: LinkedIn search patterns, `scrape_linkedin.py` usage, bot detection notes; Indeed marked as blocked; Tavily demoted to fallback only
- DB migrated: `summary` column added to live jobs.db
- AGENTS.md and TOOLS.md synced to repo (server versions were more evolved)

**Still pending:** S3 bucket policy — add `arn:aws:s3:::ih-ironclaw/jobs/*` to public-read policy via AWS console.

---

## 2026-05-18 — Scout: 13-report system, LLM summaries, job chaining

**What**: Upgraded ironclaw-jobs (Scout) to generate 13 reports per run, add LLM-generated summaries per listing, and split scrape + report into chained sessions to prevent context overflow.

**Changes:**

1. **13 reports per run** — Workflow B now generates 1 general report (unchanged table format, for monitoring) + 12 per-bootcamp branded HTML reports. Each bootcamp report uses Ironhack branding (blue `#5BBFE3`, logo embedded as base64), card layout with job summary, and a `window.print()` PDF export button with `@media print` CSS.

2. **LLM-generated summaries** — Workflow A now generates a 2-3 sentence summary per listing at scrape time, covering role, key skills, and language/experience level. Stored in new `summary TEXT` column. Existing 145 listings have `summary = NULL` and will be populated during next staleness check.

3. **Job chaining** — Workflow A ends by posting "Trigger: generate caseworker report YYYY-MM-DD" to `#ironclaw-jobs`, which starts Workflow B in a fresh session with clean context. This prevents the combined scrape+report session from hitting the 203k context limit. The weekly Caseworker Report cron remains disabled — report is now triggered by scrape completion.

4. **DB migration** — added `summary TEXT` column to `jobs` table. Live migration applied on server. `init-db.py` updated to include the column in fresh installs.

5. **AGENTS.md + TOOLS.md synced to repo** — the server's evolved versions (with Playwright-first rules, URL integrity gates, slug consistency checks) are now in `server/workspace-ironclaw-jobs/`. Also fixed all DB access to use Python (sqlite3 CLI not installed).

**Still pending:** S3 bucket policy — add `arn:aws:s3:::ih-ironclaw/jobs/*` to public-read policy via AWS console.

---

## 2026-05-08 — SEO pipeline: delivery fixes, backlog system, WD redirect monitor

**What**: Fixed Slack delivery on SEO cron jobs, redesigned Step 3 as a codebase audit, added a persistent suggestion backlog, and created a new WD redirect monitoring pipeline.

**Changes:**

1. **Fixed delivery on steps 1 and 2** — both had `announce -> last` which fails for cron jobs (no triggering channel). Updated to explicit `slack:C0B1MLM0L3X`.

2. **Step 3 redesigned** — renamed "SEO: Implementation Audit". Now audits the `main` branch of `ironhack/foundry` and `ironhack/new-website-worker` directly (what Vercel deploys), instead of open PRs.

3. **Persistent backlog** (`seo-backlog.json`) — Step 3 now runs a 3-pass approach: resolution check (re-verify open items in current `main`), discovery audit (new findings only, deduplicated), then writes a report with New Today / Resolved / Backlog sections. Seeded empty.

4. **WD redirect monitor** — new weekly cron (Tue 14:30 Rome) for the WD course page consolidation. Created `wd-redirect-map.json` (25 source URLs, 12 destinations) and `wd-redirect-monitor.py` (HTTP 301 checks + GSC page-level queries). Report is narrative-driven: transfer rate, source fade, query character shift.

5. **Rescheduled all jobs to after 14:00** — z.ai is unreliable in the morning. Spread weekly jobs across days to avoid collisions:
   - Mon 14:30: Weekly Watch
   - Tue 14:30: WD Redirect Monitor
   - Wed 14:30: Weekly Job Scrape
   - Thu 14:30: Caseworker Report (disabled)
   - 14:00 daily: Course Content Review
   - 16:00 daily: SEO pipeline

---

## 2026-05-06 — ironclaw-jobs agent: fully registered and live

**What**: Completed server-side registration of the `ironclaw-jobs` agent (Scout). Workspace was already deployed in the previous session.

**Steps completed:**
1. Deployed workspace via `./scripts/deploy-workspaces.sh` (all 22 files including 12 bootcamp profiles)
2. Created agent dir: `/home/openclaw/.openclaw/agents/ironclaw-jobs/agent/` with `auth-profiles.json` (copied from ironclaw-seo)
3. Registered `ironclaw-jobs` in `openclaw.json` — added to `agents.list` and added binding for `C0B1KDU4Q8P`
4. Added 2 cron jobs to `cron/jobs.json`:
   - `b3a1c2d4-e5f6-4789-a0b1-c2d3e4f50001` — Weekly Job Scrape, Mon 09:00 Rome, enabled
   - `b3a1c2d4-e5f6-4789-a0b1-c2d3e4f50002` — Weekly Caseworker Report, Mon 10:00 Rome, disabled (triggered by scrape)
5. Ran `python3 init-db.py` — jobs.db initialized with `jobs` and `reports` tables
6. Restarted gateway — active (running), Slack socket mode connected

**Still pending:**
- S3 bucket policy: add `jobs/*` prefix to `ih-ironclaw` public-read policy. The IAM user (`ironclaw-s3-agent`) lacks `s3:GetBucketPolicy` — must be done via AWS console. Current policy covers `seo/*`, `edu/*`, `ironclaw/*`, `watch/*`. Add: `"arn:aws:s3:::ih-ironclaw/jobs/*"`

---

## 2026-05-06 — ironclaw-jobs agent: workspace built, pending server registration

**What**: Created the full workspace for a new `ironclaw-jobs` agent (Scout) that searches StepStone.de and Indeed.de for junior/entry-level jobs in Germany aligned with Ironhack's 12 bootcamps, stores listings in SQLite, and generates S3-hosted caseworker reports.

**Files created:**
- `server/workspace-ironclaw-jobs/` — complete workspace
  - `SOUL.md`, `AGENTS.md`, `TOOLS.md`, `MEMORY.md` — agent persona, session rules, environment config
  - `init-db.py` — initializes the SQLite schema on first run
  - `jobs.db` — 0-byte placeholder (schema created at first startup)
  - `bootcamps/` — 12 pre-extracted bootcamp profiles with job titles, search terms, language notes

**Repo changes:**
- `scripts/deploy-workspaces.sh` — added ironclaw-jobs rsync block
- `README.md` — added agent row, 2 cron job rows, workspace path, pending tasks
- `CLAUDE.md` — updated agent count, workspace table, priorities, channel ID

**Pending (server-side, not yet done):**
1. Deploy: `./scripts/deploy-workspaces.sh`
2. Register agent in `/home/openclaw/.openclaw/openclaw.json`
3. Bind Slack channel `C0B1KDU4Q8P` (`#ironclaw-jobs`) to `ironclaw-jobs`
4. Add 2 cron jobs: Mon 09:00 Rome (scrape) and Mon 10:00 Rome (report)
5. Add `jobs/*` to the `ih-ironclaw` S3 bucket public-read policy
6. Run `python3 init-db.py` on server after deploy to initialize jobs.db
7. Restart gateway: `systemctl --user restart openclaw-gateway`

**Agent details:**
- Slack channel: `#ironclaw-jobs` (ID: `C0B1KDU4Q8P`)
- Sources: StepStone.de + Indeed.de (Tavily primary, Playwright fallback)
- DB: SQLite at `workspace-ironclaw-jobs/jobs.db`
- Reports: S3 `ih-ironclaw/jobs/YYYY-MM-DD/report.html`
- Purpose: Generate evidence of German job market opportunities for 12 bootcamps, to convince Jobcenter/Arbeitsagentur caseworkers to approve public financing for students

---

## 2026-05-06 — SEO pipeline hardening: gsc-query.py, gh CLI, S3 public access, 16:00 reschedule

**What**: Hardened the 5-job SEO cron chain after the first morning run surfaced multiple failures.

**Fixes applied:**

1. **GSC auth broken (env vars not passed to exec subprocesses)**
   - Root cause: `OPENCLAW_SERVICE_MANAGED_ENV_KEYS` in `gateway.systemd.env` did not include `GOOGLE_SA_KEY_PATH` or `GOOGLE_IMPERSONATE_EMAIL`.
   - Fix: Added both keys to `OPENCLAW_SERVICE_MANAGED_ENV_KEYS`, restarted gateway.

2. **Agent writing broken GSC code instead of using script**
   - Root cause: No pre-built script existed; agent was generating its own API code and getting it wrong.
   - Fix: Wrote and deployed `gsc-query.py` to `/home/openclaw/.openclaw/workspace-ironclaw-seo/` with hardcoded credentials (no env var dependency). Script handles pagination, client-side country filtering (GSC AND-logic quirk), and outputs clean JSON.
   - Updated Job 1 to call the script explicitly.

3. **GSC 0 rows (country filter AND-logic bug)**
   - Root cause: Script used `dimensionFilterGroups` with multiple `equals` filters — GSC interprets these as AND, returning nothing.
   - Fix: Script now pulls all rows (paginated to 25k) and filters client-side by `keys[1]` country value.

4. **S3 presigned URLs instead of permanent public URLs**
   - Root cause: Bucket had Block Public Access enabled, so `--acl public-read` failed silently; agent fell back to presigning.
   - Fix: Disabled all 4 Block Public Access settings on `ih-ironclaw` bucket. Added bucket policy granting `s3:GetObject` on prefixes `seo/*`, `edu/*`, `ironclaw/*`, `watch/*`.
   - Updated Job 5 to use plain `aws s3 cp` without `--acl`.
   - Updated TOOLS.md for both seo and edu agents: "NEVER use presigned URLs."

5. **Slack bot token missing errors (morning z.ai degradation)**
   - Root cause: Chinese peak hours cause z.ai service degradation; Slack delivery fails intermittently.
   - Fix: Rescheduled Job 1 from `0 6 * * *` to `0 16 * * * @ Europe/Rome` (4 PM Rome). Jobs 2-5 chain from Job 1 so all shift together.

6. **Job 3 using Python GitHub API instead of `gh` CLI**
   - Fix: Installed `gh` CLI (`gh version 2.45.0`) via `apt-get`. Tested against `ironhack/foundry` — confirmed working.
   - Updated Job 3 to use `gh pr list` and `gh pr diff` commands.
   - Updated `server/workspace-ironclaw-seo/TOOLS.md` Website Repo section to document `gh` commands.

7. **S3 folder was `optimizer/` instead of `seo/`**
   - Fix: Updated all jobs and TOOLS.md to use `seo/YYYY-MM-DD/` folder.

**ironclaw agent auth profiles fix:**
- Agent dirs `ironclaw-seo` and `ironclaw-edu` had no `auth-profiles.json` — agents couldn't connect to any LLM provider.
- Fix: Created agent dirs and copied `auth-profiles.json` from main ironclaw agent. Restarted gateway.

**Still pending:**
- Run `./scripts/deploy-workspaces.sh` to push updated TOOLS.md (rsync blocked in this session).
- Old Weekly SEO Report (`af48e2f2`) still active — redundant, should be removed.
- Verify full 5-job chain succeeds at 16:00 Rome run on 2026-05-06.

---

## 2026-05-05 — SEO daily cron chain: 5-job pipeline

**What**: Replaced single Weekly SEO Report with a 5-job chained daily pipeline for ironclaw-seo. Each job triggers the next via `openclaw cron run <id>`. Jobs 2-5 are disabled (no auto-schedule) and only fire via the chain.

| Job ID | Name | Fires | Output |
|---|---|---|---|
| `39031b84` | GSC Snapshot | 06:00 daily | `memory/YYYY-MM-DD.md` |
| `4289a69c` | Research Journal | triggered | appends to `seo-journal.md` |
| `6c85765e` | Repo Analysis + Proposals | triggered | `repo-proposals-YYYY-MM-DD.md` |
| `cc4c2154` | PR Correlation + Daily Brief | triggered | `pr-correlations-YYYY-MM-DD.md` + Slack text |
| `48960c69` | HTML Report | triggered | S3 HTML + Slack URL |

HTML report uploaded to `ih-ironclaw` S3 with `--acl public-read`. Permanent URL pattern: `https://ih-ironclaw.s3.eu-west-1.amazonaws.com/optimizer/YYYY-MM-DD/report.html`. Bucket "Block public ACLs" setting disabled to allow this.

**Still active (redundant):** old Weekly SEO Report (`af48e2f2`) — review and remove.

---

## 2026-05-05 — SEO agent (ironclaw-seo) fully wired

**What**: Completed the ironclaw-seo (Optimizer) agent setup end-to-end.

**Workspace fixes:**
- Corrected Slack channel from `#ironclaw-optimizer` → `#ironclaw-seo` (ID: `C0B1MLM0L3X`) in TOOLS.md and AGENTS.md
- Added GitHub repos: `ironhack/foundry` and `ironhack/new-website-worker` (read + PR access)
- Added GSC property: `https://www.ironhack.com/` with country-dimension filtering for ES, PT, FR, NL, DE

**Credentials added to `gateway.systemd.env`:**
- `GITHUB_TOKEN` — fine-grained PAT, read access to both repos including PRs
- `GOOGLE_SA_KEY_PATH` — service account JSON at `/home/openclaw/.openclaw/gsc-service-account.json` (project `ironclaw-495411`)
- `GOOGLE_IMPERSONATE_EMAIL=rodolfo.puglia@ironhack.com` — domain-wide delegation target

**GSC auth setup:**
- Tried service account direct → GSC UI rejected the email (Workspace org policy)
- Set up domain-wide delegation: GCP service account client ID `117678558143014238882`, Workspace Admin authorized scope `webmasters.readonly`
- Tested live: GSC API returning real data (ES: 822 clicks / 113K impressions; FR: 659 / 126K; DE: 423 / 76K for week of Apr 21-27)

**Cron chain (3 jobs, daily):**
| Job | ID | Schedule | Status |
|---|---|---|---|
| SEO: Daily GSC Snapshot | `39031b84` | 06:00 daily Rome | enabled, triggers next |
| SEO: Daily Research Journal | `4289a69c` | disabled | triggered by Job 1 |
| SEO: Repo Audit + Daily Brief | `6c85765e` | disabled | triggered by Job 2, posts to #ironclaw-seo |

Chain flow: Job 1 pulls GSC data + saves snapshot → Job 2 searches web for SEO/GEO news + updates journal → Job 3 audits GitHub PRs, correlates with rankings, posts daily brief.

**Old "Weekly SEO Report" cron job still active** — review and remove if redundant.

**Still open:**
- Firecrawl API key still PLACEHOLDER in `gateway.systemd.env`

---

## 2026-05-05 — AWS CLI installed + S3 credentials restored

**What**: AWS credentials were in `/home/openclaw/.openclaw/.env` but not copied to `gateway.systemd.env` during migration — bot couldn't reach S3. Fixed by adding `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` to `gateway.systemd.env`. Installed AWS CLI v2 (official installer, Ubuntu 24.04 apt package not available). Fixed stale Docker paths in `workspace/TOOLS.md` (`/home/node/` → `/home/openclaw/`). S3 bucket `ih-ironclaw` (eu-west-1) confirmed accessible.

---

## 2026-05-05 — Tavily + DuckDuckGo search enabled

**What**: Set Tavily API key in `gateway.systemd.env` (replaces PLACEHOLDER). Also enabled DuckDuckGo plugin as fallback. Gateway restarted.

---

## 2026-05-05 — Multi-agent architecture finalized + #ironclaw-watch context

**What**: Settled on 3-agent design: ironclaw (router + competitive intel), ironclaw-seo, ironclaw-edu. Added per-channel `systemPrompt` to `#ironclaw-watch` (C0B1MM39P8D) so ironclaw automatically frames conversations there as competitive analysis across ES/PT/FR/NL/DE. Uses OpenClaw's `channels.slack.channels[id].systemPrompt` field. Channel binding stays: ironclaw-watch → ironclaw agent (chat + cron delivery).

---

## 2026-05-05 — Telegram removed

**What**: Disabled Telegram channel (`channels.telegram.enabled: false`) and removed its binding. Gateway now runs 7 plugins (was 8). Slack is the only active channel.

---

## 2026-05-05 — Slack channel bindings finalized

**What**: Finalized Slack channel routing. Removed catch-all binding (was routing all channels including delivery-only ones to ironclaw). Added explicit binding for `#ironclaw-watch` (C0B1MM39P8D) → ironclaw agent, so it supports both interactive chat and cron digest delivery. Final bindings:
- `#ironclaw-watch` → ironclaw (chat + cron delivery)
- `#ironclaw-seo` → ironclaw-seo
- `#ironclaw-edu` → ironclaw-edu
- DMs → ironclaw (via pairing, no binding needed)

Also added `channels.slack.channels: { "*": { requireMention: false } }` so channels respond to all messages without needing @mention.

---

## 2026-05-05 — Slack channel messages enabled (requireMention: false)

**What**: OpenClaw's Slack plugin defaults to `requireMention: true` in channels, silently dropping all non-mention messages. Added `channels.slack.channels: { "*": { requireMention: false } }` to `openclaw.json` so the bot responds to all messages in channels it belongs to, without needing an @mention. Gateway restarted.

---

## 2026-05-05 — Slack routing: DM binding + Rudy pairing

**What**: Replaced the `#ironclaw` channel binding with a catch-all Slack binding (no `accountId`), so DMs from any paired user route to the ironclaw agent. `#ironclaw-seo` and `#ironclaw-edu` channel bindings remain and take priority. Rudy's Slack account (`U02MV9VPGV6`) approved and set as command owner via `openclaw pairing approve slack WSVMMXHJ`. Gateway restarted, socket mode reconnected.

---

## 2026-05-05 — Slack app recreated, tokens updated

**What**: Slack app was recreated (new App ID: `A0B19LV97DM`, previous: `A0B1NSXT18W`). Updated `SLACK_BOT_TOKEN` and `SLACK_APP_TOKEN` in `gateway.systemd.env` on the server. Restarted `openclaw-gateway` (user systemd service). Slack socket mode confirmed connected. Channels unchanged.

---

## 2026-05-05 — Docker → bare-metal migration + multi-agent expansion

**What**: Replaced Docker setup with a bare-metal systemd install. Expanded from one agent to three. Upgraded search provider. Registered 3 cron jobs.

**Migration steps completed:**
- Backed up live data from running container via `docker cp` to `/home/openclaw/openclaw-backup-20260505`
- Moved data dir from `/root/.openclaw` (root-owned, Docker) to `/home/openclaw/.openclaw` (openclaw-user-owned, bare-metal)
- Installed Node.js 24 via NodeSource PPA
- Installed `openclaw@2026.5.4` globally via npm (upgraded from Docker version 2026.3.30)
- Installed gateway as a user systemd service (`openclaw-gateway.service`), enabled linger for boot persistence
- Stopped Docker containers (`openclaw-openclaw-gateway-1`, `openclaw-openclaw-cli-1`) — both removed
- Removed Docker image `openclaw:local`
- Fixed `OPENAI_API_KEU` typo in env — now correctly `OPENAI_API_KEY`

**Config changes (`openclaw.json`):**
- Fixed workspace path (was Docker-internal `/home/node/...`, now `/home/openclaw/.openclaw/workspace`)
- Added `agents.list` with three named agents: `ironclaw` (default), `optimizer`, `education`
- Added `bindings` routing Telegram → ironclaw, Slack channels → respective agents (channel IDs are PLACEHOLDER pending Slack app setup)
- Switched web search provider: `duckduckgo` → `tavily`
- Added Firecrawl for web fetch (bypasses bot blockers)
- Added Slack channel config (tokens pending)
- Renamed agent dir `main` → `ironclaw`

**Cron jobs registered:**
| Job | Agent | Schedule | ID |
|---|---|---|---|
| Weekly Competitor Watch | ironclaw | Mon 07:00 Rome | `2f2508cc` |
| Weekly SEO Report | ironclaw-seo | Mon 08:00 Rome | `ee6d4f9e` |
| Course Content Review Loop | ironclaw-edu | Daily 06:00 Rome | `2d5e3786` |

**Pending (blocked by missing credentials/setup):**
- Workspace files for optimizer and education agents: written locally in `server/`, deploy with `./scripts/deploy-workspaces.sh` once classifier allows rsync
- Slack app setup: create at api.slack.com, fill `SLACK_BOT_TOKEN` + `SLACK_APP_TOKEN` in `gateway.systemd.env`
- Slack channel IDs: replace `PLACEHOLDER_*_CHANNEL_ID` in `openclaw.json` bindings and cron job delivery targets
- Tavily API key: replace PLACEHOLDER in `gateway.systemd.env`
- Firecrawl API key: replace PLACEHOLDER in `gateway.systemd.env`
- Composio API key + OAuth: for Google Search Console MCP (Optimizer agent)
- Device re-pairing: run `openclaw pair` to re-pair control UI and any other clients
- Education agent: set course repo + populate `review-queue.json` before enabling cron

---

## 2026-05-05 — Initial audit

**What**: First exploration of the server. No changes made.

**Found**:
- OpenClaw 2026.3.30 running on Ubuntu 24.04 (`openclaw-ironhack`) via Docker Compose
- Gateway container healthy (ports 18789-18790); CLI container dead since initial deploy (2026-04-01, exit code 1)
- Primary model: ZAI/GLM-5-turbo with GLM-4.7 fallback
- Telegram channel active; DuckDuckGo search; AWS + GitHub access configured
- Custom workspace with full IronClaw persona (SOUL.md, IDENTITY.md, MEMORY.md) and two custom skills: `course-reviewer`, `competitor-watch`
- Bug: `.env` has `OPENAI_API_KEU` typo — should be `OPENAI_API_KEY`

**Decision**: Replace Docker with a bare-metal systemd install. See README.md for migration checklist.

**Committed**: `README.md` with full server documentation.
