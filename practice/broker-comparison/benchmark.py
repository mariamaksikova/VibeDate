import asyncio
import csv
import json
import os
import statistics
import time
from dataclasses import dataclass, asdict

import aio_pika
from redis.asyncio import Redis


RABBIT_URL = os.getenv("RABBIT_URL", "amqp://guest:guest@rabbitmq:5672/")
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

MESSAGE_SIZES = [128, 1024, 10 * 1024, 100 * 1024]
TARGET_RATES = [1000, 5000, 10000]
MESSAGES_PER_TEST = 5000


@dataclass
class TestResult:
    broker: str
    message_size: int
    target_rate: int
    sent: int
    processed: int
    errors: int
    throughput_msg_sec: float
    avg_latency_ms: float
    p95_latency_ms: float
    max_latency_ms: float
    duration_sec: float
    queue_left: int


def percentile(values, p):
    if not values:
        return 0.0
    ordered = sorted(values)
    index = int((len(ordered) - 1) * p)
    return ordered[index]


def build_payload(size_bytes, sent_ts):
    fixed = {"sent_ts": sent_ts, "payload": ""}
    raw = json.dumps(fixed).encode("utf-8")
    overhead = len(raw)
    needed = max(0, size_bytes - overhead)
    fixed["payload"] = "x" * needed
    return json.dumps(fixed).encode("utf-8")


async def run_rabbit_test(message_size, target_rate, total_messages):
    connection = await aio_pika.connect(RABBIT_URL)
    channel = await connection.channel()
    queue = await channel.declare_queue("cmp_queue", durable=False)
    await queue.purge()

    latencies = []
    processed = 0
    errors = 0
    done = asyncio.Event()

    async def consumer():
        nonlocal processed, errors

        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                try:
                    body = json.loads(message.body.decode("utf-8"))
                    now = time.time()
                    latencies.append((now - body["sent_ts"]) * 1000)
                    processed += 1
                    await message.ack()
                    if processed >= total_messages:
                        done.set()
                        break
                except Exception:
                    errors += 1
                    await message.reject(requeue=False)

    async def producer():
        interval = 1 / target_rate if target_rate > 0 else 0
        for _ in range(total_messages):
            sent_ts = time.time()
            body = build_payload(message_size, sent_ts)
            msg = aio_pika.Message(body=body)
            await channel.default_exchange.publish(msg, routing_key="cmp_queue")
            if interval:
                await asyncio.sleep(interval)

    start = time.time()
    consumer_task = asyncio.create_task(consumer())
    await producer()
    await done.wait()
    duration = time.time() - start

    try:
        await asyncio.wait_for(consumer_task, timeout=2)
    except asyncio.TimeoutError:
        consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            pass
    queue_left = max(0, total_messages - processed)

    await channel.close()
    await connection.close()

    return TestResult(
        broker="rabbitmq",
        message_size=message_size,
        target_rate=target_rate,
        sent=total_messages,
        processed=processed,
        errors=errors,
        throughput_msg_sec=processed / duration if duration else 0,
        avg_latency_ms=statistics.mean(latencies) if latencies else 0,
        p95_latency_ms=percentile(latencies, 0.95),
        max_latency_ms=max(latencies) if latencies else 0,
        duration_sec=duration,
        queue_left=queue_left,
    )


async def run_redis_test(message_size, target_rate, total_messages):
    redis = Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    queue_name = "cmp_queue"
    await redis.delete(queue_name)

    latencies = []
    processed = 0
    errors = 0
    done = asyncio.Event()

    async def consumer():
        nonlocal processed, errors
        while processed < total_messages:
            item = await redis.brpop(queue_name, timeout=1)
            if not item:
                continue
            try:
                _, raw = item
                body = json.loads(raw)
                now = time.time()
                latencies.append((now - body["sent_ts"]) * 1000)
                processed += 1
            except Exception:
                errors += 1
        done.set()

    async def producer():
        interval = 1 / target_rate if target_rate > 0 else 0
        for _ in range(total_messages):
            sent_ts = time.time()
            body = build_payload(message_size, sent_ts).decode("utf-8")
            await redis.lpush(queue_name, body)
            if interval:
                await asyncio.sleep(interval)

    start = time.time()
    consumer_task = asyncio.create_task(consumer())
    await producer()
    await done.wait()
    duration = time.time() - start

    consumer_task.cancel()
    try:
        await consumer_task
    except asyncio.CancelledError:
        pass

    queue_left = await redis.llen(queue_name)
    await redis.aclose()

    return TestResult(
        broker="redis",
        message_size=message_size,
        target_rate=target_rate,
        sent=total_messages,
        processed=processed,
        errors=errors,
        throughput_msg_sec=processed / duration if duration else 0,
        avg_latency_ms=statistics.mean(latencies) if latencies else 0,
        p95_latency_ms=percentile(latencies, 0.95),
        max_latency_ms=max(latencies) if latencies else 0,
        duration_sec=duration,
        queue_left=queue_left,
    )


async def wait_for_brokers():
    for _ in range(30):
        try:
            conn = await aio_pika.connect(RABBIT_URL)
            await conn.close()
            redis = Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
            await redis.ping()
            await redis.aclose()
            return
        except Exception:
            await asyncio.sleep(2)
    raise RuntimeError("Brokers are not ready")


async def main():
    os.makedirs("results", exist_ok=True)
    await wait_for_brokers()

    results = []
    for size in MESSAGE_SIZES:
        for rate in TARGET_RATES:
            print(f"Running RabbitMQ size={size} rate={rate}", flush=True)
            rabbit_result = await run_rabbit_test(size, rate, MESSAGES_PER_TEST)
            results.append(rabbit_result)

            print(f"Running Redis size={size} rate={rate}", flush=True)
            redis_result = await run_redis_test(size, rate, MESSAGES_PER_TEST)
            results.append(redis_result)

    with open("results/results.json", "w", encoding="utf-8") as f:
        json.dump([asdict(r) for r in results], f, ensure_ascii=False, indent=2)

    with open("results/results.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(results[0]).keys()))
        writer.writeheader()
        for row in results:
            writer.writerow(asdict(row))

    print("Done. Files saved: results/results.json and results/results.csv", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
