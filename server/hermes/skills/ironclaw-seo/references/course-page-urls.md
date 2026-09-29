# Ironhack Course Page URL Patterns

Verified live June 25, 2026. Source: sitemap.xml per market + curl verification.

## Standard Course Pages (all 5 markets)

Base: `https://www.ironhack.com/{market}/`

| Course | Path | All Markets |
|--------|------|-------------|
| Web Development | `{market}/web-development` | es-en, de-en, fr-en, nl-en, pt-en |
| Data Analytics | `{market}/data-analytics` | es-en, de-en, fr-en, nl-en, pt-en |
| UX/UI Design | `{market}/ux-ui-design` | es-en, de-en, fr-en, nl-en, pt-en |
| Cybersecurity | `{market}/cybersecurity` | es-en, de-en, fr-en, nl-en, pt-en |

All return HTTP 200 via curl.

## City-Specific PDP Pages (varied by market)

Pattern: `{market}/{course}/{city}`

Examples from ES-en sitemap:
- `/es-en/cybersecurity/barcelona`
- `/es-en/cybersecurity/madrid`
- `/es-en/cybersecurity/remote`
- `/es-en/data-analytics/barcelona`
- `/es-en/data-analytics/madrid`
- `/es-en/data-analytics/remote`
- `/es-en/ux-ui-design/barcelona`
- `/es-en/ux-ui-design/madrid`
- `/es-en/ux-ui-design/remote`

City pages vary by market. Use sitemap to enumerate per market.

## New/Special Course Pages

| Course | Path | Status (Jun 2026) |
|--------|------|-------------------|
| AI Engineering | `{market}/ai-engineering` | HTTP 404 on all 5 markets. Not in sitemap. |
| Data Engineering | `{market}/data-engineering/remote` | In ES sitemap |
| Data Science & ML | `{market}/data-science-machine-learning/remote` | In ES sitemap |
| AI Product Manager | `{market}/ai-product-manager/remote` | In ES sitemap |
| AI Consulting | `{market}/ai-consulting-integration/remote` | In ES sitemap |

## Discovery Method

When unsure about a path, check the sitemap:
```bash
curl -sL https://www.ironhack.com/{market}/sitemap.xml | grep -oP '<loc>[^<]+</loc>' | grep -i 'course\|bootcamp\|web-dev\|data\|ux\|cyber\|ai'
```

## Pitfalls

- **Do NOT use `-bootcamp` suffix.** `/es-en/web-development-bootcamp` returns 404. The path is `/es-en/web-development`.
- **Do NOT use `/courses` index.** `/{market}/courses` returns 404. There is no course listing page at that path.
- **AI Engineering pages return 404** while standard course pages return 200. This is a routing issue, not a CMS data issue. The page template may exist but routing doesn't serve it.
- **JavaScript SPA behavior:** Course pages return 200 to curl despite the site being Next.js (SSR is working for course pages). Campus pages (e.g., `/de-en/campus/berlin`) return 404 to curl while appearing functional in a browser.
