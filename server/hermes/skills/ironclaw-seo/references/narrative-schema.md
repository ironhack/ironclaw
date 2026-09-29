# Narrative JSON schema (written by the agent, read by seo-build-report.py)

Path: `/tmp/seo-narrative.json`. Every key is optional; the report renders with automatic fallback text for anything missing, so a partial file is always better than none. Numbers must come from the digest. No em dashes.

```json
{
  "headline": "ONE sentence: the story of the week and what it means (drives the Slack post's first line)",
  "tldr": ["decision-first bullet", "second bullet", "third bullet"],
  "findings": ["what, where, what to do", "..."],
  "traffic_quality": "1-2 lines on engagement gaps, e.g. FR 53% engaged vs DE 44%; NL quality is there but discovery is the bottleneck.",
  "insights": {
    "snapshot": "1-2 sentences under the combined GSC+GA4 table",
    "trend": "1-2 sentences under the 4-week trend",
    "engagement": "1-2 sentences under the engagement table",
    "movers": "1-2 sentences under top movers",
    "pages": "1-2 sentences under top pages / AIO risk",
    "outcomes": "1-2 sentences under fix outcomes: which verdicts changed, what to do about regressed/no_effect items",
    "prs": "1-2 sentences under PR correlations",
    "live": "1-2 sentences under live site health"
  },
  "market_notes": {"esp": "one line", "fra": "one line", "deu": "one line", "prt": "one line", "nld": "one line"},
  "intel": [
    {"title": "headline from the digest", "source": "seroundtable", "date": "2026-09-24", "why": "why it matters for Ironhack this cycle"}
  ],
  "pr_notes": {"44": "interpretation of PR #44's measured impact", "42": "..."},
  "in_flight": {"og-tags-missing": 666, "schema-eduorg-missing-local": 677},
  "quick_wins": ["merge PR #666 (OG tags) - closes two High items", "..."],
  "research_line": "1-2 lines for the Slack RESEARCH section (omit if nothing notable)"
}
```

Slack post (Block Kit, posted by `seo-build-report.py --post`): `headline` -> first line; market scorecard is automatic (green = clicks up and GA4 agrees, red = clicks down 10%+ with GA4 not contradicting, yellow = flat or GSC/GA4 diverging); "Did our fixes work?" comes from the outcomes; `findings` -> Watch-outs; `quick_wins` (or open SEO PRs) -> Ship next; `research_line` -> Worth knowing; backlog line and buttons are automatic; a thread reply carries the per-market numbers, 4-week trend, movers, PR signals and all auto signals.

Section map (HTML): `tldr` + `findings` render as a box under the header and feed the Slack TL;DR / FINDINGS; `insights.*` render as the blue boxes under each section; `market_notes` fill the Insight column of the engagement table; `intel` replaces the raw headline list; `in_flight` tags backlog rows with "PR #n in flight"; `quick_wins` render under the backlog and in Slack.

Fix outcomes come from `seo-outcomes.py` (run by the fetch job). Verdicts: confirmed (moved as hoped and beat the market) / beat_market (did not move as hoped in absolute terms but outperformed the market control) / market_wide (moved with the market, not attributable) / measuring / no_effect / regressed (moved the wrong way and no better than the market) / new / low_volume / no_data / not_measurable. When you resolve a backlog item you MUST define its outcome first:

```
seo-backlog.py set-outcome <id> --metric ctr|clicks|impressions|position --direction up|down \
   --pages-regex '<RE2 regex on the full URL>' [--markets esp,deu] [--queries-regex '...'] \
   --hypothesis "what we expect to change and why" [--fix-date YYYY-MM-DD] [--min-effect 10]
seo-backlog.py resolve <id> --note "how verified on the live site"
```
or `seo-backlog.py resolve <id> --note "..." --not-measurable "why no GSC metric captures it"`.
