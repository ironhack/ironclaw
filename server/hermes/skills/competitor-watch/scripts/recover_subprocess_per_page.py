#!/usr/bin/env python3
"""Subprocess-per-page Camoufox recovery — worker + driver in one file.

Recovers client-rendered pages that crash the Playwright/Firefox driver
(driver death on `inner_text`, or `goto` hang) where in-process "restart
every N pages" fails. Each page runs in its own OS subprocess with a hard
timeout, so a crash/hang cannot block the batch.

Two modes:
  --one <url> <outfile.json>    fetch ONE page, write result JSON (worker)
  --batch <pages.json> <outfile.json>  driver: read {"label": url, ...},
                                spawn a subprocess per page (2 attempts),
                                merge into outfile, saving incrementally.

Pages JSON is merged into `outfile` under `pages[label]`. A page already in
`outfile` with text_len > 500 is skipped, so re-running resumes.

Edit PAGES inline (or pass a pages.json) and point OUT to the snapshot file.
Set SNAP / OUT to your target snapshot dir when not using --batch.

Usage:
  python3 recover_subprocess_per_page.py --batch /tmp/pages.json fourgeeks.json
"""
import json, os, subprocess, sys
from datetime import datetime, timezone

PY = sys.executable
SELF = os.path.abspath(__file__)

_COOKIE_JS = """() => {
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
}"""


def fetch_one(url, outfile, scroll=True, timeout_ms=25000):
    """Fetch one page via a fresh Camoufox browser, write JSON result."""
    from camoufox.sync_api import Camoufox
    result = {"url": url, "text": "", "text_len": 0, "source": "camoufox-retry"}
    cam = Camoufox(headless=True)
    try:
        pw = cam.__enter__()
    except Exception as e:
        result["error"] = f"browser start: {str(e)[:150]}"
        json.dump(result, open(outfile, "w"), ensure_ascii=False)
        return
    page = None
    try:
        page = pw.new_page()
        page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        try:
            page.evaluate(_COOKIE_JS)
        except Exception:
            pass
        if scroll:
            try:
                for _ in range(12):
                    page.evaluate("window.scrollBy(0, window.innerHeight)")
                    page.wait_for_timeout(400)
                page.evaluate("window.scrollTo(0, 0)")
                page.wait_for_timeout(600)
            except Exception:
                pass
        text = page.inner_text("body")
        result["text"] = text
        result["text_len"] = len(text)
    except Exception as e:
        result["error"] = str(e)[:180]
    finally:
        if page is not None:
            try:
                page.close()
            except Exception:
                pass
        try:
            cam.__exit__(None, None, None)
        except Exception:
            pass
    json.dump(result, open(outfile, "w"), ensure_ascii=False)


def batch(pages_path, outfile, attempts=2, timeout=80, scroll=True):
    pages = json.load(open(pages_path))  # {label: url}
    data = {}
    if os.path.exists(outfile):
        data = json.load(open(outfile))
    existing = data.setdefault("pages", {})
    for label, url in pages.items():
        if existing.get(label, {}).get("text_len", 0) > 500:
            print(f"{label}: already OK ({existing[label]['text_len']} chars)", flush=True)
            continue
        for attempt in range(1, attempts + 1):
            tmp = f"/tmp/cw_{label}_a{attempt}.json"
            print(f"{label}: attempt {attempt} ...", flush=True)
            try:
                subprocess.run([PY, SELF, "--one", url, tmp], timeout=timeout)
                res = json.load(open(tmp)) if os.path.exists(tmp) else {"text_len": 0}
            except subprocess.TimeoutExpired:
                print("  TIMEOUT — hard-killed", flush=True)
                continue
            except Exception as e:
                print(f"  ERROR {str(e)[:60]}", flush=True)
                continue
            if res.get("text_len", 0) > 500:
                existing[label] = res
                print(f"  OK ({res['text_len']} chars)", flush=True)
                break
            print(f"  FAIL: {res.get('error', 'low yield')[:70]}", flush=True)
        if label not in existing:
            existing[label] = {"url": url, "text": "", "text_len": 0,
                               "error": "all attempts failed", "source": "camoufox-retry"}
        data["pages"] = existing
        data["fetched_at"] = datetime.now(timezone.utc).isoformat()
        json.dump(data, open(outfile, "w"), ensure_ascii=False, indent=2)
    ok = sum(1 for p in existing.values() if p.get("text_len", 0) > 0)
    print(f"\nDONE: {ok}/{len(pages)} pages OK -> {outfile}", flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "--one":
        fetch_one(sys.argv[2], sys.argv[3])
    elif sys.argv[1] == "--batch":
        batch(sys.argv[2], sys.argv[3])
    else:
        print(__doc__)
        sys.exit(1)
