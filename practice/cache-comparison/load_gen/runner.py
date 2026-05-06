"""Единый генератор нагрузки: одинаковые длительность, объём запросов (по времени), диапазон id."""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

PROFILES: dict[str, float] = {
    "read_heavy": 0.8,
    "balanced": 0.5,
    "write_heavy": 0.2,
}


@dataclass
class ClientAgg:
    reads: int = 0
    writes: int = 0
    errors: int = 0
    lat_ms: list[float] = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def add(self, is_read: bool, status: int, dt_ms: float) -> None:
        async with self.lock:
            if status >= 400:
                self.errors += 1
            if is_read:
                self.reads += 1
            else:
                self.writes += 1
            self.lat_ms.append(dt_ms)


async def _worker(
    base: str,
    duration_sec: float,
    read_prob: float,
    max_id: int,
    client: httpx.AsyncClient,
    agg: ClientAgg,
    stop: asyncio.Event,
) -> None:
    deadline = time.monotonic() + duration_sec
    while time.monotonic() < deadline and not stop.is_set():
        item_id = random.randint(1, max_id)
        is_read = random.random() < read_prob
        t0 = time.perf_counter()
        try:
            if is_read:
                r = await client.get(f"{base}/items/{item_id}")
            else:
                val = f"w-{time.time_ns()}"
                r = await client.put(f"{base}/items/{item_id}", json={"value": val})
            dt_ms = (time.perf_counter() - t0) * 1000.0
            await agg.add(is_read, r.status_code, dt_ms)
        except httpx.RequestError:
            async with agg.lock:
                agg.errors += 1


async def run_load(
    base_url: str,
    duration_sec: float,
    concurrency: int,
    profile: str,
    max_id: int,
) -> dict:
    read_prob = PROFILES[profile]
    base = base_url.rstrip("/")
    agg = ClientAgg()
    stop = asyncio.Event()
    limits = httpx.Limits(max_connections=concurrency * 2, max_keepalive_connections=concurrency * 2)
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0), limits=limits) as client:
        t_wall0 = time.perf_counter()
        workers = [
            asyncio.create_task(_worker(base, duration_sec, read_prob, max_id, client, agg, stop))
            for _ in range(concurrency)
        ]
        await asyncio.gather(*workers)
        wall_sec = time.perf_counter() - t_wall0

    async with agg.lock:
        total = agg.reads + agg.writes
        lat = list(agg.lat_ms)
        err = agg.errors
        reads = agg.reads
        writes = agg.writes

    mean_ms = statistics.mean(lat) if lat else 0.0
    p50 = statistics.median(lat) if lat else 0.0
    p95 = _percentile(lat, 0.95) if lat else 0.0
    rps = total / wall_sec if wall_sec > 0 else 0.0

    return {
        "profile": profile,
        "read_prob": read_prob,
        "duration_wall_sec": round(wall_sec, 4),
        "concurrency": concurrency,
        "max_id": max_id,
        "client_total_requests": total,
        "client_reads": reads,
        "client_writes": writes,
        "client_errors": err,
        "throughput_rps": round(rps, 2),
        "latency_mean_ms": round(mean_ms, 3),
        "latency_p50_ms": round(p50, 3),
        "latency_p95_ms": round(p95, 3),
    }


def _percentile(data: list[float], q: float) -> float:
    if not data:
        return 0.0
    s = sorted(data)
    k = max(0, min(len(s) - 1, int(round(q * (len(s) - 1)))))
    return s[k]


async def fetch_stats(base_url: str) -> dict:
    base = base_url.rstrip("/")
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(f"{base}/stats")
        r.raise_for_status()
        return r.json()


async def post_reset(base_url: str) -> None:
    base = base_url.rstrip("/")
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(f"{base}/admin/reset")
        r.raise_for_status()


async def post_final_flush(base_url: str) -> None:
    base = base_url.rstrip("/")
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(f"{base}/admin/final-flush")
        r.raise_for_status()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", default="http://127.0.0.1:8090")
    p.add_argument("--duration", type=float, default=25.0)
    p.add_argument("--concurrency", type=int, default=40)
    p.add_argument("--profile", choices=list(PROFILES.keys()), required=True)
    p.add_argument("--max-id", type=int, default=5000)
    p.add_argument("--stats-out", type=Path, default=None)
    args = p.parse_args()

    async def _run() -> dict:
        client_metrics = await run_load(
            args.base_url,
            args.duration,
            args.concurrency,
            args.profile,
            args.max_id,
        )
        server = await fetch_stats(args.base_url)
        return {"client": client_metrics, "server": server}

    out = asyncio.run(_run())
    text = json.dumps(out, ensure_ascii=False, indent=2)
    print(text)
    if args.stats_out:
        args.stats_out.parent.mkdir(parents=True, exist_ok=True)
        args.stats_out.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
