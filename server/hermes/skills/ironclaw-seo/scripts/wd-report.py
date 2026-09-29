#!/usr/bin/env python3
"""
wd-report.py -- Generate HTML report from WD redirect monitor snapshot.

Usage: python3 wd-report.py <snapshot.json> [prev_snapshot.json]
  _baseline.json is auto-loaded from the same directory as snapshot.json.
Output: HTML to stdout
"""

import sys, json, os
from datetime import datetime
from collections import defaultdict

ZERO = "<span class='zero'>-</span>"

def fmt_num(n):
    return f"{int(n):,}" if n else "0"

def fmt_pct(n):
    return f"{n*100:.1f}%" if n else "0%"

def fmt_pos(n):
    return f"{n:.1f}" if n else "-"

def delta_badge(curr, prev, invert=False):
    if prev is None or prev == 0:
        return ""
    diff = curr - prev
    pct = diff / prev * 100
    if abs(pct) < 2:
        return '<span class="badge neutral">~</span>'
    up = diff > 0
    if invert:
        up = not up
    cls = "up" if up else "down"
    sign = "+" if diff > 0 else ""
    return f'<span class="badge {cls}">{sign}{pct:.0f}%</span>'

def vs_baseline_cell(curr_imp, base_avg):
    if not base_avg:
        return '<span class="zero">-</span>'
    pct = (curr_imp - base_avg) / base_avg * 100
    sign = "+" if pct >= 0 else ""
    if abs(pct) < 5:
        cls = "neutral"
    elif pct > 0:
        cls = "up"
    else:
        cls = "down"
    return f'<span class="badge {cls}">{sign}{pct:.0f}%</span><br><small style="color:#6e6e73">{fmt_num(base_avg)}/wk avg</small>'

def transfer_target_cell(curr_imp, dest_base_avg, src_base_sum):
    """Progress toward expected destination traffic (dest_baseline + source_baseline)."""
    if not src_base_sum:
        return '<span class="zero">-</span>'
    target = dest_base_avg + src_base_sum
    if target <= 0:
        return '<span class="zero">-</span>'
    pct = curr_imp / target * 100
    bar_pct = min(120, pct)  # cap bar at 120% visually
    if pct >= 100:
        bar_cls = "pb-green"
    elif pct >= 60:
        bar_cls = "pb-orange"
    else:
        bar_cls = "pb-red"
    sign = "+" if pct > 100 else ""
    label = f"{sign}{pct:.0f}%"
    target_str = fmt_num(round(target))
    src_str = fmt_num(round(src_base_sum))
    return (
        f'<div class="pb-wrap"><div class="pb-bar {bar_cls}" style="width:{bar_pct:.0f}%"></div></div>'
        f'<div class="pb-label">{label} <span class="pb-sub">of {target_str}/wk</span></div>'
        f'<div class="pb-sub2">+{src_str}/wk expected from src</div>'
    )

snapshot_path = sys.argv[1]
snapshot_dir  = os.path.dirname(os.path.abspath(snapshot_path))

with open(snapshot_path) as f:
    d = json.load(f)

prev = None
if len(sys.argv) > 2:
    try:
        with open(sys.argv[2]) as f:
            prev = json.load(f)
    except:
        pass

baseline = None
baseline_path = os.path.join(snapshot_dir, "_baseline.json")
if os.path.exists(baseline_path):
    try:
        with open(baseline_path) as f:
            baseline = json.load(f)
    except:
        pass

period    = d.get("period", {})
run_date  = datetime.now().strftime("%B %d, %Y")
period_str = f"{period.get('start','')} to {period.get('end','')}"
is_baseline_run = not prev

checks      = d.get("redirect_checks", [])
ok_count    = sum(1 for c in checks if c.get("ok"))
broken      = [c for c in checks if not c.get("ok")]
sources     = d.get("gsc_sources", [])
destinations = d.get("gsc_destinations", [])

total_src_imp    = sum(s.get("impressions", 0) for s in sources)
total_dst_imp    = sum(s.get("impressions", 0) for s in destinations)
sources_with_traffic = [s for s in sources if s.get("impressions", 0) > 0]
sources_clean    = len(sources) - len(sources_with_traffic)

prev_src_imp = prev_dst_imp = None
if prev:
    prev_src_imp = sum(s.get("impressions", 0) for s in prev.get("gsc_sources", []))
    prev_dst_imp = sum(s.get("impressions", 0) for s in prev.get("gsc_destinations", []))

