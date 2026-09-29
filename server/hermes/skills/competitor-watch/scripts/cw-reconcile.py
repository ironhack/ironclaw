#!/usr/bin/env python3
"""cw-reconcile.py - turn weekly extractions into competitor state + an append-only change log.

  apply    --date D [--dry-run]   validate extractions/D/<key>.json against prepared text, match against
                                  state/<key>.json, record changes, update state. Prints a digest.
  backfill                        set first_seen of every tracked program from the snapshot history
                                  (earliest capture containing the program name) and rewrite the
                                  baseline change entries with the historical dates.
  status                          one line per competitor: programs, claims, quiet since, capture.

Change types: program_added / program_removed / program_renamed / price_changed / duration_changed /
format_changed / cohort_moved / promo_started / promo_ended / claim_added / claim_changed / claim_removed /
positioning_changed. A program is only removed after 2 consecutive weeks missing on a usable capture.
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cw_common import *  # noqa

MIN_EVIDENCE = 20
RENAME_RATIO = 0.85
CLAIM_RATIO = 0.80


def new_state(key):
    c = COMPETITORS[key]
    return {"key": key, "name": c["name"], "site": c["site"], "markets": c["markets"], "programs": {}, "claims": {},
            "promotions": {}, "positioning": {"text": "", "since": None}, "first_extraction": None, "updated": None,
            "captures": {}}


def evidence_ok(evidence, prepared_norm):
    ev = norm_text(evidence)
    if len(ev) < MIN_EVIDENCE:
        return False
    if ev in prepared_norm:
        return True
    head = ev[:60]
    return len(head) >= MIN_EVIDENCE and head in prepared_norm


def field_change_type(field):
    return {"price": "price_changed", "duration": "duration_changed", "next_start": "cohort_moved"}.get(field, "format_changed")


def make_change(date_str, key, ctype, item, before=None, after=None, evidence="", url="", page="", **extra):
    sev, icon = CHANGE_TYPES.get(ctype, ("low", ""))
    ch = {"id": f"{date_str}:{key}:{ctype}:{norm_name(item)[:40]}", "date": date_str, "competitor": key,
          "competitor_name": COMPETITORS[key]["name"], "type": ctype, "severity": sev, "item": item,
          "before": before, "after": after, "evidence": (evidence or "")[:300], "url": url or "", "page": page or "",
          "recorded_at": now_iso()}
    ch.update(extra)
    return ch


def apply(date_str, dry_run=False):
    ensure_dirs()
    index = load_json(os.path.join(PREPARED_DIR, date_str, "index.json"), {}) or {}
    comp_index = index.get("competitors", {})
    all_changes, digest = [], [f"# Reconcile {date_str}"]
    for key, comp in COMPETITORS.items():
        ext_path = os.path.join(EXTRACT_DIR, date_str, f"{key}.json")
        ext = load_json(ext_path)
        state = load_json(os.path.join(STATE_DIR, f"{key}.json")) or new_state(key)
        quality = (comp_index.get(key) or {}).get("quality", "unknown")
        state["captures"][date_str] = {"quality": quality, "pages_ok": (comp_index.get(key) or {}).get("pages_ok"),
                                       "pages_total": len((comp_index.get(key) or {}).get("pages", {}))}
        if not ext:
            digest.append(f"- {comp['name']}: NO EXTRACTION ({ext_path} missing) - state untouched")
            if not dry_run:
                save_json(os.path.join(STATE_DIR, f"{key}.json"), state)
            continue
        try:
            prepared = open(os.path.join(PREPARED_DIR, date_str, f"{key}.txt")).read()
        except OSError:
            prepared = ""
        pn = norm_text(prepared)
        first_time = state["first_extraction"] is None
        if first_time:
            state["first_extraction"] = date_str
        changes, unverified = [], []
        usable = quality in ("ok", "partial", "unknown")

        # ── programs ──
        seen_keys = set()
        for p in ext.get("programs") or []:
            name = (p.get("name") or "").strip()
            if not name:
                continue
            if not evidence_ok(p.get("evidence", ""), pn):
                unverified.append(f"program '{name}' (evidence not found in prepared text)")
                continue
            nn = norm_name(name)
            match = nn if nn in state["programs"] else None
            if not match:
                cands = [(similar(nn, k), k) for k, v in state["programs"].items() if v.get("status") != "removed"]
                cands = [c for c in cands if c[0] >= RENAME_RATIO and c[1] not in seen_keys]
                if cands:
                    ratio, old_key = max(cands)
                    old = state["programs"].pop(old_key)
                    changes.append(make_change(date_str, key, "program_renamed", name, before=old.get("name"), after=name,
                                               evidence=p.get("evidence"), url=p.get("url"), page=p.get("page")))
                    old["name"] = name
                    state["programs"][nn] = old
                    match = nn
            fields = {k: p.get(k) for k in ("type", "duration", "format", "language", "price", "financing", "markets", "next_start", "url", "page")}
            if match:
                sp = state["programs"][match]
                for f in ("price", "duration", "format", "next_start", "language", "markets"):
                    old_v, new_v = sp.get(f), fields.get(f)
                    if isinstance(old_v, list) or isinstance(new_v, list):
                        old_c, new_c = sorted(old_v or []), sorted(new_v or [])
                    else:
                        old_c, new_c = (old_v or None), (new_v or None)
                    if old_c != new_c and (new_v not in (None, "", [])) and (old_v not in (None, "", [])):
                        changes.append(make_change(date_str, key, field_change_type(f), name, before=old_v, after=new_v,
                                                   evidence=p.get("evidence"), url=p.get("url"), page=p.get("page"), field=f))
                        sp.setdefault("history", []).append({"date": date_str, "field": f, "before": old_v, "after": new_v})
                    if new_v not in (None, "", []):
                        sp[f] = new_v
                for f in ("type", "url", "page"):
                    if fields.get(f):
                        sp[f] = fields[f]
                sp["last_seen"] = date_str
                sp["status"] = "active"
                sp["missing_streak"] = 0
                sp["evidence"] = p.get("evidence")
                seen_keys.add(match)
            else:
                state["programs"][nn] = {**fields, "name": name, "first_seen": date_str, "last_seen": date_str,
                                         "status": "active", "missing_streak": 0, "evidence": p.get("evidence"), "history": []}
                changes.append(make_change(date_str, key, "program_added", name, after=name, evidence=p.get("evidence"),
                                           url=p.get("url"), page=p.get("page"), baseline=first_time))
                seen_keys.add(nn)
        # missing programs
        for nk, sp in state["programs"].items():
            if nk in seen_keys or sp.get("status") == "removed":
                continue
            if not usable:
                continue
            sp["missing_streak"] = int(sp.get("missing_streak", 0)) + 1
            if sp["missing_streak"] >= 2:
                sp["status"] = "removed"
                sp["removed_on"] = date_str
                changes.append(make_change(date_str, key, "program_removed", sp.get("name"), before=sp.get("name"),
                                           evidence=f"absent from captures on two consecutive runs (last seen {sp.get('last_seen')})",
                                           url=sp.get("url"), page=sp.get("page")))
            else:
                sp["status"] = "unconfirmed"

        # ── claims + promotions (same mechanics) ──
        for bucket, add_t, chg_t, rem_t in (("claims", "claim_added", "claim_changed", "claim_removed"),
                                            ("promotions", "promo_started", None, "promo_ended")):
            seen = set()
            for it in ext.get(bucket) or []:
                text = (it.get("text") or "").strip()
                if not text:
                    continue
                if not evidence_ok(it.get("evidence", ""), pn):
                    unverified.append(f"{bucket[:-1]} '{text[:50]}' (evidence not found)")
                    continue
                nk = norm_text(text)[:120]
                store = state[bucket]
                match = nk if nk in store else None
                if not match:
                    cands = [(similar(nk, k), k) for k, v in store.items() if v.get("status") != "removed" and k not in seen]
                    cands = [c for c in cands if c[0] >= CLAIM_RATIO]
                    if cands:
                        _, old_key = max(cands)
                        old = store.pop(old_key)
                        if chg_t and re.sub(r"\D", "", old.get("text", "")) != re.sub(r"\D", "", text):
                            changes.append(make_change(date_str, key, chg_t, text, before=old.get("text"), after=text,
                                                       evidence=it.get("evidence"), page=it.get("page")))
                        old["text"] = text
                        store[nk] = old
                        match = nk
                if match:
                    s = store[match]
                    s.update({"last_seen": date_str, "status": "active", "missing_streak": 0, "evidence": it.get("evidence"),
                              "page": it.get("page"), "kind": it.get("kind", s.get("kind"))})
                    if it.get("ends"):
                        s["ends"] = it["ends"]
                else:
                    store[nk] = {"text": text, "kind": it.get("kind"), "page": it.get("page"), "evidence": it.get("evidence"),
                                 "first_seen": date_str, "last_seen": date_str, "status": "active", "missing_streak": 0,
                                 "ends": it.get("ends")}
                    changes.append(make_change(date_str, key, add_t, text, after=text, evidence=it.get("evidence"),
                                               page=it.get("page"), baseline=first_time))
                seen.add(nk if not match else match)
            for nk, s in state[bucket].items():
                if nk in seen or s.get("status") == "removed" or not usable:
                    continue
                s["missing_streak"] = int(s.get("missing_streak", 0)) + 1
                if s["missing_streak"] >= 2:
                    s["status"] = "removed"
                    s["removed_on"] = date_str
                    changes.append(make_change(date_str, key, rem_t, s.get("text"), before=s.get("text"),
                                               evidence=f"absent on two consecutive runs (last seen {s.get('last_seen')})", page=s.get("page")))
                else:
                    s["status"] = "unconfirmed"

        # ── positioning ──
        pos = (ext.get("positioning") or "").strip()
        if pos:
            old = state["positioning"].get("text") or ""
            if old and similar(norm_text(old), norm_text(pos)) < 0.6:
                changes.append(make_change(date_str, key, "positioning_changed", pos[:80], before=old, after=pos, page="home"))
                state["positioning"] = {"text": pos, "since": date_str}
            elif not old:
                state["positioning"] = {"text": pos, "since": date_str}
        state["notes"] = ext.get("notes")
        state["updated"] = date_str
        state["last_change"] = max([c["date"] for c in changes if not c.get("baseline")] + [state.get("last_change") or ""]) or None

        n_prog = len([v for v in state["programs"].values() if v.get("status") != "removed"])
        real = [c for c in changes if not c.get("baseline")]
        digest.append(f"- {comp['name']}: {len(ext.get('programs') or [])} programs extracted, {n_prog} tracked, "
                      f"{len(real)} change(s){' (baseline week: ' + str(len(changes)) + ' items recorded as first seen)' if first_time else ''}, "
                      f"{len(unverified)} unverified, capture {quality}")
        for c in real:
            digest.append(f"    * {c['type']}: {c['item']}" + (f" ({c['before']} -> {c['after']})" if c.get('before') and c.get('after') and c['before'] != c['after'] else ""))
        for u in unverified[:8]:
            digest.append(f"    ! unverified: {u}")
        all_changes += changes
        if not dry_run:
            save_json(os.path.join(STATE_DIR, f"{key}.json"), state)
    if not dry_run:
        # replace any earlier entries for this date (re-runs) then append
        existing = [c for c in read_jsonl(CHANGES_PATH) if c.get("date") != date_str or c.get("backfilled")]
        with open(CHANGES_PATH, "w") as f:
            for c in existing + all_changes:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
        save_json(os.path.join(WATCH_DIR, "changes", f"{date_str}.json"), all_changes)
    real_total = len([c for c in all_changes if not c.get("baseline")])
    digest.append(f"TOTAL: {real_total} verified change(s) this week" + (" [dry run]" if dry_run else ""))
    print("\n".join(digest))


def backfill():
    dates = snapshot_dates()
    if not dates:
        sys.exit("no snapshots")
    log = read_jsonl(CHANGES_PATH)
    kept = [c for c in log if not (c.get("type") == "program_added" and (c.get("baseline") or c.get("backfilled")))]
    added = []
    for key, comp in COMPETITORS.items():
        sp = os.path.join(STATE_DIR, f"{key}.json")
        state = load_json(sp)
        if not state:
            continue
        # cache normalised texts per date for this competitor
        cache = {}
        def texts(d):
            if d not in cache:
                cache[d] = {lbl: norm_text(t) for lbl, t in snapshot_texts(d, key).items()}
            return cache[d]
        first_capture = next((d for d in dates if texts(d)), None)
        for nk, prog in state["programs"].items():
            name = prog.get("name") or ""
            needle = norm_text(name)
            if len(needle) < 8:
                continue
            found = None
            for d in dates:
                for lbl, t in texts(d).items():
                    if needle in t:
                        found = (d, lbl)
                        break
                if found:
                    break
            if found:
                d, lbl = found
                prog["first_seen"] = d
                prog["first_seen_note"] = "present since first capture" if d == first_capture else "first appearance in captures"
                added.append(make_change(d, key, "program_added", name, after=name,
                                         evidence=f"first appears in snapshot {d}, page {lbl}", url=prog.get("url"), page=lbl,
                                         backfilled=True, baseline=(d == first_capture)))
            else:
                prog["first_seen_note"] = "not found in older captures (name may have changed)"
        save_json(sp, state)
        print(f"{comp['name']}: first_seen set for {len([p for p in state['programs'].values() if p.get('first_seen_note')])} programs "
              f"(first capture {first_capture})")
    with open(CHANGES_PATH, "w") as f:
        for c in sorted(kept + added, key=lambda c: (c["date"], c["competitor"])):
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"change log rewritten: {len(kept)} kept + {len(added)} backfilled program_added entries")


def status():
    for key, comp in COMPETITORS.items():
        st = load_json(os.path.join(STATE_DIR, f"{key}.json"))
        if not st:
            print(f"{comp['name']:28s} no state yet")
            continue
        progs = [p for p in st["programs"].values() if p.get("status") != "removed"]
        unc = [p for p in progs if p.get("status") == "unconfirmed"]
        cap = st.get("captures", {})
        last_cap = sorted(cap)[-1] if cap else "-"
        print(f"{comp['name']:28s} programs {len(progs):2d} ({len(unc)} unconfirmed), claims {len([c for c in st['claims'].values() if c.get('status') != 'removed'])}, "
              f"promos {len([c for c in st['promotions'].values() if c.get('status') != 'removed'])}, last change {st.get('last_change') or 'none'}, "
              f"capture {last_cap} {cap.get(last_cap, {}).get('quality', '')}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("apply"); s.add_argument("--date", default=today()); s.add_argument("--dry-run", action="store_true")
    sub.add_parser("backfill"); sub.add_parser("status")
    a = ap.parse_args()
    if a.cmd == "apply":
        apply(a.date, a.dry_run)
    elif a.cmd == "backfill":
        backfill()
    else:
        status()
