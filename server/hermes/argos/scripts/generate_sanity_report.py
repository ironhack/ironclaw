"""
generate_sanity_report.py — Generates a branded HTML sanity report with
severity-tiered issues, hypotheses, and actionable takeaways.

Usage: python3 generate_sanity_report.py < sanity_data.json
  OR:  python3 generate_sanity_report.py sanity_data.json
"""
import json
import os
import sys
from datetime import date
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from report_s3 import upload_html, load_logo

TEMPLATE_PATH = (
    "/home/openclaw/.hermes/profiles/argos/skills/marketing/"
    "argos-reports/templates/sanity-report.html"
)

# ── Hypothesis templates ──────────────────────────────────────────────
# Single-campaign templates (used when len(entries) == 1):
#   {pct}, {trend_label}, {avg_spend}, {cpa}, {roas}, {roas_verdict}
# Group templates (used when len(entries) > 1):
#   {count}, {trend_summary}, {spend_range}, {cpa_range}, {roas_range}
#   {roas_best}, {roas_worst}

def roas_verdict(roas):
    if roas <= 0:
        return "no conversions"
    if roas < 1:
        return "losing money"
    if roas < 2:
        return "marginal"
    return "healthy"

CRITICAL_SINGLE = (
    "This campaign hit {pct} of its daily budget yesterday with spend "
    "{trend_label} vs. the 7-day average (€{avg_spend}/day). "
    "CPA was €{cpa} and ROAS was {roas}x — this is <strong>{roas_verdict}</strong>. "
    "If this efficiency is acceptable, raise the budget to stop losing "
    "impression share. If not, the budget cap may actually be protecting you."
)

CRITICAL_GROUP = (
    "{count} campaigns exceeded their daily budgets yesterday. "
    "Spend trends: {trend_summary}. "
    "CPA ranges from €{cpa_range} with ROAS from {roas_range}x. "
    "Best performer: {roas_best}x ROAS. Worst: {roas_worst}x ({roas_verdict}). "
    "For campaigns with healthy ROAS, raise budgets to recover impression share. "
    "For the ones losing money, the budget cap is doing its job."
)

WARNING_GROUP = (
    "{count} campaigns approaching their daily caps ({pct_range} consumed). "
    "Spend trends: {trend_summary}. "
    "CPA: €{cpa_range}. ROAS: {roas_range}x. "
    "If the higher-ROAS campaigns are trending up, raise their budgets before "
    "they hit the cap and lose impression share."
)

INFO_SINGLE = (
    "At {pct} of daily budget with a {trend_label} trend (7-day avg: €{avg_spend}/day). "
    "Yesterday's CPA was €{cpa} at {roas}x ROAS. No immediate concern unless "
    "spend starts trending up toward the cap."
)

INFO_GROUP = (
    "{count} campaigns are well within their daily budgets ({pct_range} consumed). "
    "Spend trends: {trend_summary}. "
    "CPA: €{cpa_range}. ROAS: {roas_range}x. No immediate concerns — "
    "this section is collapsed because nothing needs attention."
)

NOT_SERVING_HYPOTHESIS = (
    "These campaigns are ENABLED but have ENDED serving status with 0 impressions "
    "in the last 7 days. Most likely they are ended experiments, A/B test losers, "
    "or seasonal campaigns that weren't cleaned up. Action: pause or remove them "
    "to keep the account tidy and avoid confusion in reporting."
)

AD_ISSUE_HYPOTHESIS = {
    "DISAPPROVED": (
        "Ad was rejected by Google's policy review. Check the policy violation "
        "details in Google Ads and either fix the ad or appeal."
    ),
    "UNDER_REVIEW": (
        "Ad is still under policy review. If it's been stuck for 24+ hours, "
        "contact Google Ads support."
    ),
    "ELIGIBLE": (
        "Ad is eligible for serving but hasn't been reviewed yet. Usually resolves "
        "within a few hours. If it's been stuck for more than a day, something is wrong."
    ),
    "SITE_SUSPENDED": (
        "The destination website has been suspended. This is serious — check the "
        "landing page immediately and resolve the suspension in Google Ads."
    ),
}


# ── Formatters ────────────────────────────────────────────────────────
def fmt_money(v):
    if v is None or v == 0:
        return "—"
    return f"€{v:,.2f}"


def severity_label(sev):
    return {"critical": "Critical", "warning": "Warning", "info": "Info"}.get(sev, sev)


