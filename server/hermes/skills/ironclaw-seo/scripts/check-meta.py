#!/usr/bin/env python3
"""Quick metadata checker for Ironhack pages."""
import sys, re, subprocess

def fetch(url):
    r = subprocess.run(['curl', '-sL', url], capture_output=True, text=True, timeout=15)
    return r.stdout

def check(url):
    html = fetch(url)
    if not html:
        print(f"  FAILED to fetch {url}")
        return
    
    # Title
    m = re.search(r'<title[^>]*>(.*?)</title>', html, re.S)
    title = m.group(1).strip() if m else 'MISSING'
    print(f"  TITLE: {title} ({len(title)} chars)")
    
    # Meta description
    m = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', html)
    if not m:
        m = re.search(r"<meta\s+name='description'\s+content='([^']*)'", html)
    desc = m.group(1) if m else 'MISSING'
    print(f"  DESC: {desc[:120]}... ({len(desc)} chars)")
    
    # Canonical
    m = re.search(r'<link\s+rel="canonical"\s+href="([^"]*)"', html)
    print(f"  CANONICAL: {m.group(1) if m else 'MISSING'}")
    
    # H1
    m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
    if m:
        h1 = re.sub(r'<[^>]+>', '', m.group(1)).strip()[:100]
    else:
        h1 = 'MISSING'
    print(f"  H1: {h1}")
    
    # OG tags
    ogs = re.findall(r'<meta\s+property="og:([^"]+)"\s+content="([^"]*)"', html)
    print(f"  OG tags: {len(ogs)}")
    for k, v in ogs:
        print(f"    og:{k}: {v[:80]}")
    
    # Hreflang (case-insensitive — site uses hrefLang with capital L)
    hls = re.findall(r'<link\s+rel="alternate"\s+hreflang="([^"]+)"\s+href="([^"]*)"', html, re.IGNORECASE)
    print(f"  HREFLANG: {len(hls)} tags")
    for k, v in hls:
        print(f"    {k}: {v}")
    
    # Schema types
    schemas = re.findall(r'"@type"\s*:\s*"([^"]+)"', html)
    print(f"  SCHEMA: {list(set(schemas))}")
    
    # robots meta
    m = re.search(r'<meta\s+name="robots"\s+content="([^"]*)"', html)
    if m:
        print(f"  ROBOTS: {m.group(1)}")

if __name__ == '__main__':
    urls = sys.argv[1:] if len(sys.argv) > 1 else [
        'https://www.ironhack.com/es-en',
        'https://www.ironhack.com/de-en',
        'https://www.ironhack.com/fr-en',
        'https://www.ironhack.com/nl-en',
        'https://www.ironhack.com/pt-en',
    ]
    for url in urls:
        print(f"\n{'='*60}")
        print(f"URL: {url}")
        print('='*60)
        check(url)
