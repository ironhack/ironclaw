## Branded Per-Bootcamp Report Format

Each of the 12 per-bootcamp reports uses this template. The Ironhack logo is embedded as a
base64 data URI so reports are self-contained and render correctly when saved as PDF.

**Bootcamp display names and descriptions:**

| Slug | Display Name | One-sentence description |
|---|---|---|
| ai-web-development | AI Web Development | Full-stack JavaScript development with React, Node.js, MongoDB, and AI-assisted workflows. |
| data-analytics | Data Analytics | Python, SQL, Tableau, and Power BI for data-driven decision making. |
| ai-consulting-integration | AI Consulting & Integration | AI workflow automation, RAG systems, and LLM orchestration for business consulting. |
| ai-driven-ux-ui | AI-Driven UX/UI Design | User research, Figma prototyping, and accessible UI design with AI tools. |
| data-science-ml | Data Science & Machine Learning | Python-based ML, deep learning, NLP, and generative AI model development. |
| ai-engineering | AI Engineering | LLM fine-tuning, RAG architectures, and MLOps with PyTorch and AWS. |
| cloud-engineering | Cloud Engineering | AWS infrastructure, Terraform IaC, Kubernetes, and DevSecOps. |
| data-engineering | Data Engineering | ETL pipelines, Apache Airflow, Kafka, and cloud data warehousing. |
| ai-driven-marketing | AI-Driven Marketing | Digital marketing strategy, GA4, paid media, and AI-powered automation. |
| cybersecurity | Cybersecurity | Network defense, penetration testing, SIEM, and incident response. |
| ai-product-management | AI Product Management | Agile product management, user research, and AI-integrated prototyping. |
| devops | DevOps & Cloud Computing | Linux, Docker, Kubernetes, GitHub Actions CI/CD, and multi-cloud. |


**HTML template:**

When generating a per-bootcamp branded report, build the HTML programmatically in Python.
Replace the placeholders shown below with actual data from the DB query.

Key placeholder reference:
- `LOGO_BASE64_HERE` → the base64 string defined at the bottom of this section
- `BOOTCAMP_NAME` → display name from the table above
- `BOOTCAMP_DESCRIPTION` → one-sentence description from the table above
- `DATE` → today's date (YYYY-MM-DD)
- `ACTIVE_COUNT` → count of rows in the filtered top-10 result set (not total active)
- `JOB_URL`, `JOB_TITLE`, `COMPANY`, `LOCATION` → from DB row
- `LANG_TAG_CLASS`, `LANG_LABEL` → derived from `language_req` (see tag mapping below)
- `EXP_TAG_CLASS`, `EXP_LABEL` → derived from `experience_level` (see tag mapping below)
- `SUMMARY_TEXT` → `summary` column value, or pending placeholder if NULL