def severity_icon(sev):
    return {"critical": "red_circle", "warning": "large_orange_diamond", "info": "small_blue_diamond"}.get(sev, "black_circle")


def severity_class(sev):
    return {"critical": "sev-critical", "warning": "sev-warning", "info": "sev-info"}.get(sev, "")


def ad_hypothesis(status):
    return AD_ISSUE_HYPOTHESIS.get(status, f"Ad has status '{status}'. Review in Google Ads for details.")


# ── Data analysis ─────────────────────────────────────────────────────
def analyze_data(data):
    """Extract categorized issues and generate takeaways."""
    accounts = data.get("accounts", {})
    
    budget_critical = []
    budget_warning = []
    budget_info = []
    not_serving = []
    ad_issues = []
    
    total_overspend = 0.0
    campaigns_over_budget = 0
    ended_campaigns_count = 0
    active_campaigns_over_75 = 0
    
    for cid, acct in accounts.items():
        # Budget constrained — already filtered to SERVING only by sanity_check.py
        for b in acct.get("budget_constrained", []):
            entry = {**b, "account_id": cid}
            sev = b.get("severity", "info")
            if sev == "critical":
                budget_critical.append(entry)
            elif sev == "warning":
                budget_warning.append(entry)
            else:
                budget_info.append(entry)
            
            pct = b.get("pct_consumed", 0)
            if pct > 100:
                total_overspend += (b.get("spent_yesterday", 0) - b.get("budget", 0))
                campaigns_over_budget += 1
            if pct >= 75:
                active_campaigns_over_75 += 1
        
        # Not serving
        for ns in acct.get("not_serving", []):
            entry = {**ns, "account_id": cid}
            not_serving.append(entry)
            ended_campaigns_count += 1
        
        # Ad issues
        for ad in acct.get("ad_issues", []):
            entry = {**ad, "account_id": cid}
            ad_issues.append(entry)
    
    # Build takeaways
    takeaways = []
    
    if campaigns_over_budget > 0:
        takeaways.append({
            "icon": "📈",
            "text": (
                f"**{campaigns_over_budget} campaign(s) exceeded their daily budget yesterday** "
                f"(total overspend: {fmt_money(total_overspend)}). "
                f"These campaigns are losing impression share. "
                f"If CPA/ROAS is healthy, consider raising their daily budgets."
            )
        })
    
    if active_campaigns_over_75 > 0:
        takeaways.append({
            "icon": "💸",
            "text": (
                f"**{active_campaigns_over_75} campaign(s) are at 75%+ of daily budget** — "
                f"monitor for upward trends. Raising budgets on the top performers "
                f"could unlock additional volume at efficient CPAs."
            )
        })
    
    if ended_campaigns_count > 0:
        # Group by pattern
        patterns = defaultdict(list)
        for ns in not_serving:
            name = ns.get("campaign_name", "")
            if "experiment" in name.lower() or "tp" in name.lower():
                patterns["experiment"].append(name)
            elif "maxconv" in name.lower():
                patterns["test_variant"].append(name)
            else:
                patterns["other"].append(name)
        
        pattern_desc = []
        if patterns.get("experiment"):
            pattern_desc.append(f"{len(patterns['experiment'])}x ended experiments")
        if patterns.get("test_variant"):
            pattern_desc.append(f"{len(patterns['test_variant'])}x test variants")
        if patterns.get("other"):
            pattern_desc.append(f"{len(patterns['other'])}x other")
        
        pattern_str = ", ".join(pattern_desc)
        takeaways.append({
            "icon": "🗑️",
            "text": (
                f"**{ended_campaigns_count} ENABLED-but-ENDED campaigns** found "
                f"({pattern_str}). They have 0 impressions in 7 days — "
                f"these are dead weight. Pause or remove them to keep the account clean."
            )
        })
    
    if ad_issues:
        disapproved = [a for a in ad_issues if a.get("approval_status") == "DISAPPROVED"]
        if disapproved:
            takeaways.append({
                "icon": "🚫",
                "text": (
                    f"**{len(disapproved)} disapproved ad(s)** — these are not serving. "
                    f"Fix the policy violations or appeal in Google Ads."
                )
            })
    
    # All clear
    if not takeaways:
        takeaways.append({
            "icon": "✅",
            "text": "**All clear.** No issues detected — campaigns are serving, budgets are healthy, and all ads are approved."
        })
    
    return {
        "budget_critical": budget_critical,
        "budget_warning": budget_warning,
        "budget_info": budget_info,
        "not_serving": not_serving,
        "ad_issues": ad_issues,
        "takeaways": takeaways,
        "counts": {
            "critical": len(budget_critical),
            "warning": len(budget_warning),
            "info": len(budget_info),
            "not_serving": len(not_serving),
            "ad_issues": len(ad_issues),
        }
    }


