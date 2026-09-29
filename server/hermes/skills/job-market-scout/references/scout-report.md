# Report Generation Script
# 
# Located at ~/.hermes/scripts/scout-report.py (not inside this skill directory).
# 
# Generates 13 HTML reports (1 general + 12 branded), uploads to S3 dated + shared folders.
# Script-only cron job (no_agent=True). No LLM cost. ~30s runtime.
#
# Key design decisions:
# - Monkey-patches generate_branded_report/generate_general_report to escape CSS braces
# - Uses aws CLI for S3 uploads (pre-authenticated via env/instance profile)
# - Always writes to BOTH dated folder AND shared folder
# - Shared folder URL is the stable student-facing link
#
# Cron job: 2a8f5a32731f, schedule: 0 14 * * 3 (Wed 16:00 CET)
