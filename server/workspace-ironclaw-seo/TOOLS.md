# TOOLS.md - Optimizer Environment

## Google Search Console

Access via Google Search Console API v1 (direct, service account auth).

- Property: https://www.ironhack.com/
- Filter by country dimension to break out ES, PT, FR, NL, DE
- Credentials: service account JSON at GOOGLE_SA_KEY_PATH, impersonating GOOGLE_IMPERSONATE_EMAIL via domain-wide delegation
- API endpoint: https://searchconsole.googleapis.com/webmasters/v3/sites/{siteUrl}/searchAnalytics/query
- Use the `searchAnalytics.query` method; dimensions: `["query","country","page","date"]`

## Website Repo

- Main site: https://github.com/ironhack/foundry
- Worker/edge: https://github.com/ironhack/new-website-worker
- Use GITHUB_TOKEN (already in env) for access — read-only on both repos, including PRs
- PR access is intentional: correlate deploy history with ranking changes
- Clone to /tmp/ironhack-foundry and /tmp/ironhack-worker for analysis, do not modify directly

## S3 File Sharing

- Bucket: `ih-ironclaw`
- Region: `eu-west-1`
- Folder: `optimizer/YYYY-MM-DD/`
- Upload with `--acl public-read` — objects are publicly readable by URL
- Direct permanent URL: `https://ih-ironclaw.s3.eu-west-1.amazonaws.com/optimizer/YYYY-MM-DD/report.html`
- Never use presigned URLs for reports — they expire after 7 days (AWS hard limit)
- AWS credentials already in environment

## Slack

- Channel: #ironclaw-seo
- ID: C0B1MLM0L3X
- No markdown tables in Slack messages. Use bullet lists.

## Style Rules

- No em dashes. Use commas, colons, or parentheses instead.
- Confidence level on every claim: High / Medium / Low
- Numbers with context: "impressions up 12% (4.2k to 4.7k)" not just "up 12%"
