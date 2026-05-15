from __future__ import annotations

import logging
import os
import threading
from typing import Any

logger = logging.getLogger(__name__)

_feed_views: Any | None = None
_reactions: Any | None = None


def _counters() -> tuple[Any, Any]:
    global _feed_views, _reactions
    if _feed_views is None:
        from prometheus_client import Counter

        _feed_views = Counter(
            "vibedate_feed_views_total",
            "Feed cards shown to users",
        )
        _reactions = Counter(
            "vibedate_reactions_total",
            "Likes and skips recorded",
            ("kind",),
        )
    return _feed_views, _reactions


def inc_feed_view() -> None:
    if os.getenv("PROMETHEUS_DISABLE", "").strip().lower() in {"1", "true", "yes"}:
        return
    views, _ = _counters()
    views.inc()


def inc_reaction(*, is_like: bool) -> None:
    if os.getenv("PROMETHEUS_DISABLE", "").strip().lower() in {"1", "true", "yes"}:
        return
    _, reactions = _counters()
    reactions.labels(kind="like" if is_like else "skip").inc()


def start_metrics_http_server_if_configured() -> None:
    port_raw = os.getenv("METRICS_PORT", "").strip()
    if not port_raw:
        return
    try:
        port = int(port_raw)
    except ValueError:
        logger.warning("METRICS_PORT is not an integer: %s", port_raw)
        return

    def _run() -> None:
        from prometheus_client import start_http_server

        start_http_server(port)
        logger.info("Prometheus metrics listening on :%s", port)

    threading.Thread(target=_run, name="prometheus-metrics", daemon=True).start()