# ── HTML builders ─────────────────────────────────────────────────────
def build_takeaways(takeaways):
    """Build the takeaways summary box."""
    items = []
    for t in takeaways:
        items.append(f'''<div class="takeaway-row">
          <span class="takeaway-icon">{t["icon"]}</span>
          <span class="takeaway-text">{t["text"]}</span>
        </div>''')
    return f'''<div class="takeaways-box">
      <div class="takeaways-title">&#128269; 30-Second Takeaway</div>
      {"".join(items)}
    </div>'''


def build_budget_section(entries, severity, collapsed=False):
    """Build a budget issue section with hypothesis and trend data."""
    if not entries:
        return ""
    
    label = severity_label(severity)
    cls = severity_class(severity)
    
    # Compute group-level trend summary
    trend_counts = {"up": 0, "down": 0, "flat": 0, "new": 0}
    for e in entries:
        t = e.get("trend", "flat")
        trend_counts[t] = trend_counts.get(t, 0) + 1
    trend_parts = []
    if trend_counts["up"]: trend_parts.append(f"{trend_counts['up']} rising")
    if trend_counts["flat"]: trend_parts.append(f"{trend_counts['flat']} stable")
    if trend_counts["down"]: trend_parts.append(f"{trend_counts['down']} falling")
    if trend_counts["new"]: trend_parts.append(f"{trend_counts['new']} new")
    trend_summary = ", ".join(trend_parts)
    
    trend_labels = {"up": "rising", "down": "falling", "flat": "stable", "new": "new"}
    trend_colors = {"up": "trend-up", "down": "trend-down", "flat": "trend-flat", "new": "trend-new"}
    
    # Compute ranges for group hypothesis
    pcts = [e.get("pct_consumed", 0) for e in entries]
    cpas = [e.get("cpa", 0) for e in entries if e.get("cpa", 0) > 0]
    roass = [e.get("roas", 0) for e in entries if e.get("roas", 0) > 0]
    
    def fmt_range(vals, fmt_fn):
        if not vals:
            return "—"
        lo, hi = min(vals), max(vals)
        if lo == hi:
            return fmt_fn(lo)
        return f"{fmt_fn(lo)}–{fmt_fn(hi)}"
    
    pct_range_str = f"{min(pcts):.0f}%–{max(pcts):.0f}%"
    cpa_range_str = fmt_range(cpas, lambda v: f"{v:,.0f}")
    roas_range_str = fmt_range(roass, lambda v: f"{v:.1f}")
    roas_best = max(roass) if roass else 0
    roas_worst = min(roass) if roass else 0
    worst_verdict = roas_verdict(roas_worst)
    
    if len(entries) == 1:
        e = entries[0]
        t = e.get("trend", "flat")
        hypothesis = (CRITICAL_SINGLE if severity == "critical" else INFO_SINGLE).format(
            pct=f"{e.get('pct_consumed', 0):.1f}%",
            trend_label=trend_labels.get(t, "stable"),
            avg_spend=f"{e.get('avg_spend_7d', 0):,.0f}",
            cpa=f"{e.get('cpa', 0):,.0f}",
            roas=f"{e.get('roas', 0):.1f}",
            roas_verdict=roas_verdict(e.get("roas", 0)),
        )
    else:
        template = CRITICAL_GROUP if severity == "critical" else (WARNING_GROUP if severity == "warning" else INFO_GROUP)
        hypothesis = template.format(
            count=len(entries),
            pct_range=pct_range_str,
            trend_summary=trend_summary,
            cpa_range=cpa_range_str,
            roas_range=roas_range_str,
            roas_best=f"{roas_best:.1f}",
            roas_worst=f"{roas_worst:.1f}",
            roas_verdict=worst_verdict,
        )
    
    collapsed_class = " collapsed" if collapsed else ""
    arrow = "&#9660;" if not collapsed else "&#9654;"
    
    # Build table rows
    rows = []
    for e in entries:
        pct = e.get("pct_consumed", 0)
        t = e.get("trend", "flat")
        t_label = trend_labels.get(t, t)
        t_cls = trend_colors.get(t, "trend-flat")
        avg = e.get("avg_spend_7d", 0)
        cpa = e.get("cpa", 0)
        roas = e.get("roas", 0)
        rows.append(f'''<tr>
          <td>{e.get("campaign_name", "?")}</td>
          <td class="num">{fmt_money(e.get("budget"))}</td>
          <td class="num">{fmt_money(e.get("spent_yesterday"))}</td>
          <td class="num"><span class="pct-badge pct-{severity}">{pct:.1f}%</span></td>
          <td class="num">{fmt_money(avg)}</td>
          <td class="num"><span class="trend-badge {t_cls}">{t_label}</span></td>
          <td class="num">{fmt_money(cpa)}</td>
          <td class="num">{roas:.2f}x</td>
        </tr>''')
    
    return f'''<div class="issue-section">
      <div class="issue-section-header {cls}" onclick="toggleSection(this)">
        <span>{arrow} {label} — Budget ({len(entries)} campaign(s))</span>
      </div>
      <div class="issue-section-body{collapsed_class}">
        <div class="hypothesis-box">
          <strong>&#128161; What this means:</strong> {hypothesis}
        </div>
        <div class="table-wrap"><table>
          <thead><tr>
            <th>Campaign</th>
            <th class="num">Daily Budget</th>
            <th class="num">Spent Yesterday</th>
            <th class="num">% Consumed</th>
            <th class="num">7d Avg Spend</th>
            <th class="num">Trend</th>
            <th class="num">CPA</th>
            <th class="num">ROAS</th>
          </tr></thead><tbody>
          {"".join(rows)}
        </tbody></table></div>
      </div>
    </div>'''


