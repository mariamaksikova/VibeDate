"""
Optional RabbitMQ consumer for vibedate.profile_events (демонстрация потоковой обработки).

Запуск локально:
  export RABBITMQ_URL=amqp://guest:guest@localhost:5672/
  python -m app.event_consumer
"""

from __future__ import annotations

import json
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    url = os.getenv("RABBITMQ_URL", "").strip()
    if not url:
        logger.error("Set RABBITMQ_URL (e.g. amqp://guest:guest@localhost:5672/)")
        sys.exit(1)
    import pika

    connection = pika.BlockingConnection(pika.URLParameters(url))
    channel = connection.channel()
    channel.queue_declare(queue="vibedate.profile_events", durable=False)

    def callback(_ch: object, method: object, _properties: object, body: bytes) -> None:
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            logger.warning("Bad JSON: %s", body[:200])
        else:
            logger.info("profile_event %s", payload)

    channel.basic_consume(queue="vibedate.profile_events", on_message_callback=callback, auto_ack=True)
    logger.info("Consuming vibedate.profile_events; Ctrl+C to stop")
    channel.start_consuming()


if __name__ == "__main__":
    main()
