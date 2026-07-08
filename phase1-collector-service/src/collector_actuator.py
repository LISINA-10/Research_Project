import time
import requests
import numpy as np
import logging
from typing import List, Dict, Any

from .models.matrix_factory import MatrixFactory
from .models.matrix_models import MetricsMatrix

logger = logging.getLogger(__name__)


class ActuatorCollector:
    """
    Collecteur générique qui supporte plusieurs formats de réponse.
    """

    def collect(self, services: List[Dict[str, Any]], duration: int, interval: int,
                factory: MatrixFactory, base_port: int = 8080) -> MetricsMatrix:
        """
        Collecte les métriques depuis les endpoints.
        """
        n_services = len(services)
        n_samples = int(duration / interval)

        service_names = [s.get('nom', 'unknown') for s in services]
        matrix = factory.create_matrix(n_services, n_samples, service_names)

        logger.info(f"Collecte: {n_samples} échantillons pour {n_services} services")
        logger.info(f"Services: {service_names}")

        for j in range(n_samples):
            start_time = time.time()

            for i, service in enumerate(services):
                service_name = service.get('nom')
                url_cpu = service.get('url_cpu')
                url_ram = service.get('url_ram')

                base_url = f"http://{service_name}:{base_port}"

                cpu_val = self._query_generic(f"{base_url}{url_cpu}")
                ram_val = self._query_generic(f"{base_url}{url_ram}")

                matrix.cpu_matrix[i, j] = cpu_val if cpu_val is not None else np.nan
                matrix.ram_matrix[i, j] = ram_val if ram_val is not None else np.nan

                logger.debug(f"  {service_name}: CPU={matrix.cpu_matrix[i,j]:.3f}, RAM={matrix.ram_matrix[i,j]:.2f}")

            elapsed = time.time() - start_time
            sleep_time = max(0, interval - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)

        logger.info(f"Collecte terminée. NaN CPU: {np.isnan(matrix.cpu_matrix).sum()}, NaN RAM: {np.isnan(matrix.ram_matrix).sum()}")

        return matrix

    def _query_generic(self, url: str) -> float:
        """
        Interroge un endpoint et essaie d'extraire la valeur.
        Supporte plusieurs formats de réponse.
        """
        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            data = response.json()

            # 1. Format Spring Boot Actuator
            if 'measurements' in data and data['measurements']:
                return data['measurements'][0]['value']

            # 2. Format Prometheus /metrics (simplifié)
            if isinstance(data, dict):
                # 2.1 Chercher des clés courantes
                common_keys = ['cpu_usage', 'cpu', 'system.cpu.usage', 'jvm.memory.used', 'memory', 'mem']
                for key in common_keys:
                    if key in data and isinstance(data[key], (int, float)):
                        return data[key]

                # 2.2 Prendre la première valeur numérique trouvée
                for key, value in data.items():
                    if isinstance(value, (int, float)):
                        return value

                # 2.3 Si la valeur est dans un objet imbriqué
                if 'value' in data:
                    return data['value']
                if 'metric' in data and 'value' in data['metric']:
                    return data['metric']['value']

            # 3. Format texte (si response est du texte, pas JSON)
            # Si ce n'est pas du JSON, on essaie de parser
            return None

        except requests.exceptions.ConnectionError:
            logger.warning(f"Connexion impossible: {url}")
            return None
        except requests.exceptions.Timeout:
            logger.warning(f"Timeout: {url}")
            return None
        except Exception as e:
            logger.warning(f"Erreur ({url}): {e}")
            return None