# Camoufox Patterns for Competitor Watch

Proven patterns from the Ironhack competitor watch pipeline. These work on the Hermes host
(Ubuntu, Camoufox installed in Hermes venv at `/home/openclaw/.hermes/hermes-agent/venv/`).

## Cookie Banner Dismissal — FAST (JS-based)

Use `page.evaluate()` with a single JS pass instead of sequential Playwright button lookups.
The old approach (13 × `get_by_role` at 1.5s timeout each) could waste 19.5s per page.
The JS approach completes in <1ms regardless of whether a banner exists.

```python
_COOKIE_JS = """\
() => {
    const labels = ["Accept all", "Accept", "Accepter", "Aceptar",
        "Alle akzeptieren", "Aceitar", "Akkoord", "Tout accepter",
        "Zustimmen", "Alles akzeptieren", "Accepter tout", "Aceptar todo",
        "Aceitar tudo", "Alles toestaan", "Allow all", "Allow cookies",
        "OK", "Got it", "I agree"];
    const norm = s => s.toLowerCase().replace(/\\s+/g, ' ').trim();
    const buttons = document.querySelectorAll('button, [role="button"], a.button, .btn');
    for (const btn of buttons) {
        const text = norm(btn.textContent || '');
        for (const label of labels) {
            if (text === norm(label) || text.startsWith(norm(label))) {
                btn.click();
                return label;
            }
        }
    }
    return null;
}
"""

result = page.evaluate(_COOKIE_JS)
if result:
    page.wait_for_timeout(400)
```

**Proven hit rate:** 100% across all 7 competitors.

## Page Fetch Pattern (for Phase 2 targeted fetches)

```python
from camoufox.sync_api import Camoufox

cam = Camoufox(headless=True)
pw = cam.__enter__()
try:
    page = pw.new_page()
    try:
        page.goto(url, timeout=10000, wait_until="domcontentloaded")
        page.wait_for_timeout(500)
        # dismiss cookies (JS-based, see above)
        text = page.inner_text("body")
    finally:
        try:
            page.close()
        except Exception:
            pass
finally:
    cam.__exit__(None, None, None)
```

- Page timeout: **10s** (15s is too generous; slow pages fail fast and move on)
- Always use explicit `try/finally` for page close to prevent leaks
- Never use `with Camoufox() as pw:` context manager — you need the wrapper for `__exit__`

## Lazy-Render Trap — Scroll Before Reading `inner_text`

**This is the #1 cause of a "successful" Camoufox capture that is actually
a thin partial page.** `page.inner_text("body")` reads only what the DOM
has rendered. Modern marketing pages (4Geeks, spiced, neue fische) lazy-load
everything below the first screen, so a plain fetch returns the hero + nav
and stops — often 10–20% of the real page.

Observed 2026-09-14: 4Geeks `cybersecurity` captured 1,695 chars on a first
Camoufox pass vs **15,692** after scrolling; `data-science-ml` 1,576 → 15,667;
`home-es` 6,565 → 22,095. All three looked like legitimate small pages and
were nearly written into the snapshot as-is.

**Always scroll the full page before reading body text:**

```python
page.goto(url, timeout=22000, wait_until="domcontentloaded")
page.wait_for_timeout(1200)
_dismiss_cookies(page)
for _ in range(10):
    page.evaluate("window.scrollBy(0, window.innerHeight)")
    page.wait_for_timeout(450)
page.evaluate("window.scrollTo(0, 0)")
page.wait_for_timeout(500)
text = page.inner_text("body")
```

**Verification rule:** compare the yield against last week's `text_len` for
the same page key. A drop to under ~40% on a content page means a partial
render — re-fetch with scrolling before integrating. Two distinct passes
(fetch-then-scroll) is fine; the second pass overwrites the first.

**Page timeout is per-site.** 10s was enough historically, but 4geeks.com
(client-side rendered) needs ~20s. Use **22s** and keep the per-competitor
process timeout generous — the fetch script uses 300s since 2026-09-14,
because per-page cost is now `goto + 1.2s + 10 × 0.45s + 0.5s`.

## Camoufox API Pitfall

`Camoufox.__enter__()` returns the Playwright Browser — NOT the Camoufox wrapper.
You MUST capture this return value. The wrapper is needed separately for `__exit__()`.

```python
# WRONG — fails with: 'Camoufox' object has no attribute 'new_page'
cam = Camoufox(headless=True)
cam.__enter__()           # return value DISCARDED
page = cam.new_page()     # AttributeError!

# CORRECT
cam = Camoufox(headless=True)
pw = cam.__enter__()      # pw is the Playwright Browser
page = pw.new_page()      # works
```

## Playwright Internal Crash (State Corruption)

Playwright 1.60.0 can crash internally with a Node.js TypeError that does NOT
raise a Python exception but silently corrupts browser state:

```
TypeError: Cannot read properties of undefined (reading 'url')
    at FFBrowserContext.<anonymous> (coreBundle.js:49624:39)
```

After this crash, subsequent `page.goto()` calls may hang forever instead of
failing. The EPIPE/ECONNREFUSED crash detection does NOT catch this.

**Fix: restart the browser every 3 pages.** This prevents state accumulation:

```python
BROWSER_RESTART_EVERY = 3
pages_since_restart = 0

for url in urls:
    if pages_since_restart >= BROWSER_RESTART_EVERY:
        _destroy_browser(cam)
        pw, cam = _create_browser()
        pages_since_restart = 0
    _fetch_one(pw, url)
    pages_since_restart += 1
```

## Subprocess-Per-Page Recovery (When Restart Isn't Enough)

The "restart every 3 pages" fix AND "fresh browser per page" (in-process) both
fail when the crash is the **DRIVER (Node.js) process dying**, not browser state
accumulation. Observed 2026-09-21 on 4geeks.com AI course pages (ai-engineering,
data-science-ml, ai-fluency, applied-ai):

- `page.goto` + scroll SUCCEED; the crash fires at `page.inner_text("body")`
  with `Connection closed while reading from the driver` (the Node driver threw
  `TypeError: Cannot read properties of undefined (reading 'url')` and died).
  This kills the page mid-read, so the page is lost even though navigation worked.
- After the driver dies, `cam.__exit__(None, None, None)` **HANGS** (it tries to
  close a dead browser), so an in-process retry loop never reaches the next page.
  `Camoufox().__enter__()` can also hang for the same reason.
- Some pages instead hang on `page.goto` (no crash, no yield) until the outer
  command timeout — a third outcome alongside "crash" and "yield".

**Fix — one OS subprocess per page with a hard timeout.** The parent runs each
page in its own subprocess (`subprocess.run(..., timeout=80)`) and hard-kills
hung subprocesses, so neither the crash nor the hang can block the batch. Save
the snapshot file incrementally per page so a partial run isn't lost.

Reusable self-contained script: `scripts/recover_subprocess_per_page.py`
(worker + driver in one file via `--one` / `--batch` modes). Pattern:

```python
import subprocess, json, os
for label, url in PAGES:
    for attempt in (1, 2):
        tmp = f"/tmp/fg_{label}_a{attempt}.json"
        try:
            subprocess.run([PY, SCRIPT, "--one", url, tmp], timeout=80)
            res = json.load(open(tmp)) if os.path.exists(tmp) else {"text_len": 0}
            if res.get("text_len", 0) > 500: break
        except subprocess.TimeoutExpired:
            print("TIMEOUT — hard-killed")
```

**Minimal no-scroll fetch as last resort.** When the SCROLL pass is what
triggers the crash (scroll-triggered lazy-render JS crashes the driver), skip
the scroll entirely: `goto(domcontentloaded)` + `wait_for_timeout(2500)` +
`inner_text`. Recovers partial content (hero + nav, ~1.5K chars vs the full
~20K) — enough to confirm the course still exists and its name/tagline, better
than empty. Mark `source: camoufox-retry` and note "partial" in the recovery log.

**Delta interpretation:** today-empty + last-week-full (`empty_pages_change`) is
a CAPTURE failure this week, NOT a course removal — do not report it as removed.

## Multiprocessing for Hard Timeouts

Threads cannot be killed in Python — a hung `page.goto()` blocks the thread
forever. Use `multiprocessing` so each competitor runs in its own process
with a hard kill timeout:

```python
import multiprocessing

procs = {}
for key, comp in COMPETITORS.items():
    ctx = multiprocessing.get_context("spawn")
    p = ctx.Process(target=fetch_competitor_worker, args=(key, comp, snapshot_dir))
    p.start()
    procs[p] = key

for p in list(procs):
    p.join(timeout=120)  # max 120s per competitor
    if p.is_alive():
        p.kill()          # hard kill — no hung browser survives this
        p.join(timeout=5)
```

With 5-7 concurrent processes, the full 42-page scan completes in **~3 minutes**
instead of the old 16-minute sequential approach.

**Resource limits with multiprocessing:**
- Each Camoufox process: ~560MB RSS
- 5 concurrent: ~2.8GB total (well within 5GB container memory)
- Sequential (old): safe but 5x slower

## Script Timeout Configuration

`no_agent` cron scripts respect `cron.script_timeout_seconds` in config.yaml.
Default is 120s — too low for any meaningful browser workload.

```bash
# Set to 10 minutes (more than enough with multiprocessing)
hermes config set cron.script_timeout_seconds 600
```

Resolution order: module patch → `HERMES_CRON_SCRIPT_TIMEOUT` env var →
`cron.script_timeout_seconds` in config.yaml → default 120s.

## stdout Buffering Gotcha

When running Camoufox scripts via Hermes cron (`no_agent=True`), Python stdout is
block-buffered (not line-buffered) when piped. Use `flush=True` on every `print()`:
```python
print(f"  [{key}] {i}/{len(pages)} {label} ...", flush=True)
```

Also write per-competitor JSON files immediately — the filesystem is the real
progress signal, not stdout.

## URL Discovery on JS-Heavy Sites

Some competitors (4Geeks, Le Wagon subdomains) render course links dynamically
via JavaScript. The homepage inner_text may list course names but not URLs.

**Pattern: extract hrefs with page.evaluate()**:
```python
links = page.evaluate("""() => {
    const anchors = document.querySelectorAll('a[href]');
    return [...new Set([...anchors].map(a => a.href))];
}""")
course_urls = [l for l in links if '/program' in l or '/course' in l or '/bootcamp' in l]
```

Then test each candidate URL for content yield (>200 chars = useful page).
