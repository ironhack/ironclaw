# Google Ads Proto Enum Codes

When querying the Google Ads API via the Python client library, enum fields like `campaign.serving_status` return raw proto integer values rather than their human-readable names. This reference maps the common ones.

## campaign.serving_status (ServingStatusEnum)

| Code | Name | Meaning |
|------|------|---------|
| 1 | UNSPECIFIED | Not specified |
| 2 | SERVING | Campaign is actively serving |
| 3 | CAMPAIGN_GROUP_BUDGET_CONSTRAINED | Limited by shared budget |
| 4 | ENDED | Campaign end date has passed |
| 5 | PENDING | Not yet started |
| 6 | SUSPENDED | Manually paused or suspended |
| 7 | BUDGET_CONSTRAINED | Limited by daily budget |

**In sanity checks**: `serving_status != 2` on an ENABLED campaign = problem.

## campaign.status (CampaignStatusEnum)

| Code | Name |
|------|------|
| 1 | UNSPECIFIED |
| 2 | ENABLED |
| 3 | PAUSED |
| 4 | REMOVED |

## campaign.advertising_channel_type (AdvertisingChannelTypeEnum)

| Code | Name |
|------|------|
| 1 | UNSPECIFIED |
| 2 | SEARCH |
| 3 | DISPLAY |
| 4 | SHOPPING |
| 5 | HOTEL |
| 6 | VIDEO |
| 7 | MULTI_CHANNEL |
| 8 | LOCAL |
| 9 | SMART |
| 10 | PERFORMANCE_MAX |
| 11 | LOCAL_SERVICES |
| 14 | DISCOVERY |
| 15 | DEMAND_GEN |
| 16 | SEARCH_ADS_360 |
| 17 | DEMAND_GEN (legacy) |

## ad_group_ad.policy_summary.approval_status (PolicyApprovalStatusEnum)

| Code | Name | Sanity check? |
|------|------|---------------|
| 1 | UNSPECIFIED | Watch |
| 2 | UNKNOWN | Watch |
| 3 | APPROVED | 🟢 OK |
| 4 | APPROVED_LIMITED | 🟢 OK (limited by policy) |
| 5 | ELIGIBLE | 🟡 Eligible but not yet reviewed |
| 6 | UNDER_REVIEW | 🟡 Still in review |
| 7 | DISAPPROVED | 🔴 Problem — ad not serving |
| 8 | SITE_SUSPENDED | 🔴 Destination site suspended |

## ad_group_ad.policy_summary.review_status (PolicyReviewStatusEnum)

| Code | Name |
|------|------|
| 1 | UNSPECIFIED |
| 2 | UNKNOWN |
| 3 | REVIEWED |
| 4 | UNDER_REVIEW |
| 5 | ELIGIBLE_MAY_REVIEW |
