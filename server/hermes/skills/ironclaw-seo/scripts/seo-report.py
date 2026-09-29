#!/usr/bin/env python3
"""
seo-report.py -- Generate HTML SEO weekly snapshot report.

Usage: python3 seo-report.py <recent.json> <previous.json> <trend28.json> <pages.json>
Output: HTML to stdout
"""

import sys, json, os
from datetime import datetime
from collections import defaultdict

COUNTRY_NAMES  = {'esp': 'Spain', 'fra': 'France', 'deu': 'Germany', 'prt': 'Portugal', 'nld': 'Netherlands'}
COUNTRY_FLAGS  = {'esp': '🇪🇸', 'fra': '🇫🇷', 'deu': '🇩🇪', 'prt': '🇵🇹', 'nld': '🇳🇱'}
COUNTRY_CODES  = {'esp': 'ES', 'fra': 'FR', 'deu': 'DE', 'prt': 'PT', 'nld': 'NL'}
COUNTRIES      = ['esp', 'fra', 'deu', 'prt', 'nld']

def load(path):
    with open(path) as f: return json.load(f)

def is_brand(q):
    q = q.lower()
    return 'ironhack' in q or 'iron hack' in q

def fmt(n):
    return f"{int(n):,}" if n >= 1000 else str(int(n))

def fmt_pct(v):
    if v == float('inf'): return '+∞%'
    s = '+' if v > 0 else ''
    return f"{s}{v:.1f}%"

def pct(new, old):
    if old == 0: return float('inf') if new > 0 else 0.0
    return (new - old) / old * 100

def badge(val, invert=False):
    if val == float('inf') or abs(val) < 2:
        return f'<span class="badge neutral">~</span>'
    up = val > 0
    if invert: up = not up
    cls = 'up' if up else 'down'
    return f'<span class="badge {cls}">{fmt_pct(val)}</span>'

def aggregate(rows):
    by_c = defaultdict(lambda: {'clicks': 0, 'impressions': 0, 'pos_sum': 0.0, 'pos_w': 0})
    for r in rows:
        c = r['keys'][1]
        by_c[c]['clicks']     += r['clicks']
        by_c[c]['impressions'] += r['impressions']
        by_c[c]['pos_sum']     += r['position'] * r['impressions']
        by_c[c]['pos_w']       += r['impressions']
    out = {}
    for c, d in by_c.items():
        imp = d['impressions']
        out[c] = {
            'clicks': d['clicks'], 'impressions': imp,
            'ctr': d['clicks'] / imp * 100 if imp else 0,
            'avg_position': d['pos_sum'] / d['pos_w'] if d['pos_w'] else 0,
        }
    return out

def brand_split(rows):
    out = defaultdict(lambda: {'brand': {'clicks': 0, 'impressions': 0}, 'nonbrand': {'clicks': 0, 'impressions': 0}})
    for r in rows:
        c = r['keys'][1]
        k = 'brand' if is_brand(r['keys'][0]) else 'nonbrand'
        out[c][k]['clicks']     += r['clicks']
        out[c][k]['impressions'] += r['impressions']
    return out

def weekly_buckets(trend_rows):
    all_dates = sorted(set(r['keys'][2] for r in trend_rows), reverse=True)
    buckets = []
    for i in range(0, min(28, len(all_dates)), 7):
        week_set = set(all_dates[i:i+7])
        if not week_set: break
        rows = [r for r in trend_rows if r['keys'][2] in week_set]
        dl = sorted(week_set)
        buckets.append({'start': dl[0], 'end': dl[-1], 'rows': rows, 'agg': aggregate(rows)})
    return buckets

def top_movers(recent_rows, prev_rows, n=5):
    def by_q(rows):
        q = defaultdict(lambda: {'clicks': 0, 'impressions': 0})
        for r in rows:
            k = (r['keys'][0], r['keys'][1])
            q[k]['clicks']     += r['clicks']
            q[k]['impressions'] += r['impressions']
        return q
    rq, pq = by_q(recent_rows), by_q(prev_rows)
    movers = defaultdict(list)
    for (query, country) in set(rq) | set(pq):
        rc = rq[(query, country)]['clicks']
        pc = pq[(query, country)]['clicks']
        movers[country].append({
            'query': query, 'delta': rc - pc,
            'recent': rc, 'prev': pc,
            'imp': rq[(query, country)]['impressions'],
            'brand': is_brand(query),
        })
    return {c: {'up': sorted(ms, key=lambda x: x['delta'], reverse=True)[:n],
                'down': sorted(ms, key=lambda x: x['delta'])[:n]}
            for c, ms in movers.items()}