def build_not_serving_section(entries):
    """Build not-serving section with pattern analysis."""
    if not entries:
        return ""
    
    # Group by pattern
    patterns = defaultdict(list)
    for e in entries:
        name = e.get("campaign_name", "")
        if "experiment" in name.lower() or "tp" in name.lower():
            patterns["Ended experiments / A/B tests"].append(e)
        elif "maxconv" in name.lower():
            patterns["Test variants (MaxConv, etc.)"].append(e)
        else:
            patterns["Other ended campaigns"].append(e)
    
    sections = []
    for pattern_name, group in sorted(patterns.items()):
        rows = []
        for e in group:
            rows.append(f'''<tr>
              <td>{e.get("campaign_name", "?")}</td>
              <td class="num">{e.get("impressions_7d", 0):,}</td>
              <td class="num">{e.get("clicks_7d", 0):,}</td>
              <td class="num">{fmt_money(e.get("cost_7d"))}</td>
              <td class="num"><span class="tag tag-err">ENDED</span></td>
            </tr>''')
        sections.append(f'''<p class="pattern-label"><strong>{pattern_name}</strong> ({len(group)}x)</p>
        <div class="table-wrap"><table>
          <thead><tr>
            <th>Campaign</th>
            <th class="num">Impr. (7d)</th>
            <th class="num">Clicks (7d)</th>
            <th class="num">Cost (7d)</th>
            <th class="num">Status</th>
          </tr></thead><tbody>
          {"".join(rows)}
        </tbody></table></div>''')
    
    return f'''<div class="issue-section">
      <div class="issue-section-header sev-notserving" onclick="toggleSection(this)">
        <span>&#9660; Not Serving — ENABLED but ENDED ({len(entries)} campaign(s))</span>
      </div>
      <div class="issue-section-body">
        <div class="hypothesis-box">
          <strong>&#128161; What this means:</strong> {NOT_SERVING_HYPOTHESIS}
        </div>
        {"".join(sections)}
      </div>
    </div>'''


def build_ad_issues_section(entries):
    """Build ad policy issues section."""
    if not entries:
        return ""
    
    rows = []
    for e in entries:
        status = e.get("approval_status", "?")
        rows.append(f'''<tr>
          <td>{e.get("campaign_name", "?")}</td>
          <td>{e.get("ad_group_name", "?")}</td>
          <td><span class="tag tag-err">{status}</span></td>
          <td>{e.get("review_status", "?")}</td>
        </tr>''')
    
    # Get hypothesis from first entry's status
    first_status = entries[0].get("approval_status", "")
    hypothesis = ad_hypothesis(first_status)
    
    return f'''<div class="issue-section">
      <div class="issue-section-header sev-adissues" onclick="toggleSection(this)">
        <span>&#9660; Ad Policy Issues ({len(entries)} ad(s))</span>
      </div>
      <div class="issue-section-body">
        <div class="hypothesis-box">
          <strong>&#128161; What this means:</strong> {hypothesis}
        </div>
        <div class="table-wrap"><table>
          <thead><tr>
            <th>Campaign</th>
            <th>Ad Group</th>
            <th>Approval</th>
            <th>Review Status</th>
          </tr></thead><tbody>
          {"".join(rows)}
        </tbody></table></div>
      </div>
    </div>'''


