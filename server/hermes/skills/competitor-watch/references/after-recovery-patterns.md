# After-Recovery Patterns

Patterns for updating snapshot metadata after recovering failed pages
via curl fallback or Camoufox retry during Phase 2.

## Manifest.json Update

After recovering a failed page, update `manifest.json` so the
confidence assessment correctly reflects the recovered data.

### Structure

`manifest.json` is at:
```
/home/openclaw/ironclaw-data/workspace/competitor-snapshots/YYYY-MM-DD/manifest.json
```

It looks like:
```json
{
  "date": "2026-06-29",
  "fetched_at": "2026-06-29T09:03:23Z",
  "competitors": {
    "lewagon": {
      "name": "Le Wagon",
      "pages_fetched": 9,
      "pages_ok": 9
    }
  }
}
```

### Python Update Pattern

```python
import json

with open(manifest_path) as f:
    manifest = json.load(f)

# After recovering all failed pages (e.g., lewagon had 8/9 → now 9/9)
manifest['competitors']['lewagon']['pages_ok'] = 9

# Also update the source field in the competitor JSON if you add one:
# data['pages']['home-fr']['source'] = 'curl-fallback'

with open(manifest_path, 'w') as f:
    json.dump(manifest, f, indent=2)
```

### When to Update

- **Curl fallback recovered a page** → increment `pages_ok` for that
  competitor if the yielded text is >500 chars
- **Camoufox retry recovered partial data** → increment `pages_ok` and
  note in the confidence assessment that partial data was used
- **Page is truly unrecoverable** → leave `pages_ok` unchanged. The
  confidence will drop from High to Medium, which is the correct
  outcome

### Sibling Subagent File Collision

If you use `delegate_task` during Phase 2, sibling subagents may write
to the same files (HTML report, news-journal.json, manifest.json) at
the same time, causing data loss. **Phase 2 must run linearly** — do
not delegate any sub-tasks during the report generation pipeline.