def top_pages(pages_rows, n=6):
    by_c = defaultdict(list)
    for r in pages_rows:
        page, country = r['keys'][0], r['keys'][1]
        by_c[country].append({'page': page, 'impressions': r['impressions'],
                               'clicks': r['clicks'], 'ctr': r['ctr'] * 100})
    return {c: sorted(v, key=lambda x: x['impressions'], reverse=True)[:n] for c, v in by_c.items()}

# ── load data ──────────────────────────────────────────────────────────────────

recent_d  = load(sys.argv[1])
prev_d    = load(sys.argv[2])
trend_d   = load(sys.argv[3])
pages_d   = load(sys.argv[4])

recent_rows = recent_d['rows']
prev_rows   = prev_d['rows']

recent_agg = aggregate(recent_rows)
prev_agg   = aggregate(prev_rows)
recent_b   = brand_split(recent_rows)
prev_b     = brand_split(prev_rows)
buckets    = weekly_buckets(trend_d['rows'])
movers     = top_movers(recent_rows, prev_rows)
pages      = top_pages(pages_d['rows'])

run_date    = datetime.now().strftime('%B %d, %Y')
period_str  = f"{recent_d.get('start_date','?')} to {recent_d.get('end_date','?')}"
prev_str    = f"{prev_d.get('start_date','?')} to {prev_d.get('end_date','?')}"

# ── summary numbers ────────────────────────────────────────────────────────────

total_r = {'clicks': sum(recent_agg.get(c, {}).get('clicks', 0) for c in COUNTRIES),
           'impressions': sum(recent_agg.get(c, {}).get('impressions', 0) for c in COUNTRIES)}
total_p = {'clicks': sum(prev_agg.get(c, {}).get('clicks', 0) for c in COUNTRIES),
           'impressions': sum(prev_agg.get(c, {}).get('impressions', 0) for c in COUNTRIES)}
total_ctr = total_r['clicks'] / total_r['impressions'] * 100 if total_r['impressions'] else 0

clicks_delta = pct(total_r['clicks'], total_p['clicks'])
imp_delta    = pct(total_r['impressions'], total_p['impressions'])

best_c   = max(COUNTRIES, key=lambda c: pct(recent_agg.get(c,{}).get('clicks',0), prev_agg.get(c,{}).get('clicks',1)))
worst_traj_c = min(COUNTRIES, key=lambda c: (
    pct(buckets[0]['agg'].get(c,{}).get('clicks',0), buckets[-1]['agg'].get(c,{}).get('clicks',1))
    if buckets else 0))

# ── 4-week trend bars ──────────────────────────────────────────────────────────

max_clicks = max(
    (b['agg'].get(c, {}).get('clicks', 0) for b in buckets for c in COUNTRIES),
    default=1
) or 1

def trend_bar_html(c):
    rows_html = ''
    week_clicks = []
    for i, b in enumerate(buckets):
        cl  = b['agg'].get(c, {}).get('clicks', 0)
        imp = b['agg'].get(c, {}).get('impressions', 0)
        week_clicks.append(cl)
        bar_w = round(cl / max_clicks * 100)
        label = 'W1 (current)' if i == 0 else f'W{i+1}'
        cls = 'bar-w1' if i == 0 else ('bar-w2' if i == 1 else 'bar-old')
        rows_html += f'''
        <div class="trend-row">
          <div class="trend-label">{label}</div>
          <div class="trend-bar-wrap">
            <div class="trend-bar {cls}" style="width:{bar_w}%"></div>
          </div>
          <div class="trend-val">{fmt(cl)} <span class="trend-sub">{fmt(imp)} imp</span></div>
        </div>'''
    traj = pct(week_clicks[0], week_clicks[-1]) if len(week_clicks) >= 2 else 0
    traj_cls = 'up' if traj > 2 else ('down' if traj < -2 else 'neutral')
    traj_html = f'<span class="badge {traj_cls}" style="font-size:12px">{fmt_pct(traj)} over {len(week_clicks)}w</span>'
    return rows_html, traj_html

# ── per-market summary rows ────────────────────────────────────────────────────

