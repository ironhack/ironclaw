"""
report_s3.py - Shared S3 upload helper for Argos HTML reports.
"""
import os
import subprocess
import sys
from datetime import date

BUCKET = "ih-ironclaw"
REGION = os.getenv("AWS_DEFAULT_REGION", "eu-west-1")
BASE_PUBLIC = f"https://{BUCKET}.s3.{REGION}.amazonaws.com"
LOGO_PATH = "/home/openclaw/ironclaw-data/workspace-ironclaw-jobs/logo.b64"


def upload_html(html_content: str, filename: str) -> str:
    today = date.today().isoformat()
    dated_key = f"ironclaw/argos/{today}/{filename}"
    shared_key = f"ironclaw/argos/shared/{filename}"
    tmp = f"/tmp/argos_{filename}"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(html_content)
    for key in [dated_key, shared_key]:
        result = subprocess.run(
            ["aws", "s3", "cp", tmp, f"s3://{BUCKET}/{key}",
             "--region", REGION, "--content-type", "text/html"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"[S3 ERROR] {key}: {result.stderr}", file=sys.stderr)
            raise RuntimeError(f"S3 upload failed for {key}: {result.stderr}")
        print(f"[S3] Uploaded: s3://{BUCKET}/{key}", file=sys.stderr)
    return f"{BASE_PUBLIC}/{shared_key}"


def load_logo() -> str:
    with open(LOGO_PATH) as f:
        return f.read().strip()
