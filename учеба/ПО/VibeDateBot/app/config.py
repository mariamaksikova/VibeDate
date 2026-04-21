from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    bot_token: str
    database_url: str
    redis_url: str
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_bucket: str
    celery_broker_url: str
    celery_result_backend: str


def load_settings() -> Settings:
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    database_url = os.getenv("DATABASE_URL", "").strip()
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0").strip()
    minio_endpoint = os.getenv("MINIO_ENDPOINT", "localhost:9000").strip()
    minio_access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin").strip()
    minio_secret_key = os.getenv("MINIO_SECRET_KEY", "minioadmin").strip()
    minio_bucket = os.getenv("MINIO_BUCKET", "vibedate-photos").strip()
    celery_broker_url = os.getenv("CELERY_BROKER_URL", redis_url).strip()
    celery_result_backend = os.getenv("CELERY_RESULT_BACKEND", redis_url).strip()

    if not bot_token:
        raise RuntimeError("BOT_TOKEN is not set")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set")

    return Settings(
        bot_token=bot_token,
        database_url=database_url,
        redis_url=redis_url,
        minio_endpoint=minio_endpoint,
        minio_access_key=minio_access_key,
        minio_secret_key=minio_secret_key,
        minio_bucket=minio_bucket,
        celery_broker_url=celery_broker_url,
        celery_result_backend=celery_result_backend,
    )
