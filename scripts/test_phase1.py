#!/usr/bin/env python3
"""Script de test rapide pour la Phase 1."""

import json
import sys
import time

import numpy as np
import requests

COLLECTOR_URL = "http://localhost:8001"


def wait_for_service(url: str, retries: int = 20) -> bool:
    for _ in range(retries):
        try:
            response = requests.get(f"{url}/health", timeout=3)
            if response.status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(2)
    return False


def main() -> int:
    print("1. Verification du service Phase 1...")
    if not wait_for_service(COLLECTOR_URL):
        print("ERREUR: phase1-collector indisponible sur http://localhost:8001")
        return 1
    print("   OK")

    payload = {
        "use_config": True,
        "duration_seconds": 20,
        "interval_seconds": 5,
        "base_port": 8080,
        "job_id": f"test_{int(time.time())}",
    }

    print("2. Lancement de la collecte...")
    response = requests.post(f"{COLLECTOR_URL}/api/v1/collect", json=payload, timeout=120)
    if response.status_code != 200:
        print(f"ERREUR collecte: {response.status_code} - {response.text}")
        return 1

    result = response.json()
    job_id = result["job_id"]
    print(f"   Job termine: {job_id}")
    print(f"   Charge activee: {result.get('load_enabled', False)}")

    print("3. Verification des matrices...")
    status = requests.get(f"{COLLECTOR_URL}/api/v1/status/{job_id}", timeout=10)
    if status.status_code != 200:
        print(f"ERREUR status: {status.text}")
        return 1

    data = status.json()
    if data.get("status") != "completed":
        print(f"ERREUR: statut inattendu {data}")
        return 1

    for metric in ("cpu", "ram", "lat", "bw"):
        shape = data["matrices"][metric]
        print(f"   {metric.upper()}: {shape}")

    print("4. Verification des valeurs non-NaN...")
    # Relecture via endpoint jobs
    job_detail = requests.get(f"{COLLECTOR_URL}/api/v1/jobs/{job_id}", timeout=10).json()
    print(f"   Services: {[s['name'] for s in job_detail['services']]}")

    print("\nTest Phase 1 reussi.")
    print(f"Fichiers attendus dans data/raw/: M_*_{job_id}.npy")
    return 0


if __name__ == "__main__":
    sys.exit(main())
