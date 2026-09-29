#!/usr/bin/env python3
"""Competitor Watch — Phase 1: Fetch raw page text from competitor websites.

Runs via Hermes cron as no_agent=True script. Uses multiprocessing so each
competitor runs in its own process with a hard timeout — no hung browser
can block the whole run.
"""

import json
import multiprocessing
import os
import sys
import time as _time
from datetime import date, datetime, timezone

# ── Competitor URL definitions ─────────────────────────────────────────────

COMPETITORS = {
    "lewagon": {
        "name": "Le Wagon",
        "main_url": "https://www.lewagon.com",
        "pages": [
            ("home", "https://www.lewagon.com"),
            ("home-fr", "https://www.lewagon.com/fr"),
            ("home-es", "https://www.lewagon.com/es-ES"),
            ("home-pt", "https://www.lewagon.com/lisbon"),
            ("home-nl", "https://www.lewagon.com/amsterdam"),
            ("home-de", "https://www.lewagon.com/de"),
            ("short-ai-automation", "https://info.lewagon.com/ai-data-automation-course"),
            ("short-ai-builder", "https://info.lewagon.com/ai-product-building-course"),
            ("business", "https://business.lewagon.com"),
        ],
    },
    "nuclio": {
        "name": "Nuclio School",
        "main_url": "https://nuclio.school",
        "pages": [
            ("home", "https://nuclio.school"),
            ("masters", "https://nuclio.school/masters"),
        ],
    },
    "neuefische": {
        "name": "Neue Fische",
        "main_url": "https://www.neuefische.de",
        "per_page": True,   # 19 pages; hung in-process on 2026-09-28 (4/19 written before the kill)
        "pages": [
            ("home-de", "https://www.neuefische.de"),
            ("home-en", "https://www.neuefische.de/en"),
            # /bootcamp returns 404 since 2026-09 — /kurse is the live listing page
            ("bootcamps", "https://www.neuefische.de/kurse"),
            ("course-web-dev", "https://www.neuefische.de/bootcamp/web-development"),
            ("course-data-analytics", "https://www.neuefische.de/bootcamp/data-analytics"),
            ("course-cyber-security", "https://www.neuefische.de/bootcamp/cyber-cloud-und-information-security"),
            ("course-data-science", "https://www.neuefische.de/bootcamp/data-science-und-ai"),
            ("course-ai-ml", "https://www.neuefische.de/bootcamp/ai-und-machine-learning-engineering"),
            ("course-cloud", "https://www.neuefische.de/bootcamp/aws-cloud-computing"),
            # ("course-ai-strategy", "https://www.neuefische.de/bootcamp/ai-project-management"),  # dropped 2026-09-28: host blocks the VPS after heavy scraping; keep the footprint small
            # Added 2026-09-14: course pages present in the footer nav but never tracked
            ("course-ai-architect", "https://www.neuefische.de/bootcamp/ai-architect"),
            # ("course-agentic-ml", "https://www.neuefische.de/bootcamp/agentic-machine-learning-engineering"),  # dropped 2026-09-28: host blocks the VPS after heavy scraping; keep the footprint small
            # ("course-data-engineering", "https://www.neuefische.de/bootcamp/data-engineering-bootcamp"),  # dropped 2026-09-28: host blocks the VPS after heavy scraping; keep the footprint small
            # ("course-java", "https://www.neuefische.de/bootcamp/java-development"),  # dropped 2026-09-28: host blocks the VPS after heavy scraping; keep the footprint small
            # ("course-ux-ui", "https://www.neuefische.de/bootcamp/ux-ui-design"),  # dropped 2026-09-28: host blocks the VPS after heavy scraping; keep the footprint small
            # ("course-digital-ki", "https://www.neuefische.de/bootcamp/digital-ki-transformation-management"),  # dropped 2026-09-28: host blocks the VPS after heavy scraping; keep the footprint small
            # ("course-full-stack", "https://www.neuefische.de/bootcamp/full-stack-software-development"),  # dropped 2026-09-28: host blocks the VPS after heavy scraping; keep the footprint small
            # ("course-it-pm", "https://www.neuefische.de/bootcamp/it-project-management"),  # dropped 2026-09-28: host blocks the VPS after heavy scraping; keep the footprint small
            # ("course-product-mgmt", "https://www.neuefische.de/bootcamp/product-management-bootcamp"),  # dropped 2026-09-28: host blocks the VPS after heavy scraping; keep the footprint small
        ],
    },
    "spiced": {
        "name": "Spiced Academy",
        "main_url": "https://www.spiced-academy.com",
        "pages": [
            ("home-de", "https://www.spiced-academy.com"),
            ("home-en", "https://www.spiced-academy.com/en"),
            ("programs", "https://www.spiced-academy.com/en/program"),
            ("course-ai-ml", "https://www.spiced-academy.com/en/program/ai-and-machine-learning-engineering"),
            ("course-ai-engineering", "https://www.spiced-academy.com/en/program/ai-engineering"),
            ("course-web-dev", "https://www.spiced-academy.com/en/program/advanced-web-development"),
            ("course-data-analytics", "https://www.spiced-academy.com/en/program/data-analytics"),
            ("course-cyber-security", "https://www.spiced-academy.com/en/program/cloud-cyber-information-security"),
            ("course-cloud-aws", "https://www.spiced-academy.com/en/program/aws"),
            ("course-ai-strategy", "https://www.spiced-academy.com/en/program/ai-data-strategy-applied-automation"),
        ],
    },
    "fourgeeks": {
        "name": "4Geeks Academy",
        "main_url": "https://4geeks.com",
        "per_page": True,   # client-rendered; the driver crashes and hangs in-process (2026-09-25)
        "pages": [
            ("home", "https://4geeks.com"),
            ("home-es", "https://4geeks.com/es"),
            ("course-full-stack", "https://4geeks.com/en/career-programs/full-stack"),
            ("course-ai-engineering", "https://4geeks.com/en/career-programs/ai-engineering"),
            ("course-cybersecurity", "https://4geeks.com/en/career-programs/cybersecurity"),
            ("course-data-science-ml", "https://4geeks.com/en/career-programs/data-science-ml"),
            ("course-ai-fluency", "https://4geeks.com/en/career-programs/ai-fluency"),
            ("course-applied-ai", "https://4geeks.com/en/career-programs/applied-ai-course"),
        ],
    },
    "masterschool": {
        "name": "Masterschool (MSIT)",
        "main_url": "https://joinmsit.de",
        "pages": [
            ("home", "https://joinmsit.de"),
            ("programs", "https://joinmsit.de/programs"),
        ],
    },
    "liora": {
        "name": "Liora (ex-DataScientest)",
        "main_url": "https://liora.io",
        "pages": [
            ("home-fr", "https://liora.io"),
            ("home-en", "https://liora.io/en"),
            ("formations", "https://liora.io/formations"),
        ],
    },
}