def market_row(c):
    r  = recent_agg.get(c, {'clicks': 0, 'impressions': 0, 'ctr': 0, 'avg_position': 0})
    p  = prev_agg.get(c,   {'clicks': 0, 'impressions': 0, 'ctr': 0, 'avg_position': 0})
    rb = recent_b.get(c,   {'brand': {'clicks': 0}, 'nonbrand': {'clicks': 0}})
    pb = prev_b.get(c,     {'brand': {'clicks': 0}, 'nonbrand': {'clicks': 0}})
    cd = pct(r['clicks'],  p['clicks'])
    id_ = pct(r['impressions'], p['impressions'])
    pd = r['avg_position'] - p['avg_position']
    bd = pct(rb['brand']['clicks'],    pb['brand']['clicks'])
    nd = pct(rb['nonbrand']['clicks'], pb['nonbrand']['clicks'])
    pos_flag = ' <span class="pos-flag">⚠ pos shift</span>' if abs(pd) > 2 else ''
    return f'''
    <tr>
      <td><strong>{COUNTRY_CODES[c]}</strong> <span class="flag">{COUNTRY_FLAGS[c]}</span> {COUNTRY_NAMES[c]}</td>
      <td class="num">{fmt(r['clicks'])} {badge(cd)}</td>
      <td class="num small">
        Brand: {fmt(rb['brand']['clicks'])} {badge(bd)}<br>
        Non-brand: {fmt(rb['nonbrand']['clicks'])} {badge(nd)}
      </td>
      <td class="num">{fmt(r['impressions'])} {badge(id_)}</td>
      <td class="num">{r['ctr']:.2f}%</td>
      <td class="num">{r['avg_position']:.1f} <span class="delta {("worse" if pd>0 else "better") if abs(pd)>0.1 else ""}">{("+"+f"{pd:.1f}") if pd>=0 else f"{pd:.1f}"}</span>{pos_flag}</td>
    </tr>'''

# ── low-CTR pages table ────────────────────────────────────────────────────────

def pages_rows_html():
    rows = ''
    all_pages = []
    for c in COUNTRIES:
        for p in pages.get(c, []):
            all_pages.append((c, p))
    all_pages.sort(key=lambda x: x[1]['impressions'], reverse=True)
    for c, p in all_pages[:15]:
        path = p['page'].replace('https://www.ironhack.com', '') or '/'
        ctr  = p['ctr']
        low  = p['impressions'] > 3000 and ctr < 0.1
        ctr_cls = 'ctr-low' if low else ('ctr-ok' if ctr > 0.5 else '')
        flag = ' <span class="badge down" style="font-size:10px">LOW CTR</span>' if low else ''
        rows += f'''
    <tr>
      <td><span class="country-tag">{COUNTRY_CODES[c]}</span> <span class="url">{path[:80]}</span>{flag}</td>
      <td class="num">{fmt(p["impressions"])}</td>
      <td class="num">{p["clicks"]}</td>
      <td class="num {ctr_cls}">{ctr:.2f}%</td>
    </tr>'''
    return rows

# ── movers tables ──────────────────────────────────────────────────────────────

def movers_html(c):
    m = movers.get(c, {'up': [], 'down': []})
    def row(item, is_up):
        delta_str = f"+{item['delta']}" if item['delta'] > 0 else str(item['delta'])
        cls = 'up' if is_up else 'down'
        brand_tag = ' <span class="brand-tag">brand</span>' if item['brand'] else ''
        return f'<tr><td class="url">{item["query"][:60]}{brand_tag}</td><td class="num"><span class="badge {cls}">{delta_str}</span></td><td class="num small">{item["prev"]}→{item["recent"]}</td><td class="num small">{fmt(item["imp"])} imp</td></tr>'
    up_rows   = ''.join(row(x, True)  for x in m['up']   if x['delta'] > 0)
    down_rows = ''.join(row(x, False) for x in m['down'] if x['delta'] < 0)
    return up_rows, down_rows

# ── assemble HTML ──────────────────────────────────────────────────────────────

trend_sections = ''
for c in COUNTRIES:
    bars, traj = trend_bar_html(c)
    trend_sections += f'''
    <div class="trend-market">
      <div class="trend-market-header">
        <span class="flag">{COUNTRY_FLAGS[c]}</span>
        <strong>{COUNTRY_CODES[c]} — {COUNTRY_NAMES[c]}</strong>
        {traj}
      </div>
      {bars}
    </div>'''

market_rows = ''.join(market_row(c) for c in COUNTRIES)