base_dst_map = {}
base_src_map = {}
dest_src_baseline = defaultdict(float)
base_period_str = ""
total_base_dst_avg = total_base_src_avg = None

if baseline:
    bp = baseline.get("baseline_period", {})
    base_period_str = f"{bp.get('start','')} to {bp.get('end','')} ({bp.get('weeks','')} wks)"
    for x in baseline.get("gsc_destinations", []):
        base_dst_map[x["url"]] = x
    for x in baseline.get("gsc_sources", []):
        base_src_map[x["url"]] = x
        dst = x.get("destination")
        if dst:
            dest_src_baseline[dst] += x.get("weekly_avg_impressions", 0)
    total_base_dst_avg = sum(x.get("weekly_avg_impressions", 0) for x in baseline.get("gsc_destinations", []))
    total_base_src_avg = sum(x.get("weekly_avg_impressions", 0) for x in baseline.get("gsc_sources", []))

# Overall transfer target progress
total_transfer_target = 0.0
total_transfer_curr   = 0.0
for dest in destinations:
    u  = dest["url"]
    sb = dest_src_baseline.get(u, 0)
    if sb > 0:
        db     = base_dst_map.get(u, {}).get("weekly_avg_impressions", 0)
        target = db + sb
        total_transfer_target += target
        total_transfer_curr   += dest.get("impressions", 0)
overall_transfer_pct = (total_transfer_curr / total_transfer_target * 100) if total_transfer_target > 0 else None

prev_dst_map = {}
prev_src_map = {}
if prev:
    for x in prev.get("gsc_destinations", []):
        prev_dst_map[x["url"]] = x
    for x in prev.get("gsc_sources", []):
        prev_src_map[x["url"]] = x

redirect_map = {c["source_url"]: c for c in checks}
destinations_sorted = sorted(destinations, key=lambda x: x.get("impressions", 0), reverse=True)
sources_sorted      = sorted(sources,      key=lambda x: x.get("impressions", 0), reverse=True)

# --- cards ---
src_card_sub = f"{sources_clean} of {len(sources)} sources at zero"
if prev_src_imp is not None:
    src_card_sub += " " + delta_badge(total_src_imp, prev_src_imp, invert=True)
dst_card_sub = f"{len(destinations)} pages"
if prev_dst_imp is not None:
    dst_card_sub += " " + delta_badge(total_dst_imp, prev_dst_imp)
if total_base_dst_avg:
    dst_card_sub += f" &nbsp;{delta_badge(total_dst_imp, total_base_dst_avg)} vs baseline"

if overall_transfer_pct is not None:
    if overall_transfer_pct >= 100:
        transfer_card_cls = "green"
    elif overall_transfer_pct >= 60:
        transfer_card_cls = "orange"
    else:
        transfer_card_cls = "red"
    transfer_card_val = f"{overall_transfer_pct:.0f}%"
    transfer_card_sub = f"of combined baseline target ({fmt_num(round(total_transfer_target))}/wk)"
