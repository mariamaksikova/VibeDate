#!/usr/bin/env python3
"""Запускает все комбинации режима кеша и профиля нагрузки на отдельном uvicorn-процессе."""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
try:
    import httpx
except ModuleNotFoundError:
    print(
        "Нет пакета httpx. Установите зависимости в виртуальное окружение:\n"
        "  cd practice/cache-comparison\n"
        "  python3 -m venv .venv\n"
        "  .venv/bin/pip install -r requirements.txt\n"
        "  export PYTHONPATH=.\n"
        "  .venv/bin/python3 scripts/run_matrix.py\n",
        file=sys.stderr,
    )
    sys.exit(1)

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from load_gen.runner import fetch_stats, post_final_flush, post_reset, run_load

PORT = int(os.environ.get("BENCH_PORT", "8090"))
HOST = os.environ.get("BENCH_HOST", "127.0.0.1")
BASE = f"http://{HOST}:{PORT}"
DURATION = float(os.environ.get("BENCH_DURATION", "25"))
CONCURRENCY = int(os.environ.get("BENCH_CONCURRENCY", "40"))
MAX_ID = int(os.environ.get("BENCH_MAX_ID", "5000"))

MODES = ["cache_aside", "write_through", "write_back"]
PROFILES = ["read_heavy", "balanced", "write_heavy"]


def _wait_health(timeout: float = 40.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = httpx.get(f"{BASE}/health", timeout=2.0)
            if r.status_code == 200:
                return
        except httpx.RequestError:
            pass
        time.sleep(0.2)
    raise RuntimeError("Сервер не поднялся за отведённое время")


def _start_server(mode: str) -> subprocess.Popen:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    env["CACHE_MODE"] = mode
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            HOST,
            "--port",
            str(PORT),
        ],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


async def _one_case(mode: str, profile: str) -> dict:
    await post_reset(BASE)
    await asyncio.sleep(0.25)
    client = await run_load(BASE, DURATION, CONCURRENCY, profile, MAX_ID)
    if mode == "write_back":
        await asyncio.sleep(2.0)
        await post_final_flush(BASE)
    server = await fetch_stats(BASE)
    return {"mode": mode, "profile": profile, "client": client, "server": server}


async def _run_matrix() -> list[dict]:
    rows: list[dict] = []
    proc: subprocess.Popen | None = None
    try:
        for mode in MODES:
            if proc is not None:
                proc.send_signal(signal.SIGTERM)
                proc.wait(timeout=15)
                proc = None
                await asyncio.sleep(0.8)
            proc = _start_server(mode)
            await asyncio.to_thread(_wait_health)
            for profile in PROFILES:
                rows.append(await _one_case(mode, profile))
                print(json.dumps(rows[-1], ensure_ascii=False)[:600], flush=True)
    finally:
        if proc is not None:
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
    return rows


def main() -> None:
    out_path = ROOT / "results" / "matrix.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows = asyncio.run(_run_matrix())
    summary = {
        "meta": {
            "duration_sec": DURATION,
            "concurrency": CONCURRENCY,
            "max_id": MAX_ID,
            "base_url": BASE,
        },
        "runs": rows,
    }
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