movers_sections = ''
for c in COUNTRIES:
    up_rows, down_rows = movers_html(c)
    movers_sections += f'''
    <div class="movers-market">
      <h3>{COUNTRY_FLAGS[c]} {COUNTRY_CODES[c]} — {COUNTRY_NAMES[c]}</h3>
      <div class="movers-cols">
        <div>
          <div class="movers-title up-title">Gainers</div>
          <table><thead><tr><th>Query</th><th>Δ</th><th>Clicks</th><th>Imp</th></tr></thead>
          <tbody>{up_rows or "<tr><td colspan=4 class=zero>No gainers</td></tr>"}</tbody></table>
        </div>
        <div>
          <div class="movers-title down-title">Losers</div>
          <table><thead><tr><th>Query</th><th>Δ</th><th>Clicks</th><th>Imp</th></tr></thead>
          <tbody>{down_rows or "<tr><td colspan=4 class=zero>No losers</td></tr>"}</tbody></table>
        </div>
      </div>
    </div>'''

html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SEO Weekly Snapshot — {period_str}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f5f5f7; color: #1d1d1f; font-size: 14px; }}
  .wrap {{ max-width: 1100px; margin: 0 auto; padding: 32px 20px; }}
  h1 {{ font-size: 24px; font-weight: 700; margin-bottom: 4px; }}
  h2 {{ font-size: 16px; font-weight: 600; margin-bottom: 16px; }}
  h3 {{ font-size: 14px; font-weight: 600; margin-bottom: 10px; }}
  .subtitle {{ color: #6e6e73; margin-bottom: 28px; font-size: 13px; }}

  .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin-bottom: 28px; }}
  .card {{ background: white; border-radius: 12px; padding: 18px 20px; box-shadow: 0 1px 3px rgba(0,0,0,.07); }}
  .card .label {{ font-size: 10px; text-transform: uppercase; letter-spacing: .6px; color: #6e6e73; margin-bottom: 8px; }}
  .card .value {{ font-size: 26px; font-weight: 700; line-height: 1; }}
  .card .sub {{ font-size: 12px; color: #6e6e73; margin-top: 6px; }}
  .card.green .value {{ color: #34c759; }}
  .card.red   .value {{ color: #ff3b30; }}
  .card.blue  .value {{ color: #007aff; }}
  .card.orange .value {{ color: #ff9500; }}

  section {{ background: white; border-radius: 12px; padding: 24px; box-shadow: 0 1px 3px rgba(0,0,0,.07); margin-bottom: 20px; }}

  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ text-align: left; font-weight: 600; color: #6e6e73; font-size: 11px; text-transform: uppercase; letter-spacing: .4px; padding: 0 8px 10px 0; white-space: nowrap; }}
  td {{ padding: 8px 8px 8px 0; border-top: 1px solid #f5f5f7; vertical-align: middle; }}
  .num {{ text-align: right; white-space: nowrap; }}
  .small {{ font-size: 12px; color: #6e6e73; }}
  .url {{ font-family: "SF Mono", "Fira Mono", monospace; font-size: 12px; word-break: break-all; }}
  .zero {{ color: #c7c7cc; font-size: 12px; padding: 6px 0; }}

  .badge {{ display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: 600; }}
  .badge.up      {{ background: #d1f5dc; color: #1a7f37; }}
  .badge.down    {{ background: #fde8e8; color: #cf222e; }}
  .badge.neutral {{ background: #f0f0f0; color: #6e6e73; }}
  .pos-flag {{ font-size: 10px; color: #ff9500; font-weight: 500; }}
  .delta.worse {{ color: #cf222e; }}
  .delta.better {{ color: #1a7f37; }}
  .flag {{ font-size: 16px; }}
  .brand-tag {{ display: inline-block; background: #e8f0fe; color: #1a56db; border-radius: 3px; padding: 0 4px; font-size: 10px; font-weight: 500; margin-left: 3px; }}
  .country-tag {{ display: inline-block; background: #f0f0f0; border-radius: 3px; padding: 1px 5px; font-size: 11px; font-weight: 600; color: #1d1d1f; margin-right: 4px; }}
  .ctr-low {{ color: #cf222e; font-weight: 600; }}
  .ctr-ok  {{ color: #1a7f37; }}

  /* 4-week trend */
  .trend-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; }}
  .trend-market {{ padding: 16px; background: #f9f9fb; border-radius: 10px; }}
  .trend-market-header {{ display: flex; align-items: center; gap: 8px; margin-bottom: 12px; font-size: 13px; }}
  .trend-row {{ display: flex; align-items: center; gap: 8px; margin-bottom: 6px; font-size: 12px; }}
  .trend-label {{ width: 80px; color: #6e6e73; flex-shrink: 0; }}
  .trend-bar-wrap {{ flex: 1; height: 10px; background: #e8e8ed; border-radius: 5px; overflow: hidden; }}
  .trend-bar {{ height: 10px; border-radius: 5px; transition: width .3s; }}
  .bar-w1  {{ background: #007aff; }}
  .bar-w2  {{ background: #5ac8fa; }}
  .bar-old {{ background: #c7c7cc; }}
  .trend-val {{ width: 70px; text-align: right; font-weight: 600; white-space: nowrap; }}
  .trend-sub {{ font-size: 10px; color: #6e6e73; font-weight: 400; }}

  /* movers */
  .movers-market {{ margin-bottom: 24px; padding-bottom: 24px; border-bottom: 1px solid #f0f0f0; }}
  .movers-market:last-child {{ border-bottom: none; margin-bottom: 0; padding-bottom: 0; }}
  .movers-cols {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
  .movers-title {{ font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .4px; margin-bottom: 8px; }}
  .up-title   {{ color: #1a7f37; }}
  .down-title {{ color: #cf222e; }}
  @media (max-width: 640px) {{ .movers-cols {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<div class="wrap">

  <h1>SEO Weekly Snapshot</h1>
  <div class="subtitle">
    This week: {period_str} &nbsp;&middot;&nbsp; vs {prev_str} &nbsp;&middot;&nbsp; Generated {run_date}
  </div>

  <div class="cards">
    <div class="card {'green' if clicks_delta > 0 else 'red'}">
      <div class="label">Total Clicks</div>
      <div class="value">{fmt(total_r['clicks'])}</div>
      <div class="sub">{badge(clicks_delta)} vs last week (was {fmt(total_p['clicks'])})</div>
    </div>
    <div class="card blue">
      <div class="label">Total Impressions</div>
      <div class="value">{fmt(total_r['impressions'])}</div>
      <div class="sub">{badge(imp_delta)} vs last week</div>
    </div>
    <div class="card">
      <div class="label">Avg CTR</div>
      <div class="value">{total_ctr:.2f}%</div>
      <div class="sub">across all 5 markets</div>
    </div>
    <div class="card green">
      <div class="label">Best WoW</div>
      <div class="value">{COUNTRY_CODES[best_c]}</div>
      <div class="sub">{badge(pct(recent_agg.get(best_c,{}).get("clicks",0), prev_agg.get(best_c,{}).get("clicks",1)))} clicks this week</div>
    </div>
    <div class="card {'red' if pct(buckets[0]["agg"].get(worst_traj_c,{}).get("clicks",0), buckets[-1]["agg"].get(worst_traj_c,{}).get("clicks",1)) < -5 else ''}">
      <div class="label">Weakest 4-Week Trend</div>
      <div class="value">{COUNTRY_CODES[worst_traj_c]}</div>
      <div class="sub">{fmt_pct(pct(buckets[0]["agg"].get(worst_traj_c,{}).get("clicks",0), buckets[-1]["agg"].get(worst_traj_c,{}).get("clicks",1)))} over 4 weeks</div>
    </div>
  </div>

  <section>
    <h2>4-Week Click Trend</h2>
    <div class="trend-grid">
      {trend_sections}
    </div>
  </section>

  <section>
    <h2>Market Summary (WoW)</h2>
    <table>
      <thead><tr>
        <th>Market</th>
        <th style="text-align:right">Clicks</th>
        <th style="text-align:right">Brand / Non-brand</th>
        <th style="text-align:right">Impressions</th>
        <th style="text-align:right">CTR</th>
        <th style="text-align:right">Avg Pos</th>
      </tr></thead>
      <tbody>{market_rows}</tbody>
    </table>
  </section>

  <section>
    <h2>Top Pages by Impressions</h2>
    <p style="font-size:12px;color:#6e6e73;margin-bottom:16px">Pages with high impressions and CTR &lt; 0.1% are marked LOW CTR — likely absorbed by AI Overviews.</p>
    <table>
      <thead><tr><th>Page</th><th style="text-align:right">Impressions</th><th style="text-align:right">Clicks</th><th style="text-align:right">CTR</th></tr></thead>
      <tbody>{pages_rows_html()}</tbody>
    </table>
  </section>

  <section>
    <h2>Top Movers by Clicks</h2>
    {movers_sections}
  </section>

<!-- agent sections appended below -->
'''

print(html)
