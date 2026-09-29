# Site Restructure Recovery Playbook

When a competitor reorganizes their website, multiple old course URLs
start returning 404s at once. This is NOT per-page fetch failure — it
is a URL restructure, and it needs a different recovery flow.
Validated 2026-08-03: neue fische (5 remapped courses + dead listing
page), spiced academy (1 course moved).

## 1. Detection — the uniform thin-page signature

A 404 template renders the site's chrome (nav, footer, contact info)
plus an error message, so every dead page extracts to roughly the SAME
character count and near-identical text.

- Several course pages returning identical/near-identical thin text
  (~800-900 chars) = site-wide 404 template, NOT independent failures.
  (Observed: 5 neuefische course pages, all exactly 836 chars.)
- Confirm: grep the text for the language's 404 phrase in the first
  500 chars — `nicht gefunden` / `not found` / `no encontrado` /
  `non trouvé` / `404`.
- The 404 template often lists the NEW program names in its nav/footer
  (neuefische's template listed "AWS Cloud Computing mit KI,
  AI Engineering - Data Science und Machine Learning Engineering, ...").
  Read the 404 text itself for the new catalog before fetching anything.
- Do NOT curl-retry the old slugs — they are gone. Go straight to
  discovery (step 2). Treat an otherwise-healthy competitor with N
  uniformly-thin pages as "restructure in progress" in the report's
  Data Quality Flags, not as "N failed fetches".

## 2. Discovery — extract new slugs from the homepage

curl the competitor's homepage HTML and regex out internal hrefs,
filtering for course/program keywords:

```bash
curl -sL --max-time 25 -o home.html \
  -H "User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36" \
  -H "Accept-Language: de-DE,de;q=0.9" "https://www.neuefische.de"
python3 - <<'EOF'
import re
html = open('home.html', encoding='utf-8', errors='replace').read()
urls = sorted(set(re.findall(r'href="(/[^"]+)"', html)))
for u in urls:
    if any(k in u.lower() for k in ['bootcamp', 'kurs', 'weiterbildung',
                                    'course', 'program', 'ai', 'data',
                                    'cloud', 'cyber', 'web']):
        print(u)
EOF
```

(Works for both neuefische and spiced — their homepages are
server-rendered even when individual pages are SPAs.)

## 3. Remap + recover

Build a slug map old-key → new-URL. Keep the ORIGINAL page keys in the
snapshot JSON (so the delta comparison stays key-to-key) and record the
old URL + a note:

```python
nf['pages'][old_key] = {
    "url": new_url,                       # new slug
    "old_url": nf['pages'][old_key]['url'],  # the 404'd URL
    "text": recovered_text,
    "text_len": len(recovered_text),
    "source": "curl-fallback",
    "note": "old URL returned 404; remapped to new slug",
}
```

Then curl each new slug (match Accept-Language to the site language),
extract text, and verify the first ~300 chars show the RIGHT course
before integrating (a wrong redirect would silently inject another
page's content).

Observed remaps (2026-08-03):

| Competitor | Old slug | New slug |
|---|---|---|
| neue fische | /bootcamp/cyber-security | /bootcamp/cyber-cloud-und-information-security |
| neue fische | /bootcamp/data-science | /bootcamp/data-science-und-ai |
| neue fische | /bootcamp/ai-machine-learning | /bootcamp/ai-und-machine-learning-engineering |
| neue fische | /bootcamp/cloud-computing | /bootcamp/aws-cloud-computing |
| neue fische | /bootcamp/ai-data-strategy | /bootcamp/ai-project-management |
| neue fische | /bootcamp (listing) | gone — no replacement |
| spiced | /en/program/cyber-security | /en/program/cloud-cyber-information-security |

## 4. Refresh manifest AND delta AFTER recovery

- Update `manifest.json`: `pages_ok`/`pages_fetched` per competitor,
  `source: "partially-curl-recovered"`.
- Re-run the delta comparison script ONLY after all recovery is done.
  A stale `delta-analysis.json` (e.g., from a crashed earlier Phase 2
  run, or computed before remapping) will mislabel pages — re-running
  after remap correctly shows remapped pages as "changed" (new content
  under the same key) rather than confusing new/removed pairs.
- **PERSIST THE REMAP — update the fetch script (MANDATORY, do not skip).**
  The Phase-1 script at `/home/openclaw/.hermes/scripts/competitor-watch-fetch.py`
  hardcodes page URLs in its `COMPETITORS` dict. If you remap the snapshot
  JSONs but leave the OLD slugs in the script, next week's Phase 1 re-fetches
  the dead URLs and the entire 404-template recovery repeats verbatim.
  **Observed 2026-08-17:** the 5 neue fische courses + spiced cyber-security
  reverted to thin 404 templates again because the 2026-08-10 recovery
  remapped the snapshot files but never patched the fetch script. After any
  remap, patch the script's `COMPETITORS` URLs to the new slugs too (use the
  `patch` tool with a V4A multi-hunk patch — one call can rewrite all 5-6
  URLs at once).

## 5. Report it as a strategic signal

A URL restructure across course pages is a business signal, not just a
data-recovery note: it usually accompanies rebranded programs, new
certifications, and repositioning (neuefische's 404 template + new
homepage revealed "Data Science & AI + AI Modeling with IHK-Zertifikat"
and an Agentic ML Engineering lineup). Put it in the Executive Summary
and Delta sections, and list the dead slugs under Data Quality Flags.
