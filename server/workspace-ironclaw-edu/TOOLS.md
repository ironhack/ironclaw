# TOOLS.md - Education Environment

## GitHub Access

- Bot account: `ironclaw-ih`
- Auth: GITHUB_TOKEN env var (already set), HTTPS clone
- Clone format: `git clone https://ironclaw-ih:$GITHUB_TOKEN@github.com/<org>/<repo>.git`
- Local clone path: `/tmp/<repo-name>` (ephemeral per session is fine)

## Branch Conventions

- `published-ft` / `published-pt` - production baseline (FT = full-time, PT = part-time)
  Same content, different schedules. Branch PRs from these.
- `cohort-*` - live student-facing branches. NEVER touch.
- PR branches: `ironclaw-qa/<lesson-slug>-<date>`

## Course Index

`index.yaml` in each repo is the source of truth for course structure.
Read it first to understand the actual week/day/content mapping.
The filesystem layout alone can be misleading.

## Course Repos

TODO: add list of active bootcamp repos and their GitHub URLs.
Start with one course (to be specified by Rudy).

## S3

- Bucket: `ih-ironclaw`
- Folder: `education/YYYY-MM-DD/`
- Use presigned URLs for any files shared externally
- AWS credentials in environment

## Slack

- Channel: #ironclaw-education
- ID: TODO - fill in after Slack app is created
- Post session summaries here. Keep them short: what you reviewed, what you changed.

## Style Rules

- No em dashes. Use commas, colons, or parentheses instead.
- In PR bodies: be factual. "Changed X to Y because Z." Not "improved" or "enhanced."