def fetch_competitor_worker(key, comp, snapshot_dir, browser_restart_every=3):
    """Fetch all pages for one competitor. Runs in a subprocess.

    Restarts the browser every N pages to prevent Playwright state corruption
    from accumulating. Returns (key, results_dict).
    """
    from camoufox.sync_api import Camoufox

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

    name = comp["name"]
    pages = comp["pages"]
    comp_results = {
        "competitor": name,
        "main_url": comp["main_url"],
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "pages": {},
    }

    def _create_browser():
        cam = Camoufox(headless=True)
        pw = cam.__enter__()
        return pw, cam

    def _destroy_browser(cam):
        try:
            cam.__exit__(None, None, None)
        except Exception:
            pass

    def _dismiss_cookies(page):
        try:
            result = page.evaluate(_COOKIE_JS)
            if result:
                page.wait_for_timeout(400)
            return result
        except Exception:
            return None

    def _fetch_one(pw_browser, url):
        page = None
        try:
            page = pw_browser.new_page()
            # 22s timeout: 4geeks.com is client-side rendered and needs >10s
            page.goto(url, timeout=22000, wait_until="domcontentloaded")
            page.wait_for_timeout(1200)
            _dismiss_cookies(page)
            # Scroll to trigger lazy-loaded sections; without this, long
            # course pages render only the first screen (observed 2026-09-14:
            # 4geeks cybersecurity captured 1.7K chars thin vs 15.7K scrolled).
            try:
                for _ in range(10):
                    page.evaluate("window.scrollBy(0, window.innerHeight)")
                    page.wait_for_timeout(450)
                page.evaluate("window.scrollTo(0, 0)")
                page.wait_for_timeout(500)
            except Exception:
                pass
            text = page.inner_text("body")
            return {"url": url, "text": text, "text_len": len(text)}
        except Exception as e:
            return {"url": url, "text": "", "text_len": 0, "error": str(e)[:200]}
        finally:
            if page is not None:
                try:
                    page.close()
                except Exception:
                    pass

    if comp.get("per_page"):
        import subprocess
        for i, (label, url) in enumerate(pages, 1):
            print(f"  [{key}] {i}/{len(pages)} {label} (per-page process) ...", flush=True)
            result = None
            for attempt in (1, 2):
                try:
                    r = subprocess.run([sys.executable, os.path.abspath(__file__), "--fetch-one", url],
                                       capture_output=True, text=True, timeout=75)
                    line = [l for l in r.stdout.splitlines() if l.startswith("{")]
                    result = json.loads(line[-1]) if line else {"url": url, "text": "", "text_len": 0,
                                                                 "error": (r.stderr or "no output")[-200:]}
                except subprocess.TimeoutExpired:
                    result = {"url": url, "text": "", "text_len": 0, "error": "per-page process timeout (75s)"}
                except Exception as e:
                    result = {"url": url, "text": "", "text_len": 0, "error": str(e)[:200]}
                if "error" not in result and result.get("text_len", 0) > 0:
                    break
                if attempt == 1:
                    print(f"  [{key}]   retrying {label} ({result.get('error', 'empty')[:60]})", flush=True)
            comp_results["pages"][label] = result
            try:
                with open(os.path.join(snapshot_dir, f"{key}.json"), "w") as _f:
                    json.dump(comp_results, _f, ensure_ascii=False, indent=2)
            except OSError:
                pass
            print(f"  [{key}]   {'FAIL: ' + result['error'][:80] if 'error' in result else 'OK (' + str(result['text_len']) + ' chars)'}", flush=True)
        ok = sum(1 for p in comp_results["pages"].values() if "error" not in p)
        print(f"  [{key}] {name}: {ok}/{len(pages)} pages OK", flush=True)
        return key, comp_results, ok

    pw_browser, cam = _create_browser()
    pages_since_restart = 0

    try:
        for i, (label, url) in enumerate(pages, 1):
            # Restart browser periodically to avoid state corruption
            if pages_since_restart >= browser_restart_every:
                _destroy_browser(cam)
                pw_browser, cam = _create_browser()
                pages_since_restart = 0

            print(f"  [{key}] {i}/{len(pages)} {label} ...", flush=True)
            result = _fetch_one(pw_browser, url)
            pages_since_restart += 1

            comp_results["pages"][label] = result
            # incremental write: a worker killed on timeout keeps the pages it already captured
            try:
                with open(os.path.join(snapshot_dir, f"{key}.json"), "w") as _f:
                    json.dump(comp_results, _f, ensure_ascii=False, indent=2)
            except OSError:
                pass
            if "error" in result:
                print(f"  [{key}]   FAIL: {result['error'][:80]}", flush=True)
            else:
                print(f"  [{key}]   OK ({result['text_len']} chars)", flush=True)
    finally:
        _destroy_browser(cam)

    # Write per-competitor file
    out_path = os.path.join(snapshot_dir, f"{key}.json")
    with open(out_path, "w") as f:
        json.dump(comp_results, f, ensure_ascii=False, indent=2)

    ok = sum(1 for p in comp_results["pages"].values() if "error" not in p)
    print(f"  [{key}] {name}: {ok}/{len(pages)} pages OK", flush=True)
    return key, comp_results, ok


