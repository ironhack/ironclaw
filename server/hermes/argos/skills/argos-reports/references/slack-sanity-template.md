# Slack post - Daily sanity check (v2, since 2026-09-29)

The post is built and sent by `scripts/argos/argos_sanity_slack.py`, called from
`generate_sanity_report.py --post`. The agent never writes Slack code; it only writes the narrative JSON
(`references/narrative-schema.md`, section "Daily sanity"). One post per run, details in a thread.

## Shape (same family as the weekly performance post)

1. header `Google Ads daily check · YYYY-MM-DD`
2. **headline** (narrative, else automatic): what needs a hand today, new vs carried over, cleared count
3. market scorecard `BER AMS MAD LIS PAR`: red = a campaign over budget with 0 conversions or a disapproved
   ad; yellow = over budget with ROAS < 1, at the cap with 0 conversions, or a raise candidate; green = clean
4. **Needs a hand today**: red lines (over budget + 0 conversions, disapproved ads) then yellow lines, each
   with spend vs budget, %, conversions / ROAS, spend trend; `:new:` if first seen today, `(day N)` if carried
5. **Capped but efficient (raise candidates)**: >= 80% consumed at ROAS >= 2
6. **Cleared since last check**: issues present at the previous run and gone today
7. **Data gaps** (only when an account query failed)
8. **Watch-outs** (narrative `findings`), **Actions** (narrative `actions`, else automatic)
9. context line: serving campaigns checked, dead enabled-but-ended count by pattern, "yesterday's spend vs daily budget"
10. buttons: Open report, Weekly performance
11. thread: every serving campaign with flag, ad policy list, enabled-but-ended campaigns grouped by pattern, `notes`

## Flags (computed in `argos_sanity_slack.summarize`, serving campaigns only)

| flag | rule | where it shows |
|---|---|---|
| over_no_return | >= 100% of budget and 0 conversions | Needs a hand (red) |
| over_weak | >= 100% and ROAS < 1 | Needs a hand (yellow) |
| capped_no_return | 80-100% and 0 conversions | Needs a hand (yellow) |
| raise | >= 80% and ROAS >= 2 | Raise candidates |
| near_cap | >= 80% otherwise | thread only |
| ok | < 80% | thread only |

Enabled-but-ended campaigns (serving_status ENDED, 0 impressions in 7 days) are dead weight: counted in the
context line and listed in the thread, grouped as experiments / legacy remarketing / seasonal / other. They
are never listed in the main post unless new ones appear (the `:new:` count in the context line).

## State

`/home/openclaw/ironclaw-data/argos/sanity-state.json` keeps `first_seen` / `last_seen` per issue id
(`budget:<campaign_id>`, `ad:<ad_id>`, `ns:<campaign_id>`). Updated only by a real post (not `--to` previews);
issues unseen for 60 days are forgotten.

## Manual use

```
python3 argos_sanity_slack.py /tmp/argos_sanity_data.json --summary            # what the agent sees
python3 argos_sanity_slack.py /tmp/argos_sanity_data.json --narrative n.json   # text render, no post
python3 generate_sanity_report.py /tmp/argos_sanity_data.json --narrative n.json --to U02MV9VPGV6 --post   # DM preview
```

Rules that still apply: Slack `:shortcodes:` only (the module converts its own icons), no `execute_code`
in cron mode, the token is read line by line from the profile `.env`.
