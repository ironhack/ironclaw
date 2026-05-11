# TOOLS.md - Optimizer Environment

## Google Search Console

Access via pre-built script — do NOT write your own GSC API code.

- Script: `/home/openclaw/.openclaw/workspace-ironclaw-seo/gsc-query.py`
- Usage: `python3 gsc-query.py <start-date> <end-date> [country1 country2 ...]`
  - Dates: `YYYY-MM-DD` format
  - Countries: `esp`, `prt`, `fra`, `nld`, `deu` (ISO alpha-3, lowercase)
  - No countries arg = all markets
- Output: JSON `{"rows": [...], "total_fetched": N, "total_filtered": N}`
  - Each row: `{"keys": [query, country, page, date], "clicks": N, "impressions": N, "ctr": F, "position": F}`
- Property: `https://www.ironhack.com/`
- Credentials are hardcoded in the script — no env var setup needed

## Website Repo

- Main site: `ironhack/foundry`
- Worker/edge: `ironhack/new-website-worker`
- Use `gh` CLI — GITHUB_TOKEN is already in env, `gh` picks it up automatically
- PR access is intentional: correlate deploy history with ranking changes
- List merged PRs: `gh pr list --repo ironhack/foundry --state merged --limit 20 --json number,title,mergedAt,author`
- Diff a PR: `gh pr diff <number> --repo ironhack/foundry`
- Do not clone or modify directly

## S3 File Sharing

- Bucket: `ih-ironclaw`
- Region: `eu-west-1`
- Folder: `seo/YYYY-MM-DD/`
- Upload with plain `aws s3 cp` — no `--acl` flag needed (bucket policy handles public access)
- Direct permanent URL: `https://ih-ironclaw.s3.eu-west-1.amazonaws.com/seo/YYYY-MM-DD/report.html`
- NEVER use presigned URLs — they expire and are useless for sharing. Always use the direct URL above.
- AWS credentials already in environment

## Slack

- Channel: #ironclaw-seo
- ID: C0B1MLM0L3X
- No markdown tables in Slack messages. Use bullet lists.

## Style Rules

- No em dashes. Use commas, colons, or parentheses instead.
- Confidence level on every claim: High / Medium / Low
- Numbers with context: "impressions up 12% (4.2k to 4.7k)" not just "up 12%"