def main():
    today = date.today().isoformat()
    snapshot_dir = os.path.expanduser(
        f"~/ironclaw-data/workspace/competitor-snapshots/{today}"
    )
    os.makedirs(snapshot_dir, exist_ok=True)

    total_pages = sum(len(c["pages"]) for c in COMPETITORS.values())

    print(f"Competitor Watch Fetch — {today}")
    print(f"Output: {snapshot_dir}/")
    print(f"Competitors: {len(COMPETITORS)}, Pages: {total_pages}")
    print(f"Started: {datetime.now(timezone.utc).isoformat()}")
    print()

    results = {}
    total_ok = 0
    competitor_timeout = int(os.environ.get("COMPETITOR_WATCH_COMPETITOR_TIMEOUT", "600"))  # per competitor (raised from 120
    # on 2026-09-14: per-page 22s goto + scroll pass; neuefische now has 19 pages)

    # HARD OVERALL DEADLINE — added 2026-09-21.
    # The join loop below bounds EACH competitor at competitor_timeout, but the
    # joins run sequentially, so N hanging competitors can accumulate N*300s.
    # With cron.script_timeout_seconds = 600 the process is SIGKILLed before it
    # reaches the manifest write, leaving NO manifest.json and NO stub files.
    # Observed 2026-09-21: Phase 1 timed out at 600s -> no manifest.json,
    # fourgeeks.json missing entirely. The deadline guarantees the script
    # always reaches its finalization (stubs + manifest) inside the budget.
    _deadline_budget = float(os.environ.get("COMPETITOR_WATCH_BUDGET", "500"))
    _deadline = _time.monotonic() + _deadline_budget

    # One process per competitor, but at most MAX_CONCURRENT browsers at a time (2026-09-25:
    # 7 parallel Camoufox instances starved each other on the VPS and every page.goto timed out).
    MAX_CONCURRENT = int(os.environ.get("COMPETITOR_WATCH_CONCURRENCY", "3"))
    ctx = multiprocessing.get_context("spawn")
    only = None
    if "--only" in sys.argv:
        only = set(sys.argv[sys.argv.index("--only") + 1].split(","))
    pending = [(k, c) for k, c in COMPETITORS.items() if not only or k in only]
    _targets = [k for k, _ in pending]
    procs = {}
    started_at = {}

    def _start_next():
        while pending and len([q for q in procs if q.is_alive()]) < MAX_CONCURRENT:
            key, comp = pending.pop(0)
            p = ctx.Process(target=fetch_competitor_worker, args=(key, comp, snapshot_dir), name=f"fetch-{key}")
            p.start()
            procs[p] = key
            started_at[p] = _time.monotonic()

    _start_next()
    finished = set()
    while len(finished) < len(_targets):
        _start_next()
        progressed = False
        for p in list(procs):
            if p in finished:
                continue
            key = procs[p]
            if p.is_alive():
                if (_time.monotonic() - started_at[p]) < competitor_timeout and _time.monotonic() < _deadline:
                    continue
            finished.add(p)
            progressed = True
            _remaining = _deadline - _time.monotonic()
            p.join(timeout=max(1.0, min(5.0, _remaining)))
            result_path = os.path.join(snapshot_dir, f"{key}.json")
            if p.is_alive():
                print(f"  [{key}] TIMEOUT after {competitor_timeout}s — killing", flush=True)
                p.kill()
                p.join(timeout=5)
                comp = COMPETITORS[key]
                # Preserve any partial file the worker already wrote — a killed
                # worker may have completed most of its pages. Only write an empty
                # stub when there is genuinely nothing on disk (2026-09-21: an
                # unconditional stub overwrote a worker's near-complete result).
                if os.path.exists(result_path):
                    try:
                        with open(result_path) as f:
                            results[key] = json.load(f)
                        ok = sum(1 for pg in results[key].get("pages", {}).values()
                                 if "error" not in pg)
                        total_ok += ok
                        print(f"  [{key}] kept partial worker output "
                              f"({len(results[key].get('pages', {}))} pages)", flush=True)
                        continue
                    except Exception as e:
                        print(f"  [{key}] partial file unreadable: {e}", flush=True)
                stub = {
                    "competitor": comp["name"],
                    "main_url": comp["main_url"],
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "pages": {},
                    "error": f"Timeout after {competitor_timeout}s",
                }
                results[key] = stub
                with open(result_path, "w") as f:
                    json.dump(stub, f, ensure_ascii=False, indent=2)
            else:
                # Load result from the file the worker wrote
                try:
                    with open(result_path) as f:
                        results[key] = json.load(f)
                    ok = sum(1 for p in results[key].get("pages", {}).values()
                            if "error" not in p)
                    total_ok += ok
                except Exception as e:
                    print(f"  [{key}] Failed to read results: {e}", flush=True)
        if not progressed:
            _time.sleep(1.0)

    # Safety: no worker may outlive the deadline (a hung Playwright driver ignores page timeouts)
    for p in list(procs):
        if p.is_alive():
            print(f"  [{procs[p]}] still alive at finalization — killing", flush=True)
            p.kill()
            p.join(timeout=5)

    # Write manifest
    # pages_ok recomputed from text_len > 0, NOT from error absence: the worker
    # counts a page as OK when it has no `error` field, but a page whose goto
    # succeeded while inner_text returned "" (React SPA rendering nothing) is
    # counted OK and inflates pages_ok (observed 2026-08-17: fourgeeks 5 vs 3).
    def _page_ok(pg):
        return len(pg.get("text") or "") > 0 or (pg.get("text_len") or 0) > 0

    manifest = {
        "date": today,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "competitors": {
            k: {
                "name": c["name"],
                "pages_fetched": len(c["pages"]),
                "pages_ok": sum(
                    1 for pg in results.get(k, {}).get("pages", {}).values()
                    if _page_ok(pg)
                ),
            }
            for k, c in COMPETITORS.items() if k in _targets
        },
    }
    with open(os.path.join(snapshot_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    total_ok = sum(m["pages_ok"] for m in manifest["competitors"].values())
    print(f"\nDone. {total_ok}/{total_pages} pages fetched.")
    print(f"Snapshots saved to {snapshot_dir}/")
    print(json.dumps(manifest, indent=2))

    if total_ok == 0:
        sys.exit(1)


def fetch_one_main(url):
    """Standalone single-page fetch (used by per_page competitors). Prints one JSON line."""
    from camoufox.sync_api import Camoufox
    result = {"url": url, "text": "", "text_len": 0, "error": "not started"}
    cam = Camoufox(headless=True)
    pw = cam.__enter__()
    try:
        page = pw.new_page()
        page.goto(url, timeout=22000, wait_until="domcontentloaded")
        page.wait_for_timeout(1200)
        try:
            for _ in range(10):
                page.evaluate("window.scrollBy(0, window.innerHeight)")
                page.wait_for_timeout(450)
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(500)
        except Exception:
            pass
        text = page.inner_text("body")
        result = {"url": url, "text": text, "text_len": len(text)}
    except Exception as e:
        result = {"url": url, "text": "", "text_len": 0, "error": str(e)[:200]}
    finally:
        try:
            cam.__exit__(None, None, None)
        except Exception:
            pass
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    if "--fetch-one" in sys.argv:
        fetch_one_main(sys.argv[sys.argv.index("--fetch-one") + 1])
        os._exit(0)
    main()