else:
    transfer_card_cls = ""
    transfer_card_val = "N/A"
    transfer_card_sub = "no baseline data"

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>WD Redirect Monitor - {run_date}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f5f5f7; color: #1d1d1f; font-size: 14px; }}
  .wrap {{ max-width: 1060px; margin: 0 auto; padding: 32px 20px; }}
  h1 {{ font-size: 24px; font-weight: 700; margin-bottom: 4px; }}
  .subtitle {{ color: #6e6e73; margin-bottom: 6px; font-size: 13px; }}
  .baseline-note {{ color: #6e6e73; margin-bottom: 28px; font-size: 12px; }}
  .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 32px; }}
  .card {{ background: white; border-radius: 12px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }}
  .card .label {{ font-size: 11px; text-transform: uppercase; letter-spacing: .5px; color: #6e6e73; margin-bottom: 8px; }}
  .card .value {{ font-size: 28px; font-weight: 700; line-height: 1; }}
  .card .sub {{ font-size: 12px; color: #6e6e73; margin-top: 6px; }}
  .card.green .value {{ color: #34c759; }}
  .card.red .value {{ color: #ff3b30; }}
  .card.orange .value {{ color: #ff9500; }}
  section {{ background: white; border-radius: 12px; padding: 24px; box-shadow: 0 1px 3px rgba(0,0,0,.08); margin-bottom: 20px; }}
  section h2 {{ font-size: 15px; font-weight: 600; margin-bottom: 4px; padding-bottom: 12px; border-bottom: 1px solid #f0f0f0; }}
  section .h2-sub {{ font-size: 11px; color: #6e6e73; margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid #f0f0f0; margin-top: -8px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ text-align: left; font-weight: 600; color: #6e6e73; font-size: 11px; text-transform: uppercase; letter-spacing: .5px; padding: 0 10px 10px 0; white-space: nowrap; }}
  td {{ padding: 8px 10px 8px 0; border-top: 1px solid #f5f5f7; vertical-align: middle; }}
  .url {{ font-family: monospace; font-size: 12px; color: #1d1d1f; word-break: break-all; }}
  .badge {{ display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: 600; margin-left: 2px; }}
  .badge.up {{ background: #d1f5dc; color: #1a7f37; }}
  .badge.down {{ background: #fde8e8; color: #cf222e; }}
  .badge.neutral {{ background: #f0f0f0; color: #6e6e73; }}
  .ok {{ color: #34c759; font-weight: 600; }}
  .fail {{ color: #ff3b30; font-weight: 600; }}
  .tag {{ display: inline-block; padding: 2px 7px; border-radius: 4px; font-size: 11px; font-weight: 500; }}
  .tag.remote {{ background: #e8f0fe; color: #1a56db; }}
  .tag.location {{ background: #fef3c7; color: #92400e; }}
  .queries span {{ display: inline-block; background: #f5f5f7; border-radius: 4px; padding: 1px 6px; margin: 2px 2px 0 0; font-size: 12px; color: #6e6e73; }}
  .zero {{ color: #c7c7cc; }}
  .alert {{ background: #fff8e6; border-left: 3px solid #ff9500; padding: 12px 16px; border-radius: 0 8px 8px 0; font-size: 13px; margin-bottom: 12px; }}
  .alert strong {{ display: block; margin-bottom: 2px; }}
  /* progress bar for transfer target */
  .pb-wrap {{ width: 90px; height: 5px; background: #f0f0f0; border-radius: 3px; margin-bottom: 4px; overflow: hidden; }}
  .pb-bar {{ height: 5px; border-radius: 3px; }}
  .pb-green {{ background: #34c759; }}
  .pb-orange {{ background: #ff9500; }}
  .pb-red {{ background: #ff3b30; }}
  .pb-label {{ font-size: 12px; font-weight: 600; color: #1d1d1f; }}
  .pb-sub {{ font-size: 11px; font-weight: 400; color: #6e6e73; }}
  .pb-sub2 {{ font-size: 10px; color: #c7c7cc; margin-top: 1px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>WD Redirect Monitor</h1>
  <div class="subtitle">This week: {period_str} &nbsp;&middot;&nbsp; Generated {run_date}{"&nbsp;&middot;&nbsp; First run after redirect launch" if is_baseline_run else ""}</div>
  {"<div class='baseline-note'>Baseline: " + base_period_str + "</div>" if base_period_str else ""}

  <div class="cards">
    <div class="card {'green' if ok_count == len(checks) else 'red'}">
      <div class="label">Redirect Health</div>
      <div class="value">{ok_count}/{len(checks)}</div>
      <div class="sub">{"All redirects OK" if ok_count == len(checks) else str(len(broken)) + " broken"}</div>
    </div>
    <div class="card">
      <div class="label">Source Impressions</div>
      <div class="value">{fmt_num(total_src_imp)}</div>
      <div class="sub">{src_card_sub}</div>
    </div>
    <div class="card">
      <div class="label">Destination Impressions</div>
      <div class="value">{fmt_num(total_dst_imp)}</div>
      <div class="sub">{dst_card_sub}</div>
    </div>
    <div class="card {transfer_card_cls}">
      <div class="label">Transfer Target</div>
      <div class="value">{transfer_card_val}</div>
      <div class="sub">{transfer_card_sub}</div>
    </div>
    <div class="card {'orange' if sources_with_traffic else 'green'}">
      <div class="label">Sources Still Visible</div>
      <div class="value">{len(sources_with_traffic)}</div>
      <div class="sub">of {len(sources)} source URLs</div>
    </div>
  </div>
"""

if broken:
    html += '<section><h2>Broken Redirects</h2>'
    for b in broken:
        html += f'<div class="alert"><strong>{b["source_url"]}</strong>{b.get("issue","")}</div>'
    html += '</section>'

has_baseline_dst = bool(base_dst_map)
has_transfer_col = bool(dest_src_baseline)
html += '<section>'
html += '<h2>Destination Pages</h2>'
if has_baseline_dst:
    html += f'<div class="h2-sub">Transfer Target = destination traffic as % of (dest baseline + source baseline). Baseline: {base_period_str}</div>'
html += '<table><thead><tr>'
html += '<th>URL</th><th>Country</th><th>Impressions</th><th>Clicks</th><th>CTR</th><th>Avg Pos</th>'
if has_baseline_dst:
    html += '<th>vs Dest Baseline</th>'
if has_transfer_col:
    html += '<th>Transfer Target</th>'
if prev_dst_map:
    html += '<th>vs Last Week</th>'
html += '<th>Top Query</th></tr></thead><tbody>'

for dest in destinations_sorted:
    u      = dest["url"]
    imp    = dest.get("impressions", 0)
    clicks = dest.get("clicks", 0)
    ctr    = dest.get("ctr", 0)
    pos    = dest.get("position", 0)
    top_q  = dest.get("top_queries", [{}])[0].get("query", "-") if dest.get("top_queries") else "-"
    imp_str = fmt_num(imp) if imp else '<span class="zero">0</span>'
    clk_str = fmt_num(clicks) if clicks else '<span class="zero">0</span>'
    html += f'<tr><td class="url"><a href="{u}" target="_blank">{u.replace("https://www.ironhack.com","")}</a></td>'
    html += f'<td>{dest.get("country","")} <small style="color:#6e6e73">({dest.get("language","")})</small></td>'
    html += f'<td>{imp_str}</td><td>{clk_str}</td><td>{fmt_pct(ctr)}</td><td>{fmt_pos(pos)}</td>'
    if has_baseline_dst:
        base_avg = base_dst_map.get(u, {}).get("weekly_avg_impressions", 0)
        html += f'<td>{vs_baseline_cell(imp, base_avg)}</td>'
    if has_transfer_col:
        sb       = dest_src_baseline.get(u, 0)
        base_avg = base_dst_map.get(u, {}).get("weekly_avg_impressions", 0)
        html += f'<td>{transfer_target_cell(imp, base_avg, sb)}</td>'
    if prev_dst_map:
        p_imp = prev_dst_map.get(u, {}).get("impressions", 0)
        html += f'<td>{delta_badge(imp, p_imp) or ZERO}</td>'
    html += f'<td class="queries"><span>{top_q}</span></td></tr>'

html += '</tbody></table></section>'

has_baseline_src = bool(base_src_map)
html += '<section>'
html += '<h2>Source Pages</h2>'
html += '<div class="h2-sub">Should trend to zero impressions as Google clears the redirected URLs.</div>'
html += '<table><thead><tr>'
html += '<th>URL</th><th>Type</th><th>Impressions</th><th>Clicks</th><th>Avg Pos</th>'
if has_baseline_src:
    html += '<th>vs Baseline avg</th>'
if prev_src_map:
    html += '<th>vs Last Week</th>'
html += '<th>Top Query</th><th>301</th></tr></thead><tbody>'

for src in sources_sorted:
    u      = src["url"]
    imp    = src.get("impressions", 0)
    clicks = src.get("clicks", 0)
    pos    = src.get("position", 0)
    top_q  = src.get("top_queries", [{}])[0].get("query", "-") if src.get("top_queries") else "-"
    typ    = src.get("type", "")
    tag_cls = "remote" if typ == "Remote" else "location"
    redir_ok = redirect_map.get(u, {}).get("ok", False)
    redir_cell = '<span class="ok">301</span>' if redir_ok else '<span class="fail">BROKEN</span>'
    imp_str = fmt_num(imp) if imp else '<span class="zero">0</span>'
    clk_str = fmt_num(clicks) if clicks else '<span class="zero">0</span>'
    html += f'<tr><td class="url"><a href="{u}" target="_blank">{u.replace("https://www.ironhack.com","")}</a></td>'
    html += f'<td><span class="tag {tag_cls}">{typ}</span></td>'
    html += f'<td>{imp_str}</td><td>{clk_str}</td><td>{fmt_pos(pos) if pos else ZERO}</td>'
    if has_baseline_src:
        base_avg = base_src_map.get(u, {}).get("weekly_avg_impressions", 0)
        html += f'<td>{vs_baseline_cell(imp, base_avg) if base_avg else ZERO}</td>'
    if prev_src_map:
        p_imp = prev_src_map.get(u, {}).get("impressions", 0)
        html += f'<td>{delta_badge(imp, p_imp, invert=True) or ZERO}</td>'
    html += f'<td class="queries"><span>{top_q if imp else "-"}</span></td><td>{redir_cell}</td></tr>'

html += '</tbody></table></section></div></body></html>'

print(html)
