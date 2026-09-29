#!/usr/bin/env python3
"""Analyze GSC data from two 7-day windows with optional 28-day trend and page data.

Usage:
  python3 analyze-gsc.py <recent.json> <previous.json> [trend28.json] [pages.json]

  recent.json   - 7-day window (most recent), dimensions: query,country,date
  previous.json - 7-day window (prior week for WoW comparison), dimensions: query,country,date
  trend28.json  - 28-day window (optional; enables 4-week trend section), dimensions: query,country,date
  pages.json    - 7-day window (optional; enables top pages section), dimensions: page,country
"""
import json, sys
from collections import defaultdict
from datetime import datetime

COUNTRY_NAMES = {
    'esp': 'ES (Spain)', 'fra': 'FR (France)', 'deu': 'DE (Germany)',
    'prt': 'PT (Portugal)', 'nld': 'NL (Netherlands)'
}
COUNTRIES = ['esp', 'fra', 'deu', 'prt', 'nld']


def load(path):
    with open(path) as f:
        return json.load(f)


def is_brand(query):
    q = query.lower()
    return 'ironhack' in q or 'iron hack' in q


def aggregate_by_country(rows):
    by_c = defaultdict(lambda: {'clicks': 0, 'impressions': 0, 'pos_sum': 0.0, 'pos_w': 0})
    for r in rows:
        c = r['keys'][1]
        by_c[c]['clicks'] += r['clicks']
        by_c[c]['impressions'] += r['impressions']
        by_c[c]['pos_sum'] += r['position'] * r['impressions']
        by_c[c]['pos_w'] += r['impressions']
    out = {}
    for c, d in by_c.items():
        imp = d['impressions']
        out[c] = {
            'clicks': d['clicks'],
            'impressions': imp,
            'ctr': round(d['clicks'] / imp * 100, 3) if imp else 0,
            'avg_position': round(d['pos_sum'] / d['pos_w'], 2) if d['pos_w'] else 0,
        }
    return out


def brand_split(rows):
    out = defaultdict(lambda: {
        'brand':    {'clicks': 0, 'impressions': 0},
        'nonbrand': {'clicks': 0, 'impressions': 0},
    })
    for r in rows:
        c = r['keys'][1]
        k = 'brand' if is_brand(r['keys'][0]) else 'nonbrand'
        out[c][k]['clicks'] += r['clicks']
        out[c][k]['impressions'] += r['impressions']
    return out


def daily_breakdown(rows):
    bd = defaultdict(lambda: defaultdict(lambda: {'clicks': 0, 'impressions': 0}))
    for r in rows:
        bd[r['keys'][1]][r['keys'][2]]['clicks'] += r['clicks']
        bd[r['keys'][1]][r['keys'][2]]['impressions'] += r['impressions']
    return bd


def top_movers(recent_rows, prev_rows, n=5):
    def by_query(rows):
        q = defaultdict(lambda: {'clicks': 0, 'impressions': 0})
        for r in rows:
            k = (r['keys'][0], r['keys'][1])
            q[k]['clicks'] += r['clicks']
            q[k]['impressions'] += r['impressions']
        return q

    rq, pq = by_query(recent_rows), by_query(prev_rows)
    movers = defaultdict(list)
    for (query, country) in set(rq) | set(pq):
        rc = rq[(query, country)]['clicks']
        pc = pq[(query, country)]['clicks']
        ri = rq[(query, country)]['impressions']
        movers[country].append({
            'query': query, 'delta': rc - pc,
            'recent_clicks': rc, 'prev_clicks': pc,
            'recent_imp': ri, 'brand': is_brand(query),
        })
    return {
        c: {
            'up':   sorted(ms, key=lambda x: x['delta'], reverse=True)[:n],
            'down': sorted(ms, key=lambda x: x['delta'])[:n],
        }
        for c, ms in movers.items()
    }


def weekly_buckets(trend_rows):
    """Split trend rows into up to 4 weekly buckets, most recent first."""
    all_dates = sorted(set(r['keys'][2] for r in trend_rows), reverse=True)
    buckets = []
    for i in range(0, min(28, len(all_dates)), 7):
        week_set = set(all_dates[i:i + 7])
        if not week_set:
            break
        rows = [r for r in trend_rows if r['keys'][2] in week_set]
        dl = sorted(week_set)
        buckets.append({'start': dl[0], 'end': dl[-1], 'rows': rows})
    return buckets


def fmt(n):
    return f"{int(n):,}" if n >= 1000 else str(int(n))


def pct(new, old):
    if old == 0:
        return float('inf') if new > 0 else 0.0
    return (new - old) / old * 100


def fmtpct(v):
    if v == float('inf'):
        return '+inf%'
    return f"{'+' if v > 0 else ''}{v:.1f}%"


