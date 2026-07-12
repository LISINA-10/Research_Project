import time
import requests
import numpy as np
import logging
from typing import List, Dict, Any

from .load_generator import LoadGenerator
from .models.matrix_factory import MatrixFactory
from .models.matrix_models import MetricsMatrix

logger = logging.getLogger(__name__)


class ActuatorCollector:
    """
    Collecteur générique qui supporte plusieurs formats de réponse.
    Collecte : CPU, RAM, Latence, Débit
    """

    def __init__(self) -> None:
        self.load_generator = LoadGenerator()

    def collect(self, services: List[Dict[str, Any]], duration: int, interval: int,
                factory: MatrixFactory, base_port: int = 8080) -> MetricsMatrix:
        """
        Collecte les métriques depuis les endpoints.
        Lance en parallèle un générateur de charge si transactions > 0.
        """
        n_services = len(services)
        n_samples = max(1, int(duration / interval))

        service_names = [s.get('nom', 'unknown') for s in services]
        matrix = factory.create_matrix(n_services, n_samples, service_names)

        logger.info(f"Collecte: {n_samples} échantillons pour {n_services} services")
        logger.info(f"Services: {service_names}")

        self.load_generator.start(services, base_port, duration)

        try:
            for j in range(n_samples):
                start_time = time.time()

                for i, service in enumerate(services):
                    service_name = service.get('nom')
                    url_cpu = service.get('url_cpu')
                    url_ram = service.get('url_ram')
                    url_lat = service.get('url_lat', '/actuator/health')
                    url_bw = service.get('url_bw', '/actuator/health')

                    base_url = f"http://{service_name}:{base_port}"

                    cpu_val = self._query_generic(f"{base_url}{url_cpu}")
                    ram_val = self._query_generic(f"{base_url}{url_ram}")
                    lat_val = self._query_latency(service_name, base_port, url_lat)
                    bw_val = self._query_bandwidth(service_name, base_port, url_bw)

                    matrix.cpu_matrix[i, j] = cpu_val if cpu_val is not None else np.nan
                    matrix.ram_matrix[i, j] = ram_val if ram_val is not None else np.nan
                    matrix.lat_matrix[i, j] = lat_val if lat_val is not None else np.nan
                    matrix.bw_matrix[i, j] = bw_val if bw_val is not None else np.nan

                    logger.debug(
                        "  %s: CPU=%.3f, RAM=%.2f, Lat=%.2fms, BW=%.2f bytes/s",
                        service_name,
                        matrix.cpu_matrix[i, j],
                        matrix.ram_matrix[i, j],
                        matrix.lat_matrix[i, j],
                        matrix.bw_matrix[i, j],
                    )

                elapsed = time.time() - start_time
                sleep_time = max(0, interval - elapsed)
                if sleep_time > 0:
                    time.sleep(sleep_time)
        finally:
            self.load_generator.stop()

        logger.info("Collecte terminée.")
        logger.info("  NaN CPU: %s", np.isnan(matrix.cpu_matrix).sum())
        logger.info("  NaN RAM: %s", np.isnan(matrix.ram_matrix).sum())
        logger.info("  NaN LAT: %s", np.isnan(matrix.lat_matrix).sum())
        logger.info("  NaN BW:  %s", np.isnan(matrix.bw_matrix).sum())

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
                common_keys = ['cpu_usage', 'cpu', 'system.cpu.usage', 
                               'jvm.memory.used', 'memory', 'mem']
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

    def _normalize_endpoint(self, endpoint: str) -> str:
        if not endpoint:
            return "/actuator/health"
        return endpoint if endpoint.startswith("/") else f"/{endpoint}"

    def _query_latency(self, service_name: str, base_port: int, endpoint: str = "/actuator/health") -> float:
        """
        Mesure la latence en effectuant un appel HTTP vers le service.
        
        Args:
            service_name: Nom du service
            base_port: Port du service
            endpoint: Endpoint à interroger (par défaut /actuator/health)
        
        Returns:
            Latence en millisecondes (ms)
        """
        endpoint = self._normalize_endpoint(endpoint)
        url = f"http://{service_name}:{base_port}{endpoint}"
        try:
            start = time.time()
            response = requests.get(url, timeout=5)
            end = time.time()
            latency = (end - start) * 1000
            
            # Vérifier que la réponse est valide
            if response.status_code == 200:
                return latency
            else:
                logger.warning(f"Latence: statut HTTP {response.status_code} pour {url}")
                return np.nan
        except requests.exceptions.ConnectionError:
            logger.warning(f"Latence: Connexion impossible {url}")
            return np.nan
        except requests.exceptions.Timeout:
            logger.warning(f"Latence: Timeout {url}")
            return np.nan
        except Exception as e:
            logger.warning(f"Latence: Erreur {url} - {e}")
            return np.nan

    def _query_bandwidth(self, service_name: str, base_port: int, endpoint: str = "/actuator/health") -> float:
        """
        Mesure le débit en récupérant la taille de la réponse divisée par le temps de réponse.
        
        Args:
            service_name: Nom du service
            base_port: Port du service
            endpoint: Endpoint à interroger (par défaut /actuator/health)
        
        Returns:
            Débit en octets/seconde
        """
        endpoint = self._normalize_endpoint(endpoint)
        url = f"http://{service_name}:{base_port}{endpoint}"
        try:
            start = time.time()
            response = requests.get(url, timeout=5)
            end = time.time()
            duration = end - start

            if duration > 0 and response.status_code == 200:
                bandwidth = len(response.content) / duration
                return bandwidth
            else:
                return np.nan
        except requests.exceptions.ConnectionError:
            logger.warning(f"Débit: Connexion impossible {url}")
            return np.nan
        except requests.exceptions.Timeout:
            logger.warning(f"Débit: Timeout {url}")
            return np.nan
        except Exception as e:
            logger.warning(f"Débit: Erreur {url} - {e}")
            return np.nan