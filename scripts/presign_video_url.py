#!/usr/bin/env python3
"""
Print a presigned (viewable) URL for a private S3 video URL.

Raw S3 object URLs (e.g. from task results or DB) return 403 in the browser
because the bucket is private. This script converts a stored URL into a
temporary presigned URL you can open in a browser.

Usage:
  python3 scripts/presign_video_url.py "https://viral-video-som.s3.eu-west-1.amazonaws.com/workspaces/.../video.mp4"
  python3 scripts/presign_video_url.py  # then paste URL when prompted
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.services.storage_service import get_download_url

PREVIEW_URL_EXPIRY = 86400  # 24 hours


def main() -> None:
    if len(sys.argv) > 1:
        raw_url = sys.argv[1].strip()
    else:
        raw_url = input("Paste the raw S3 video URL: ").strip()
    if not raw_url:
        print("No URL provided.", file=sys.stderr)
        sys.exit(1)
    settings = get_settings()
    if not settings.aws_access_key_id or not settings.aws_secret_access_key:
        print("AWS credentials not set. Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY.", file=sys.stderr)
        sys.exit(1)
    signed = get_download_url(raw_url, expiration=PREVIEW_URL_EXPIRY)
    print(signed)


if __name__ == "__main__":
    main()
