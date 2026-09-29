# Slack Performance Report Summary — block structure & computation pattern

> **Superseded 2026-09-25 for the cron job.** The weekly post is now generated and posted by
> `scripts/argos/argos_slack.py` (called by `generate_performance_report.py --post`): headline, channel + market
> scorecards, funnel, campaign / generic ad group / keyword movers, watch-outs, actions, totals, buttons, details in a
> thread. The agent only writes `/tmp/argos-narrative.json` (see `references/narrative-schema.md`). Everything below
> is kept for ad-hoc Slack answers and as the reasoning reference for the narrative (lead-insight branching, mover
> edge cases, short names).

Companion to `references/slack-sanity-template.md`. This is the *weekly* performance report
message (Mon + Thu), not the daily sanity check. Verified working 2026-08-17.

## Structure (block order) — updated 2026-09-25 (Pablo's feedback: channel, funnel, ad group + keyword alerts)

1. **Header** — `"Argos Performance Report — YYYY-MM-DD"` (`header` block, `emoji: true`).
2. **Lead insight** — one sentence, the headline finding *before* any numbers.
3. **KPI summary** — Spend, Conversions, CPA, ROAS for last 7d across all accounts, each with WoW % direction.
4. **Channel split** — one line per channel from `by_channel_7d` (brand / generic / pmax / display): `conv prev→cur, ROAS prev→cur, CPA` — and say which channel is the drag / driver.
5. **Funnel** — `Apps › QApps › TI › SA › BST` prev→cur with % per stage from `totals_7d.*.stages`; name the stage where the change concentrates. Ignore stages with < 5 conversions (BST is always tiny).
6. **Divider**.
7. **Campaign movers by conversions** — up to 3 up (`:small_red_triangle:`) / 3 down (`:small_red_triangle_down:`) from `movers_7d.campaigns.conversions_up/down`, each with cost delta and ROAS prev→cur. Mark `status != ENABLED` as `*(paused)*`.
8. **Ad group movers** — 3 up / 3 down from `movers_7d.ad_groups.conversions_*`, prioritising `channel` generic / pmax. Format: `*BER Generic · CY-Cybersecurity-en* conv 12→1 (−€210)`.
9. **Keyword movers** — 3 up / 3 down from `movers_7d.keywords.conversions_*`, prioritising generic. Format: `*BER Generic · "cybersecurity courses"* conv 12→1 (−€251)`.
10. **Device note** — only if any `totals_7d.*.devices.<dev>.conv_share` moved ≥ 0.05 between previous and current.
11. **Report link** — `:bar_chart: <S3_URL|View Full HTML Report>` (tip: deep links work — `performance.html#last_7d/generic`).

## Key technique: use the injected summary — never hand-add

Since 2026-09-25 the collector's stdout **is** a pre-computed summary (`totals_7d`, `by_channel_7d`,
`movers_7d`) built from the same `/tmp/argos_perf_data.json` the HTML uses, so the Slack numbers and
the report agree by construction. Read those numbers straight from the injected JSON (or from
`/tmp/argos_perf_summary.json` if you re-ran the collector) inside `slack_post.py`. Only the
*interpretation* (lead insight, "the drag lives in…") is hand-written.

Legacy pattern (still valid if you only have the full dataset): sum `campaigns.last_7d.current` vs `.previous`:

```python
def totals(d):
    c = conv = val = 0.0
    for r in d.values():
        c += r.get("cost", 0) or 0
        conv += r.get("conversions", 0) or 0
        val += r.get("conversions_value", 0) or 0
    return {"cost": c, "conversions": conv, "value": val,
            "cpa": c / conv if conv else 0.0,
            "roas": val / c if c else 0.0}
```

Top movers = sort `current.cost - previous.cost` per campaign (skip |delta| < 10), take 3
from each end. This makes the message's numbers and the HTML report agree exactly.

### Mover line format (verified 2026-09-10)

A bare spend delta is meaningless without its efficiency impact. Each mover line should carry
conversions AND ROAS alongside the cost delta so the reader sees *why* the move matters:

```
:small_red_triangle: *BER Brand DE* +€629 (conv 74→63, ROAS 12.73→5.84)
:small_red_triangle_down: *PAR Brand EN* −€110 (conv 7→26, ROAS 0.74→10.14)
```

Full campaign names (`BER_Germany_Berlin_Global_Search_Brand_DE`) are too long for Slack —
shorten them with a helper keyed to the naming convention
`{MARKET}_{Country}_{City}_Global_{Channel}_{Type}_{Subtype}_{LANG}`:

```python
def short_name(name):
    parts = name.split('_')
    market = parts[0]                                    # BER / AMS / MAD / LIS / PAR
    lang = parts[-1] if len(parts[-1]) == 2 else ''      # DE / EN / ES / PT / FR
    typ = ('Brand' if 'Brand' in name else
           'PMAX' if 'PMAX' in name else
           'Display' if 'Display' in name else
           'Generic' if 'Generic' in name else
           'Awareness' if 'Awareness' in name else '')
    return ' '.join(x for x in [market, typ] if x) + (f' {lang}' if lang else '')
```
→ "BER Brand DE", "BER Generic", "BER PMAX", "AMS Display EN", "MAD Generic" (subtype "High" drops — fine).

Since 2026-09-25 every entity in the JSON also carries `channel` (brand / generic / pmax / display)
computed with the same rule the HTML uses — prefer `e["channel"]` over re-deriving it from the name.
(`type` holds the same value for backward compatibility; PMAX and display are no longer lumped into generic.)

The channel-split line (`brand: ROAS 7.16x, CPA €32 — healthy` vs `generic: ROAS 1.49x, CPA €102 — the drag`)
sums up *where* the problem lives before naming individual campaigns — it's now a required block (see Structure).

### Mover selection edge cases (verified 2026-09-21)

- **A PAUSED campaign is often the biggest raw spend decrease** — it stopped spending, which is not a performance signal. Annotate it `*(paused)*` so the reader doesn't treat it as a decision to investigate.
- **The "up" side can have fewer than 3.** When spend broadly declines, `take 3 from each end` may yield only 1–2 positive-delta campaigns. List what exists (2 up + 3 down is fine); never pad the "up" list with a negative-delta campaign.
- **Raw spend movers ≠ the efficiency story when spend is flat-ish but conversions crater.** In that regime the biggest *spend* decreases are usually healthy pullbacks (paused campaigns, or campaigns whose ROAS *improved*), while the damaging efficiency collapse lives in campaigns whose spend barely moved. Flag those separately in the `notable changes` line with conv + ROAS prev→cur (e.g. "BER Brand DE (conv 78→45, ROAS 9.6→4.0)"), and put the brand-vs-generic ROAS split there too.

## Analyze first, then post

The lead insight and "notable changes" lines need interpretation, and hand-summing 13+ campaigns to get the numbers is error-prone. Two-step pattern (verified 2026-08-24):

1. Write a throwaway `/tmp/argos_analyze.py` that prints exact totals (spend / conversions / value / CPA / ROAS with % deltas), per-campaign cost deltas (with conversions + ROAS prev→cur), and the full campaign list sorted by type. Run it and *read* the printed numbers to hand-verify against the injected JSON and pick the headline insight.
2. Then write `/tmp/slack_post.py` with the programmatic `totals()` + mover computation (below) AND the crafted lead-insight + notable-changes text embedded. Numbers always come from the programmatic compute so they match the HTML exactly; only the *interpretation* is hand-written.

## Lead-insight branching (say the anomaly first)

- spend down **and** conversions down by more → "spend down X% but conversions down Y% — efficiency deteriorating, ROAS fell, CPA rose".
- spend up **but** conversions down → ":red_circle: paying more for fewer conversions".
- spend flat/up but **conversions_value** drops far faster than conversions → ":warning: tracking/pixel suspect, not performance" — see the "Efficiency Drop: Performance vs Tracking Diagnostic" section in `argos-intelligence`. Check brand `conversions_value` across accounts before blaming efficiency.
- otherwise → flat "Spend X%, conversions Y%. ROAS Zx, CPA €N.".

Use `:warning:` (yellow) for efficiency drift, `:red_circle:` only for spend-up/conversions-down.

## Emoji (Slack `:name:` only — never Unicode)

`:warning:` `:red_circle:` `:small_red_triangle_down:` `:small_red_triangle:` `:arrow_up:`
`:arrow_down:` `:arrow_right:` `:bar_chart:` `:white_check_mark:`

## Constants

- Channel: `C0BFMA3117F`
- Endpoint: `https://slack.com/api/chat.postMessage`
- Token: `SLACK_BOT_TOKEN` from `~/.hermes/profiles/argos/.env` (line-by-line parse, strip quotes).
- Stable report URL: `https://ih-ironclaw.s3.eu-west-1.amazonaws.com/ironclaw/argos/shared/performance.html`
- Verify response has `ok: true` and capture `ts`; exit non-zero on `ok: false`.

## Ad group + keyword movers need the drill-down data

Since 2026-09-25 the message includes ad group and keyword movers (Pablo's request: the
per-campaign conversion alert alone doesn't tell him *which* generic ad group / keyword moved).
These come from `movers_7d.ad_groups` and `movers_7d.keywords` in the injected summary, so a
campaign-only dataset is no longer enough — if the summary is missing, re-run the collector
rather than posting a campaign-only message.
