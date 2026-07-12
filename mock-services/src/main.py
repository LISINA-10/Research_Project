import os
import time
from threading import Lock

from fastapi import FastAPI

SERVICE_NAME = os.getenv("SERVICE_NAME", "mock-service")
BASE_LOAD = float(os.getenv("BASE_CPU", "0.15"))
LOAD_FACTOR = float(os.getenv("LOAD_FACTOR", "0.0004"))

app = FastAPI(title=f"Mock Actuator - {SERVICE_NAME}")
_request_count = 0
_lock = Lock()
_start_time = time.time()


def _increment_requests() -> int:
    global _request_count
    with _lock:
        _request_count += 1
        return _request_count


def _current_cpu() -> float:
    count = _increment_requests()
    elapsed = max(1.0, time.time() - _start_time)
    load = BASE_LOAD + (count * LOAD_FACTOR) + (count / elapsed) * 0.0001
    return min(load, 0.99)


def _current_ram() -> float:
    count = _increment_requests()
    return 256_000_000 + (count * 12_000)


@app.get("/actuator/health")
async def health():
    _increment_requests()
    return {"status": "UP", "service": SERVICE_NAME}


@app.get("/actuator/metrics/system.cpu.usage")
async def cpu_metric():
    value = _current_cpu()
    return {
        "name": "system.cpu.usage",
        "measurements": [{"statistic": "VALUE", "value": value}],
    }


@app.get("/actuator/metrics/jvm.memory.used")
async def ram_metric():
    value = _current_ram()
    return {
        "name": "jvm.memory.used",
        "measurements": [{"statistic": "VALUE", "value": value}],
    }


@app.get("/health")
async def root_health():
    return await health()
