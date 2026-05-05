# AGENTS.md - Education Workspace

## Session Startup

1. Read `SOUL.md` - this is who you are and how you work
2. Read `TOOLS.md` - repo access, branch conventions, GitHub setup
3. Read `review-queue.json` - where you left off

Then pick up the next items in the queue and proceed.

## Review Queue

`review-queue.json` is your persistent state. Structure:

```json
{
  "course": "bootcamp-name",
  "repo": "github-org/repo-name",
  "branch": "published-ft",
  "queue": [
    {"file": "week1/day1/lesson.md", "status": "pending"},
    {"file": "week1/day1/lab.md",    "status": "done", "pr": 42},
    ...
  ],
  "lastUpdated": "2026-05-05"
}
```

Statuses: `pending`, `in-progress`, `done`, `skipped` (no issues found)

Always update the queue file after each session. This is how future-you
knows where you left off.

## Per-Session Workflow

1. Read queue, find next 3 `pending` items
2. For each item:
   a. Clone/pull the repo if not already local (`/tmp/<repo-name>`)
   b. Read the full file
   c. Review against QA checklist in SOUL.md
   d. If issues found: make improvements, create branch, open PR
   e. If no issues: mark `skipped`
   f. Update queue status
3. Post a short summary to Slack (#ironclaw-education): what you reviewed, PRs opened
4. Stop. Next session tomorrow.

## Memory

- `memory/YYYY-MM-DD.md` - what you reviewed today, PRs opened, anything notable
- `MEMORY.md` - patterns you've noticed across the curriculum

Write to memory at the end of every session.

## Red Lines

- Never push to `published-*` or `cohort-*` directly. PRs only.
- Never mark done without actually opening a PR (or confirming no issues).
- Never touch a file that is currently in an open PR by another reviewer.
- Do not batch multiple lessons into one PR.
