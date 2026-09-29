#!/usr/bin/env python3
"""Argos Daily Sanity Check — Google Ads health across all accounts."""

import json
import os
import sys
import tempfile
from datetime import date

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

# --- Auth ---
service_account_info = json.loads(os.environ["GOOGLE_APPLICATION_CREDENTIALS_JSON"])
key_file = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
json.dump(service_account_info, key_file)
key_file.close()

client = GoogleAdsClient.load_from_dict({
    "developer_token": os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"],
    "login_customer_id": os.environ["GOOGLE_ADS_LOGIN_CUSTOMER_ID"],
    "use_proto_plus": True,
    "json_key_file_path": key_file.name,
})

ga_service = client.get_service("GoogleAdsService")

CUSTOMER_IDS = [cid.strip() for cid in os.environ["GADS_CUSTOMER_ID"].split(",")]

# --- Queries ---
BUDGET_QUERY = """
    SELECT
      campaign.id,
      campaign.name,
      campaign.status,
      campaign_budget.amount_micros,
      metrics.cost_micros,
      metrics.conversions,
      metrics.conversions_value,
      campaign.serving_status
    FROM campaign
    WHERE campaign.status = 'ENABLED'
      AND segments.date DURING YESTERDAY
"""

AD_STATUS_QUERY = """
    SELECT
      campaign.id,
      campaign.name,
      ad_group.id,
      ad_group.name,
      ad_group_ad.ad.id,
      ad_group_ad.status,
      ad_group_ad.policy_summary.approval_status,
      ad_group_ad.policy_summary.review_status
    FROM ad_group_ad
    WHERE campaign.status = 'ENABLED'
      AND ad_group.status = 'ENABLED'
      AND ad_group_ad.status = 'ENABLED'
"""

SERVING_QUERY = """
    SELECT
      campaign.id,
      campaign.name,
      campaign.status,
      campaign.serving_status,
      campaign.advertising_channel_type,
      metrics.impressions,
      metrics.clicks,
      metrics.cost_micros
    FROM campaign
    WHERE campaign.status != 'REMOVED'
      AND segments.date DURING LAST_7_DAYS
"""

# 7-day daily spend per campaign — used to detect spend trends
TREND_QUERY = """
    SELECT
      campaign.id,
      segments.date,
      metrics.cost_micros
    FROM campaign
    WHERE campaign.status = 'ENABLED'
      AND segments.date DURING LAST_7_DAYS
"""


def run_query(customer_id, query):
    """Run a GAQL query and return rows, catching per-account errors."""
    try:
        stream = ga_service.search_stream(customer_id=customer_id, query=query)
        rows = []
        for batch in stream:
            for row in batch.results:
                rows.append(row)
        return rows
    except GoogleAdsException as ex:
        return {"error": str(ex), "request_id": ex.request_id}


def micros_to_float(micros):
    """Convert micros to display currency."""
    if micros is None or micros == 0:
        return 0.0
    return micros / 1_000_000


# --- Run all queries ---
results = {
    "date": str(date.today()),
    "accounts": {},
    "issues_found": False,
}

