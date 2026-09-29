"""
Job card HTML template for branded reports.
Variables: {title}, {company}, {location}, {url}, {lang_class}, {lang_label}, {exp_class}, {exp_label}, {summary_text}
"""
JOB_CARD_TEMPLATE = """<div class="job-card">
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
</div>"""

SUMMARY_PENDING = '<em style="color:#aaa">Summary available after next scrape.</em>'

LANG_MAP = {
    'english_only': ('tag-en', 'English only'),
    'german_b1': ('tag-b1', 'German B1'),
    'unknown': ('tag-unk', 'Language n/a'),
    'german_required': ('tag-req', 'German required'),
}

EXP_MAP = {
    'junior': ('tag-jr', 'Junior'),
    'internship': ('tag-intern', 'Internship'),
    'entry_level': ('tag-jr', 'Entry level'),
    'other': ('tag-unk', '&ndash;'),
    'senior': ('tag-unk', 'Senior'),
}

BOOTCAMPS = [
    ('ai-web-development', 'AI Web Development', 'Full-stack JavaScript development with React, Node.js, MongoDB, and AI-assisted workflows.'),
    ('data-analytics', 'Data Analytics', 'Python, SQL, Tableau, and Power BI for data-driven decision making.'),
    ('ai-consulting-integration', 'AI Consulting & Integration', 'AI workflow automation, RAG systems, and LLM orchestration for business consulting.'),
    ('ai-driven-ux-ui', 'AI-Driven UX/UI Design', 'User research, Figma prototyping, and accessible UI design with AI tools.'),
    ('data-science-ml', 'Data Science & Machine Learning', 'Python-based ML, deep learning, NLP, and generative AI model development.'),
    ('ai-engineering', 'AI Engineering', 'LLM fine-tuning, RAG architectures, and MLOps with PyTorch and AWS.'),
    ('cloud-engineering', 'Cloud Engineering', 'AWS infrastructure, Terraform IaC, Kubernetes, and DevSecOps.'),
    ('data-engineering', 'Data Engineering', 'ETL pipelines, Apache Airflow, Kafka, and cloud data warehousing.'),
    ('ai-driven-marketing', 'AI-Driven Marketing', 'Digital marketing strategy, GA4, paid media, and AI-powered automation.'),
    ('cybersecurity', 'Cybersecurity', 'Network defense, penetration testing, SIEM, and incident response.'),
    ('ai-product-management', 'AI Product Management', 'Agile product management, user research, and AI-integrated prototyping.'),
    ('devops', 'DevOps & Cloud Computing', 'Linux, Docker, Kubernetes, GitHub Actions CI/CD, and multi-cloud.'),
]

def generate_branded_report(slug, display_name, description, rows, date, logo_b64):
    """Generate branded HTML for one bootcamp."""
    cards = []
    for row in rows:
        lang_class, lang_label = LANG_MAP.get(row[4], ('tag-unk', 'Language n/a'))
        exp_class, exp_label = EXP_MAP.get(row[5], ('tag-unk', '&ndash;'))
        summary = row[6] if row[6] else SUMMARY_PENDING
        cards.append(JOB_CARD_TEMPLATE.format(
            title=row[0], company=row[1], location=row[2], url=row[3],
            lang_class=lang_class, lang_label=lang_label,
            exp_class=exp_class, exp_label=exp_label,
            summary_text=summary,
        ))
    branded_template = open('/home/openclaw/.hermes/skills/ironhack/job-market-scout/templates/report-branded.html').read()
    return branded_template.format(
        logo_b64=logo_b64, date=date,
        bootcamp_name=display_name, bootcamp_description=description,
        active_count=len(rows), job_cards='\n'.join(cards),
    )

def generate_general_report(all_rows, date):
    """Generate general HTML with all bootcamps in table format."""
    template = open('/home/openclaw/.hermes/skills/ironhack/job-market-scout/templates/report-general.html').read()
    sections = []
    for slug, display_name, desc in BOOTCAMPS:
        rows = [r for r in all_rows if r[0] == slug]  # r[0] is bootcamp
        if not rows: continue
        rows_html = []
        for r in rows[:10]:
            lang_class, lang_label = LANG_MAP.get(r[4], ('tag-unk', 'Language n/a'))
            exp_class, exp_label = EXP_MAP.get(r[5], ('tag-unk', '&ndash;'))
            rows_html.append(f'<tr><td>{r[1]}</td><td>{r[2]}</td><td>{r[3]}</td><td><span class="{lang_class}">{lang_label}</span></td><td>{exp_label}</td><td><a href="{r[6]}">View</a></td></tr>')
        sections.append(f'<h2>{display_name}</h2><p>{desc}</p><table><tr><th>Job Title</th><th>Company</th><th>Location</th><th>Language</th><th>Level</th><th>URL</th></tr>{"".join(rows_html)}</table>')
    return template.format(date=date, sections='\n'.join(sections))