def build_status_badges(counts):
    """Build status badge row at top."""
    total_issues = sum(counts.values())
    
    def badge(label, value, cls):
        return f'<div class="status-badge {cls}">{label}<br><span style="font-size:22px;">{value}</span></div>'
    
    badges = []
    if counts["critical"] > 0:
        badges.append(badge("Critical budget", counts["critical"], "status-error"))
    if counts["warning"] > 0:
        badges.append(badge("Budget warnings", counts["warning"], "status-warn"))
    if counts["not_serving"] > 0:
        badges.append(badge("Not serving", counts["not_serving"], "status-warn"))
    if counts["ad_issues"] > 0:
        badges.append(badge("Ad issues", counts["ad_issues"], "status-error"))
    
    if total_issues == 0:
        badges.append(badge("All clear", 0, "status-ok"))
    
    badges.append(badge("Info items", counts["info"], "status-neutral"))
    
    return "\n".join(badges)


# ── Main generator ────────────────────────────────────────────────────
def generate(data: dict) -> str:
    logo = load_logo()
    today = data.get("date", date.today().isoformat())
    
    analysis = analyze_data(data)
    
    status_badges = build_status_badges(analysis["counts"])
    takeaways_html = build_takeaways(analysis["takeaways"])
    
    # Build issue sections in priority order
    sections = []
    
    # Critical budget issues (always expanded)
    sections.append(build_budget_section(analysis["budget_critical"], "critical"))
    
    # Warning budget issues
    sections.append(build_budget_section(analysis["budget_warning"], "warning"))
    
    # Not serving
    sections.append(build_not_serving_section(analysis["not_serving"]))
    
    # Ad issues
    sections.append(build_ad_issues_section(analysis["ad_issues"]))
    
    # Info budget items (collapsed by default)
    sections.append(build_budget_section(analysis["budget_info"], "info", collapsed=True))
    
    issues_html = "\n".join(s for s in sections if s)
    
    if not issues_html:
        issues_html = '<div class="all-clear-box">&#10003; All campaigns are healthy — no issues detected</div>'
    
    with open(TEMPLATE_PATH) as f:
        template = f.read()
    
    return template.format(
        logo_b64=logo,
        date=today,
        status_badges=status_badges,
        takeaways_html=takeaways_html,
        issues_html=issues_html,
    )


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Argos daily sanity: HTML report (+ Slack post via argos_sanity_slack)")
    ap.add_argument("data", nargs="?", help="sanity_check.py dataset (default: stdin)")
    ap.add_argument("--narrative", help="agent narrative JSON (headline / findings / actions / notes)")
    ap.add_argument("--post", action="store_true", help="post the Block Kit message + thread")
    ap.add_argument("--to", help="preview target (user or channel id); state is not updated")
    ap.add_argument("--preview", action="store_true", help="upload as sanity-preview.html instead of sanity.html")
    ap.add_argument("--local", help="write the HTML to this path instead of uploading")
    ap.add_argument("--blocks-out", help="also dump the Slack blocks JSON here")
    a = ap.parse_args()
    if a.data:
        with open(a.data) as f:
            data = json.load(f)
    else:
        data = json.load(sys.stdin)

    html = generate(data)
    if a.local:
        with open(a.local, "w") as f:
            f.write(html)
        url = a.local
    else:
        url = upload_html(html, "sanity-preview.html" if a.preview else "sanity.html")
    print(url)

    if a.post or a.narrative:
        from argos_sanity_slack import summarize, post_report, render_text, CHANNEL, REPORT_URL
        N = {}
        if a.narrative:
            with open(a.narrative) as f:
                N = json.load(f)
        S = summarize(data)
        link = url if url.startswith("http") else REPORT_URL
        if a.post:
            ts = post_report(S, N, link, channel=a.to or CHANNEL, blocks_out=a.blocks_out, update_state=not a.to)
            print(f"SLACK_POSTED channel={a.to or CHANNEL} ts={ts}")
        else:
            print(render_text(S, N, link))


if __name__ == "__main__":
    main()