for cid in CUSTOMER_IDS:
    acct = {"budget_constrained": [], "ad_issues": [], "not_serving": []}

    # 1. Budget check
    budget_rows = run_query(cid, BUDGET_QUERY)
    if isinstance(budget_rows, dict):
        acct["error"] = budget_rows
        results["issues_found"] = True
        results["accounts"][cid] = acct
        continue

    for row in budget_rows:
        camp = row.campaign
        metrics = row.metrics
        budget_amount = getattr(row.campaign_budget, 'amount_micros', 0) or 0
        budget = micros_to_float(budget_amount)
        spent = micros_to_float(metrics.cost_micros)
        pct = (spent / budget * 100) if budget > 0 else 0
        conversions = round(getattr(metrics, 'conversions', 0) or 0, 2)
        conv_value = float(getattr(metrics, 'conversions_value', 0) or 0)
        cpa = (spent / conversions) if conversions > 0 else 0
        roas = (conv_value / spent) if spent > 0 else 0
        serving = str(row.campaign.serving_status)

        # Only include SERVING campaigns in budget analysis.
        # ENDED campaigns (serving_status=4) have 0 spend and are dead — they
        # belong in "not_serving", not here. Skip them.
        if serving != "2":
            continue

        # Classify severity
        if pct >= 95:
            severity = "critical"
        elif pct >= 75:
            severity = "warning"
        else:
            severity = "info"

        acct["budget_constrained"].append({
            "campaign_id": camp.id,
            "campaign_name": camp.name,
            "budget": round(budget, 2),
            "spent_yesterday": round(spent, 2),
            "pct_consumed": round(pct, 1),
            "conversions": conversions,
            "cpa": round(cpa, 2),
            "roas": round(roas, 2),
            "serving_status": serving,
            "severity": severity,
        })

    # 1b. Compute 7-day spend trend for budget campaigns
    trend_rows = run_query(cid, TREND_QUERY)
    if not isinstance(trend_rows, dict):
        # Aggregate daily spend per campaign
        from collections import defaultdict
        camp_daily_spend = defaultdict(lambda: defaultdict(float))
        for row in trend_rows:
            cid_key = str(row.campaign.id)
            day = row.segments.date
            spend = micros_to_float(row.metrics.cost_micros)
            camp_daily_spend[cid_key][day] = spend

        today_str = str(date.today())
        yesterday_str = str(date.today())
        # Use the latest date in the data as "yesterday" (GAQL DURING LAST_7_DAYS includes yesterday)
        # Compute avg spend excluding the most recent day
        for entry in acct["budget_constrained"]:
            daily = camp_daily_spend.get(str(entry["campaign_id"]), {})
            if not daily:
                entry["trend"] = "new"
                entry["avg_spend_7d"] = 0.0
                continue
            days_sorted = sorted(daily.keys())
            yesterday_spend = daily.get(days_sorted[-1], 0) if days_sorted else 0
            prev_days = [daily[d] for d in days_sorted[:-1]] if len(days_sorted) > 1 else []
            avg_prev = sum(prev_days) / len(prev_days) if prev_days else yesterday_spend

            entry["avg_spend_7d"] = round(avg_prev, 2)

            if avg_prev == 0:
                if yesterday_spend > 0:
                    entry["trend"] = "up"
                else:
                    entry["trend"] = "flat"
            else:
                ratio = yesterday_spend / avg_prev
                if ratio > 1.2:
                    entry["trend"] = "up"
                elif ratio < 0.8:
                    entry["trend"] = "down"
                else:
                    entry["trend"] = "flat"

    # 2. Ad approval check
    ad_rows = run_query(cid, AD_STATUS_QUERY)
    if isinstance(ad_rows, dict):
        acct["ad_query_error"] = ad_rows
    else:
        for row in ad_rows:
            approval = row.ad_group_ad.policy_summary.approval_status
            if approval.name != "APPROVED" and approval.name != "APPROVED_LIMITED":
                acct["ad_issues"].append({
                    "campaign_id": row.campaign.id,
                    "campaign_name": row.campaign.name,
                    "ad_group_id": row.ad_group.id,
                    "ad_group_name": row.ad_group.name,
                    "ad_id": row.ad_group_ad.ad.id,
                    "ad_status": row.ad_group_ad.status.name,
                    "approval_status": approval.name,
                    "review_status": row.ad_group_ad.policy_summary.review_status.name,
                })

    # 3. Campaigns not serving
    serving_rows = run_query(cid, SERVING_QUERY)
    if isinstance(serving_rows, dict):
        acct["serving_query_error"] = serving_rows
    else:
        for row in serving_rows:
            camp = row.campaign
            metrics = row.metrics
            serving_name = camp.serving_status.name if hasattr(camp.serving_status, 'name') else str(camp.serving_status)
            if serving_name != "SERVING" and camp.status.name == "ENABLED":
                acct["not_serving"].append({
                    "campaign_id": camp.id,
                    "campaign_name": camp.name,
                    "status": camp.status.name,
                    "serving_status": serving_name,
                    "channel_type": str(camp.advertising_channel_type),
                    "impressions_7d": metrics.impressions,
                    "clicks_7d": metrics.clicks,
                    "cost_7d": round(micros_to_float(metrics.cost_micros), 2),
                })

    if acct["budget_constrained"] or acct["ad_issues"] or acct["not_serving"]:
        results["issues_found"] = True

    results["accounts"][cid] = acct


# --- Output (v2, 2026-09-29): full dataset to a file, compact classified summary to stdout for the agent ---
OUT = "/tmp/argos_sanity_data.json"
if "--out" in sys.argv:
    OUT = sys.argv[sys.argv.index("--out") + 1]
with open(OUT, "w") as f:
    json.dump(results, f, indent=2, default=str)
if "--full-stdout" in sys.argv:
    print(json.dumps(results, indent=2, default=str))
else:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from argos_sanity_slack import summarize, compact_summary
    _data = json.loads(json.dumps(results, default=str))
    print(json.dumps({"data_file": OUT, **compact_summary(summarize(_data))}, indent=1, ensure_ascii=False))
