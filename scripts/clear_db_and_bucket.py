#!/usr/bin/env python3
"""
Clear database (truncate all tables) and S3 bucket (delete all objects).

Usage:
  python scripts/clear_db_and_bucket.py [--db-only] [--bucket-only] [--yes]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root so app imports work
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def clear_db() -> None:
    from sqlalchemy import create_engine, text
    from app.config import get_settings

    settings = get_settings()
    engine = create_engine(settings.database_url)

    with engine.connect() as conn:
        conn.execute(text("TRUNCATE users, plans RESTART IDENTITY CASCADE"))
        conn.commit()
    print("Database cleared.")


def clear_bucket() -> None:
    from app.config import get_settings
    from app.services.storage_service import _client

    settings = get_settings()
    if not settings.aws_access_key_id or not settings.aws_secret_access_key:
        print("Skipping bucket: AWS credentials not set (aws_access_key_id, aws_secret_access_key).")
        return

    bucket = settings.s3_bucket
    client = _client()
    paginator = client.get_paginator("list_objects_v2")
    deleted = 0
    for page in paginator.paginate(Bucket=bucket):
        objects = page.get("Contents") or []
        if not objects:
            continue
        keys = [{"Key": obj["Key"]} for obj in objects]
        client.delete_objects(Bucket=bucket, Delete={"Objects": keys})
        deleted += len(keys)
    print(f"S3 bucket '{bucket}' cleared ({deleted} objects deleted).")


def main() -> int:
    p = argparse.ArgumentParser(description="Clear DB and/or S3 bucket")
    p.add_argument("--db-only", action="store_true", help="Only clear database")
    p.add_argument("--bucket-only", action="store_true", help="Only clear S3 bucket")
    p.add_argument("--yes", "-y", action="store_true", help="Skip confirmation")
    args = p.parse_args()

    do_db = not args.bucket_only
    do_bucket = not args.db_only

    if not args.yes:
        msg = "This will permanently delete "
        if do_db and do_bucket:
            msg += "all database data and all S3 bucket objects"
        elif do_db:
            msg += "all database data"
        else:
            msg += "all S3 bucket objects"
        msg += ". Continue? [y/N] "
        if input(msg).lower() != "y":
            print("Aborted.")
            return 1

    if do_db:
        clear_db()
    if do_bucket:
        clear_bucket()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
