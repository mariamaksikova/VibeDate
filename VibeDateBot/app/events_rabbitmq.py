from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_channel: Any | None = None
_connection: Any | None = None


def _ensure_connection_unlocked() -> tuple[Any, Any] | None:
    global _connection, _channel
    url = os.getenv("RABBITMQ_URL", "").strip()
    if not url:
        return None
    if _channel is not None:
        return _connection, _channel
    try:
        import pika
    except ImportError:
        logger.warning("pika not installed; RabbitMQ events disabled")
        return None
    params = pika.URLParameters(url)
    _connection = pika.BlockingConnection(params)
    _channel = _connection.channel()
    _channel.queue_declare(queue="vibedate.profile_events", durable=False)
    return _connection, _channel


def publish_profile_interaction(
    *,
    event: str,
    actor_tg_id: int,
    target_profile_id: int,
    is_like: bool | None = None,
    to_tg_id: int | None = None,
    text: str | None = None,
) -> None:
    """Fire-and-forget JSON event to RabbitMQ (stream processing demo)."""
    with _lock:
        conn_ch = _ensure_connection_unlocked()
        if conn_ch is None:
            return
        _connection, channel = conn_ch
        body: dict[str, Any] = {
            "event": event,
            "actor_tg_id": actor_tg_id,
            "target_profile_id": target_profile_id,
            "is_like": is_like,
        }
        if to_tg_id is not None:
            body["to_tg_id"] = to_tg_id
        if text is not None:
            body["text"] = text
        try:
            import pika

            channel.basic_publish(
                exchange="",
                routing_key="vibedate.profile_events",
                body=json.dumps(body).encode("utf-8"),
                properties=pika.BasicProperties(content_type="application/json", delivery_mode=1),
            )
        except Exception:
            logger.exception("RabbitMQ publish failed for %s", event)


def shutdown_publisher() -> None:
    global _connection, _channel
    with _lock:
        if _connection is not None:
            try:
                _connection.close()
            except Exception:
                logger.debug("RabbitMQ close ignored", exc_info=True)
        _connection = None
        _channel = None
