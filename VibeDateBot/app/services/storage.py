from __future__ import annotations

import io
import logging
from datetime import timedelta
from uuid import uuid4

from minio import Minio
from minio.error import S3Error

from app.config import load_settings

logger = logging.getLogger(__name__)


def _client() -> Minio:
    settings = load_settings()
    endpoint = settings.minio_endpoint.replace("http://", "").replace("https://", "")
    secure = settings.minio_endpoint.startswith("https://")
    return Minio(
        endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=secure,
    )


def ensure_bucket() -> None:
    settings = load_settings()
    client = _client()
    if not client.bucket_exists(settings.minio_bucket):
        client.make_bucket(settings.minio_bucket)
        logger.info("MinIO bucket created: %s", settings.minio_bucket)


def upload_profile_photo(profile_id: int, data: bytes, content_type: str = "image/jpeg") -> str:
    """Upload bytes to MinIO; returns object key (stored in photos.s3_key)."""
    settings = load_settings()
    ensure_bucket()
    key = f"profiles/{profile_id}/{uuid4().hex}.jpg"
    client = _client()
    client.put_object(
        settings.minio_bucket,
        key,
        io.BytesIO(data),
        length=len(data),
        content_type=content_type,
    )
    return key


def download_profile_photo(s3_key: str) -> bytes | None:
    settings = load_settings()
    client = _client()
    try:
        response = client.get_object(settings.minio_bucket, s3_key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()
    except S3Error:
        logger.exception("MinIO get_object failed for key=%s", s3_key)
        return None


def presigned_photo_url(s3_key: str, *, hours: int = 1) -> str | None:
    settings = load_settings()
    try:
        return _client().presigned_get_object(
            settings.minio_bucket,
            s3_key,
            expires=timedelta(hours=hours),
        )
    except S3Error:
        logger.exception("MinIO presign failed for key=%s", s3_key)
        return None
