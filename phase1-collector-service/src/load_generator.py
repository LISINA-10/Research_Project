import logging
import threading
import time
from typing import Any, Dict, List

import requests

logger = logging.getLogger(__name__)


class LoadGenerator:
    """Génère une charge HTTP concurrente pendant la collecte de métriques."""

    def __init__(self) -> None:
        self._stop_event = threading.Event()
        self._threads: List[threading.Thread] = []

    def start(
        self,
        services: List[Dict[str, Any]],
        base_port: int,
        duration: int,
        load_endpoint: str = "/actuator/health",
    ) -> None:
        self._stop_event.clear()
        self._threads = []

        for service in services:
            tps = int(service.get("transactions", 0) or 0)
            if tps <= 0:
                continue

            service_name = service.get("nom")
            endpoint = service.get("url_lat") or load_endpoint
            thread = threading.Thread(
                target=self._generate_load,
                args=(service_name, base_port, tps, endpoint, duration),
                daemon=True,
            )
            thread.start()
            self._threads.append(thread)
            logger.info(
                "Charge démarrée pour %s: %s req/s vers %s",
                service_name,
                tps,
                endpoint,
            )

    def stop(self) -> None:
        self._stop_event.set()
        for thread in self._threads:
            thread.join(timeout=3)
        self._threads.clear()

    def _generate_load(
        self,
        service_name: str,
        base_port: int,
        tps: int,
        endpoint: str,
        duration: int,
    ) -> None:
        if not endpoint.startswith("/"):
            endpoint = f"/{endpoint}"

        url = f"http://{service_name}:{base_port}{endpoint}"
        interval = 1.0 / tps
        end_time = time.time() + duration + 2

        while time.time() < end_time and not self._stop_event.is_set():
            started = time.time()
            try:
                requests.get(url, timeout=3)
            except requests.RequestException:
                pass

            elapsed = time.time() - started
            sleep_time = max(0.0, interval - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)