**CSS + structure (write once per report, then loop job cards):**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Ironhack Germany — {bootcamp_name} Jobs — {date}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ font-family: Arial, sans-serif; max-width: 960px; margin: 0 auto; padding: 32px 24px; color: #1a1a1a; background: #fff; }}
    .header {{ display: flex; align-items: center; justify-content: space-between; border-bottom: 4px solid #5BBFE3; padding-bottom: 20px; margin-bottom: 0; }}
    .header img {{ height: 48px; }}
    .header-right {{ text-align: right; }}
    .header-label {{ font-size: 12px; font-weight: bold; text-transform: uppercase; letter-spacing: 1px; color: #5BBFE3; }}
    .header-date {{ font-size: 12px; color: #888; margin-top: 2px; }}
    .hero {{ background: linear-gradient(135deg, #0d1b2a 0%, #1a3a5c 100%); color: #fff; border-radius: 8px; padding: 28px 32px; margin: 24px 0 20px; }}
    .hero h1 {{ font-size: 26px; font-weight: bold; margin: 0 0 6px; }}
    .hero .hero-sub {{ font-size: 14px; color: #9dcfe8; margin: 0; }}
    .toolbar {{ display: flex; align-items: center; gap: 12px; margin-bottom: 28px; flex-wrap: wrap; }}
    .btn-pdf {{ background: #5BBFE3; color: #fff; border: none; padding: 10px 20px; border-radius: 5px; font-size: 13px; font-weight: bold; cursor: pointer; white-space: nowrap; }}
    .btn-pdf:hover {{ background: #3aa8d8; }}
    .stat-badge {{ background: #f0f8fc; border: 1px solid #c0e4f0; border-radius: 4px; padding: 9px 14px; font-size: 13px; color: #2a6a85; flex: 1; }}
    .job-card {{ border: 1px solid #e4e8ec; border-radius: 8px; padding: 20px 22px; margin-bottom: 12px; page-break-inside: avoid; }}
    .job-card:hover {{ border-color: #5BBFE3; box-shadow: 0 2px 8px rgba(91,191,227,0.18); }}
    .card-top {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }}
    .card-main {{ flex: 1; min-width: 0; }}
    .job-title {{ font-size: 16px; font-weight: bold; margin: 0 0 4px; color: #0d1b2a; }}
    .job-meta {{ font-size: 13px; color: #666; margin-bottom: 10px; }}
    .tags {{ display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 12px; }}
    .tag {{ padding: 2px 9px; border-radius: 12px; font-size: 11px; font-weight: bold; }}
    .tag-en     {{ background: #d4edda; color: #155724; }}
    .tag-b1     {{ background: #fff3cd; color: #856404; }}
    .tag-unk    {{ background: #f0f0f0; color: #666; }}
    .tag-req    {{ background: #fce4e4; color: #8b0000; }}
    .tag-jr     {{ background: #e8f0fe; color: #1a56b0; }}
    .tag-intern {{ background: #e3f5e1; color: #1a6e1a; }}
    .view-btn {{ flex-shrink: 0; display: inline-block; border: 1.5px solid #5BBFE3; color: #2a7aa0; padding: 7px 14px; border-radius: 5px; font-size: 12px; font-weight: bold; text-decoration: none; white-space: nowrap; align-self: flex-start; }}
    .view-btn:hover {{ background: #5BBFE3; color: #fff; }}
    .summary-label {{ font-size: 10px; font-weight: bold; text-transform: uppercase; color: #bbb; letter-spacing: 0.5px; margin: 0 0 4px; }}
    .summary-text {{ font-size: 13px; color: #444; line-height: 1.55; margin: 0; }}
    .footer {{ margin-top: 48px; font-size: 11px; color: #bbb; border-top: 1px solid #eee; padding-top: 14px; }}
    @media print {{
      .btn-pdf {{ display: none !important; }}
      .toolbar {{ margin-bottom: 16px; }}
      .view-btn {{ border-color: #999; color: #333; }}
      .hero {{ background: #0d1b2a !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
      body {{ padding: 16px; }}
    }}
  </style>
</head>
<body>
  <div class="header">
    <img src="data:image/jpeg;base64,{logo_b64}" alt="Ironhack">
    <div class="header-right">
      <div class="header-label">Germany Job Market Report</div>
      <div class="header-date">Generated: {date}</div>
    </div>
  </div>
  <div class="hero">
    <h1>{bootcamp_name}</h1>
    <p class="hero-sub">{bootcamp_description}</p>
  </div>
  <div class="toolbar">
    <button class="btn-pdf" id="btnPdf">&#128438; Print / Save as PDF</button>
    <div class="stat-badge">
      <strong>{active_count} best-fit listings</strong> &nbsp;&middot;&nbsp; Junior &amp; entry-level priority &nbsp;&middot;&nbsp; English-first &nbsp;&middot;&nbsp; Source: LinkedIn &nbsp;&middot;&nbsp; Verified: {date}
    </div>
  </div>
  {job_cards}
  <div class="footer">
    Ironhack Germany &mdash; Job Market Intelligence &nbsp;&middot;&nbsp; {date} &nbsp;&middot;&nbsp;
    All listings sourced from public job boards. Click any "View listing" button to verify the original posting on LinkedIn.
  </div>
  <script>
    document.getElementById('btnPdf').addEventListener('click', function() {{
      window.print();
    }});
  </script>
</body>
</html>
```

**Job card template (repeat for each DB row):**

```html
<div class="job-card">
  <div class="card-top">
    <div class="card-main">
      <div class="job-title">{title}</div>
      <div class="job-meta">{company} &nbsp;&middot;&nbsp; {location}</div>
      <div class="tags">
        <span class="tag {lang_class}">{lang_label}</span>
        <span class="tag {exp_class}">{exp_label}</span>
      </div>
      <div class="summary-label">Summary</div>
      <p class="summary-text">{summary_text}</p>
    </div>
    <a class="view-btn" href="{url}" target="_blank">View listing &#8594;</a>
  </div>
</div>
```

If `summary IS NULL`: use `<em style="color:#aaa">Summary available after next scrape.</em>` as `summary_text`.

**Tag class + label mapping:**

| `language_req` value | `lang_class` | `lang_label` |
|---|---|---|
| `english_only` | `tag-en` | English only |
| `german_b1` | `tag-b1` | German B1 |
| `unknown` | `tag-unk` | Language n/a |
| `german_required` | `tag-req` | German required |

| `experience_level` value | `exp_class` | `exp_label` |
|---|---|---|
| `junior` | `tag-jr` | Junior |
| `internship` | `tag-intern` | Internship |
| `entry_level` | `tag-jr` | Entry level |
| `other` | `tag-unk` | – |

**`{logo_b64}` value:** Read from `logo.b64` in the workspace directory:
```bash
cat logo.b64
```