def top_pages(pages_rows, n=5):
    """Return top n pages per country sorted by impressions, with CTR flag."""
    by_country = defaultdict(list)
    for r in pages_rows:
        page, country = r['keys'][0], r['keys'][1]
        by_country[country].append({
            'page': page,
            'impressions': r['impressions'],
            'clicks': r['clicks'],
            'ctr': r['ctr'],
            'position': r.get('position', 0),
        })
    return {
        c: sorted(pages, key=lambda x: x['impressions'], reverse=True)[:n]
        for c, pages in by_country.items()
    }


def main():
    recent_data = load(sys.argv[1])
    prev_data   = load(sys.argv[2])
    trend_data  = load(sys.argv[3]) if len(sys.argv) > 3 else None
    pages_data  = load(sys.argv[4]) if len(sys.argv) > 4 else None

    recent_rows = recent_data['rows']
    prev_rows   = prev_data['rows']

    recent_start = recent_data.get('start_date', '?')
    recent_end   = recent_data.get('end_date',   '?')
    prev_start   = prev_data.get('start_date',   '?')
    prev_end     = prev_data.get('end_date',     '?')

    recent_agg  = aggregate_by_country(recent_rows)
    prev_agg    = aggregate_by_country(prev_rows)
    recent_b    = brand_split(recent_rows)
    prev_b      = brand_split(prev_rows)
    daily       = daily_breakdown(recent_rows)
    movers      = top_movers(recent_rows, prev_rows)
    all_dates   = sorted(set(r['keys'][2] for r in recent_rows))

    lines = []
    lines.append(f"# GSC Analysis — {datetime.now().strftime('%Y-%m-%d')}")
    lines.append(f"- Recent: {recent_start} to {recent_end}  |  Previous: {prev_start} to {prev_end}")
    lines.append(f"- Rows: recent {recent_data.get('total_fetched','?')} fetched / {recent_data.get('total_filtered','?')} filtered"
                 f"  |  prev {prev_data.get('total_fetched','?')} / {prev_data.get('total_filtered','?')}")
    lines.append("")

    # --- 4-week trend (only when trend data provided) ---
    if trend_data:
        lines.append("## 4-Week Click Trend")
        lines.append("W1 = most recent week, W4 = oldest. Trajectory = W4 to W1.")
        lines.append("")
        buckets = weekly_buckets(trend_data['rows'])
        for c in COUNTRIES:
            name = COUNTRY_NAMES[c]
            lines.append(f"### {name}")
            week_clicks = []
            for i, b in enumerate(buckets):
                agg = aggregate_by_country(b['rows']).get(c, {})
                cl  = agg.get('clicks', 0)
                imp = agg.get('impressions', 0)
                week_clicks.append(cl)
                lines.append(f"- W{i+1} ({b['start']} to {b['end']}): {fmt(cl)} clicks, {fmt(imp)} imp")
            if len(week_clicks) >= 2:
                traj = pct(week_clicks[0], week_clicks[-1])
                lines.append(f"- Trajectory (W{len(week_clicks)} to W1): {fmtpct(traj)} ({fmt(week_clicks[-1])} -> {fmt(week_clicks[0])})")
            lines.append("")

    # --- Market summary ---
    lines.append("## Market Summary (WoW)")
    lines.append("")
    for c in COUNTRIES:
        name = COUNTRY_NAMES[c]
        r = recent_agg.get(c, {'clicks': 0, 'impressions': 0, 'ctr': 0, 'avg_position': 0})
        p = prev_agg.get(c,   {'clicks': 0, 'impressions': 0, 'ctr': 0, 'avg_position': 0})
        pos_delta = r['avg_position'] - p['avg_position']
        pos_flag  = " [POS SHIFT >2]" if abs(pos_delta) > 2 else ""

        rb = recent_b.get(c, {'brand': {'clicks': 0, 'impressions': 0}, 'nonbrand': {'clicks': 0, 'impressions': 0}})
        pb = prev_b.get(c,   {'brand': {'clicks': 0, 'impressions': 0}, 'nonbrand': {'clicks': 0, 'impressions': 0}})

        lines.append(f"### {name}{pos_flag}")
        lines.append(f"- Clicks: {fmt(r['clicks'])} (was {fmt(p['clicks'])}, {fmtpct(pct(r['clicks'], p['clicks']))})")
        lines.append(f"  - Brand: {fmt(rb['brand']['clicks'])} (was {fmt(pb['brand']['clicks'])}, {fmtpct(pct(rb['brand']['clicks'], pb['brand']['clicks']))})")
        lines.append(f"  - Non-brand: {fmt(rb['nonbrand']['clicks'])} (was {fmt(pb['nonbrand']['clicks'])}, {fmtpct(pct(rb['nonbrand']['clicks'], pb['nonbrand']['clicks']))})")
        lines.append(f"- Impressions: {fmt(r['impressions'])} (was {fmt(p['impressions'])}, {fmtpct(pct(r['impressions'], p['impressions']))})")
        lines.append(f"- CTR: {r['ctr']:.3f}%  |  Avg Position: {r['avg_position']:.1f} ({'+' if pos_delta >= 0 else ''}{pos_delta:.1f} WoW)")
        lines.append("")

    # --- Daily breakdown ---
    lines.append("## Daily Breakdown (Recent Window)")
    lines.append("")
    for c in COUNTRIES:
        lines.append(f"### {COUNTRY_NAMES[c]}")
        for d in all_dates:
            dd = daily.get(c, {}).get(d, {'clicks': 0, 'impressions': 0})
            lines.append(f"- {d}: {fmt(dd['clicks'])} clicks, {fmt(dd['impressions'])} imp")
        lines.append("")

    # --- Top movers ---
    lines.append("## Top Movers (by clicks)")
    lines.append("")
    for c in COUNTRIES:
        name = COUNTRY_NAMES[c]
        m = movers.get(c, {'up': [], 'down': []})

        lines.append(f"### {name} — Gainers")
        for item in m['up']:
            if item['delta'] > 0:
                tag = " [brand]" if item['brand'] else ""
                lines.append(f"- \"{item['query'][:80]}\"{tag}: +{item['delta']} ({item['prev_clicks']} -> {item['recent_clicks']}), imp {item['recent_imp']}")
        lines.append("")

        lines.append(f"### {name} — Losers")
        for item in m['down']:
            if item['delta'] < 0:
                tag = " [brand]" if item['brand'] else ""
                lines.append(f"- \"{item['query'][:80]}\"{tag}: {item['delta']} ({item['prev_clicks']} -> {item['recent_clicks']}), imp {item['recent_imp']}")
        lines.append("")

    # --- Top pages (only when pages data provided) ---
    if pages_data:
        pages = top_pages(pages_data['rows'])
        lines.append("## Top Pages by Impressions")
        lines.append("Pages with high impressions and low CTR are candidates for title/meta optimization or are being cannibalized by AI Overviews.")
        lines.append("")
        for c in COUNTRIES:
            name = COUNTRY_NAMES[c]
            pg = pages.get(c, [])
            if not pg:
                continue
            lines.append(f"### {name}")
            for p in pg:
                path = p['page'].replace('https://www.ironhack.com', '') or '/'
                ctr_pct = p['ctr'] * 100
                flag = " [LOW CTR]" if p['impressions'] > 5000 and ctr_pct < 0.1 else ""
                lines.append(f"- {fmt(p['impressions'])} imp / {p['clicks']} clicks / CTR {ctr_pct:.2f}%{flag}  {path}")
            lines.append("")

    # --- Auto-detected anomalies ---
    lines.append("## Auto-Detected Anomalies")
    lines.append("")
    anomalies = []
    for c in COUNTRIES:
        name = COUNTRY_NAMES[c]
        r = recent_agg.get(c, {'clicks': 0, 'impressions': 0, 'avg_position': 0})
        p = prev_agg.get(c,   {'clicks': 0, 'impressions': 0, 'avg_position': 0})
        cd  = pct(r['clicks'], p['clicks'])
        id_ = pct(r['impressions'], p['impressions'])
        pd  = r['avg_position'] - p['avg_position']
        rb  = recent_b.get(c, {'brand': {'clicks': 0}})
        pb_ = prev_b.get(c,   {'brand': {'clicks': 0}})

        if abs(cd) > 15:
            anomalies.append(f"{name}: clicks {'up' if cd > 0 else 'down'} {abs(cd):.0f}% ({fmt(p['clicks'])} -> {fmt(r['clicks'])})")
        if abs(id_) > 20:
            anomalies.append(f"{name}: impressions {'up' if id_ > 0 else 'down'} {abs(id_):.0f}% ({fmt(p['impressions'])} -> {fmt(r['impressions'])})")
        if abs(pd) > 2:
            anomalies.append(f"{name}: avg position {'worsened' if pd > 0 else 'improved'} {abs(pd):.1f} ({p['avg_position']:.1f} -> {r['avg_position']:.1f})")
        if pb_['brand']['clicks'] > 10:
            bd = pct(rb['brand']['clicks'], pb_['brand']['clicks'])
            if abs(bd) > 20:
                anomalies.append(f"{name}: brand clicks {'up' if bd > 0 else 'down'} {abs(bd):.0f}% ({fmt(pb_['brand']['clicks'])} -> {fmt(rb['brand']['clicks'])})")

    if anomalies:
        for a in anomalies:
            lines.append(f"- {a}")
    else:
        lines.append("- No anomalies detected (all metrics within normal range).")
    lines.append("")

    print('\n'.join(lines))


if __name__ == '__main__':
    main()
