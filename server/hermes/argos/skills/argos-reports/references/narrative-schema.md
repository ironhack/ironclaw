# Argos narrative JSON (written by the agent, read by generate_performance_report.py --post)

Path: `/tmp/argos-narrative.json`. Every key optional; the Slack post falls back to automatic text for anything missing. Numbers must come from the collector summary. No em dashes.

```json
{
  "headline": "ONE sentence: what happened this week and what it means (first line of the Slack post)",
  "findings": ["what, where, what to do", "..."],
  "actions": ["Pause MAD Generic High: EUR 1,773 at 0.10x ROAS, 13 conversions", "Raise BER Brand DE budget: capped at 126% with 6.6x ROAS", "..."],
  "channel_notes": {"brand": "one line", "generic": "one line", "pmax": "one line", "display": "one line"}
}
```

The Slack post (`argos_slack.py`, posted by the generator with `--post`):
- header "Google Ads weekly · <7d window>"
- `headline`, then a channel scorecard (green = conversions up 5%+ at CPA not worse than +10%; red = conversions down 15%+ or ROAS down 25%+ on flat/higher spend; yellow otherwise; white = negligible spend) and a market scorecard (BER / AMS / MAD / LIS / PAR from the campaign-name prefix)
- funnel line Apps › QApps › TI › SA › BST with previous → current and % change
- biggest campaign movers by conversions (3 down, 2 up) with spend delta and ROAS
- ad groups and keywords to look at (generic/pmax first)
- `findings` -> Watch-outs, `actions` -> Actions
- totals line (spend, conversions, CPA, ROAS with deltas) and buttons: full report, generic view, brand view, 30 days
- thread reply: by channel, by market, devices, campaign movers by conversions and by spend, ad group movers, keyword movers, `channel_notes`

Manual use: `python3 argos_slack.py /tmp/argos_perf_data.json --narrative n.json --to U02MV9VPGV6 --post` posts a preview to a DM.

# Daily sanity narrative (written by the agent, read by generate_sanity_report.py --post)

Path: `/tmp/argos-sanity-narrative.json`. Every key optional; the post falls back to automatic text. Numbers must come from the collector summary (the stdout of `sanity_check.py`, also `argos_sanity_slack.py data --summary`). No em dashes.

```json
{
  "headline": "ONE sentence: what needs a hand today and whether it is new or carried over",
  "findings": ["what, where, what to do", "..."],
  "actions": ["Cap or pause BER Generic BGS DE: 158% of budget, 0 conversions, spend rising", "..."],
  "notes": "optional free text for the thread"
}
```

The post (`argos_sanity_slack.py`, see `slack-sanity-template.md`): header, headline, market scorecard, needs-a-hand list with new / day-N markers, raise candidates, cleared items, `findings` -> Watch-outs, `actions` -> Actions, context line, buttons; thread with every serving campaign, ad policy and the dead-weight list.
