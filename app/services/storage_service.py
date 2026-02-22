"""S3 upload and signed URL generation for assets."""

import io
import uuid
from typing import BinaryIO, Optional

import boto3
from botocore.config import Config

from app.config import get_settings


def _client():
    settings = get_settings()
    kwargs = {
        "region_name": settings.s3_region,
        "aws_access_key_id": settings.aws_access_key_id or None,
        "aws_secret_access_key": settings.aws_secret_access_key or None,
        "config": Config(signature_version="s3v4"),
    }
    if settings.s3_endpoint_url:
        kwargs["endpoint_url"] = settings.s3_endpoint_url
    else:
        # Use regional endpoint so presigned URLs don't trigger 307 redirect;
        # following redirect changes Host and invalidates the signature (403).
        kwargs["endpoint_url"] = f"https://s3.{settings.s3_region}.amazonaws.com"
    return boto3.client("s3", **kwargs)


def upload_file(
    key: str,
    body: BinaryIO,
    content_type: str,
    bucket: Optional[str] = None,
) -> str:
    """
    Upload to S3; return public or path-style URL.
    Key should be e.g. workspaces/{workspace_id}/music/{asset_id}.mp3
    """
    settings = get_settings()
    bucket = bucket or settings.s3_bucket
    client = _client()
    client.upload_fileobj(
        body,
        bucket,
        key,
        ExtraArgs={"ContentType": content_type},
    )
    if settings.s3_endpoint_url:
        return f"{settings.s3_endpoint_url}/{bucket}/{key}"
    return f"https://{bucket}.s3.{settings.s3_region}.amazonaws.com/{key}"


def upload_bytes(
    key: str,
    data: bytes,
    content_type: str,
    bucket: Optional[str] = None,
) -> str:
    """Upload bytes to S3; return URL."""
    import io
    return upload_file(key, io.BytesIO(data), content_type, bucket=bucket)


def presigned_url(
    key: str,
    expiration: int = 3600,
    bucket: Optional[str] = None,
) -> str:
    """Generate a presigned GET URL for private object."""
    settings = get_settings()
    bucket = bucket or settings.s3_bucket
    client = _client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expiration,
    )


def get_download_url(url: str, expiration: int = 3600) -> str:
    """
    Resolve a stored object URL to a URL that can be GET'd (e.g. presigned for private S3).
    Use this whenever a URL will be fetched: backend download (render task) or API responses
    to the frontend (video preview, music playback, asset list). Leaves non-S3 URLs unchanged.
    """
    settings = get_settings()
    if not settings.aws_access_key_id or not settings.aws_secret_access_key:
        return url
    if settings.s3_endpoint_url:
        # Custom endpoint (e.g. MinIO): path-style like http://host/bucket/key
        base = f"{settings.s3_endpoint_url.rstrip('/')}/{settings.s3_bucket}/"
        if url.startswith(base):
            key = url[len(base):]
            return presigned_url(key, expiration=expiration)
        return url
    prefix = f"https://{settings.s3_bucket}.s3.{settings.s3_region}.amazonaws.com/"
    if url.startswith(prefix):
        key = url[len(prefix):]
        return presigned_url(key, expiration=expiration)
    return url


def music_upload_key(workspace_id: uuid.UUID, asset_id: uuid.UUID, ext: str) -> str:
    return f"workspaces/{workspace_id}/music/{asset_id}{ext}"


def voice_preview_key(workspace_id: uuid.UUID, voice_id: str) -> str:
    return f"workspaces/{workspace_id}/voices/preview_{voice_id}.mp3"
