from __future__ import annotations

import os

from celery import Celery
from dotenv import load_dotenv

load_dotenv()

celery_app = Celery(
    "vibedate",
    broker=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1"),
)

celery_app.conf.imports = ("app.tasks",)
celery_app.conf.timezone = "UTC"
celery_app.conf.beat_schedule = {
    "recalculate-all-ratings": {
        "task": "app.tasks.recalculate_all_ratings",
        "schedule": 600.0,
    },
}
