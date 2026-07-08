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
    Collecte les métriques CPU et RAM depuis les endpoints Spring Boot Actuator.
    """
    
    def collect(self, services: List[Dict[str, Any]], duration: int, interval: int,
                factory: MatrixFactory, base_port: int = 8080) -> MetricsMatrix:
        """
        Collecte les métriques depuis Actuator.
        
        Args:
            services: Liste des services avec 'nom', 'url_cpu', 'url_ram'
            duration: Durée de collecte en secondes
            interval: Intervalle d'échantillonnage en secondes
            factory: MatrixFactory pour créer la matrice
            base_port: Port par défaut (8080)
        
        Returns:
            MetricsMatrix: Matrice des métriques collectées
        """
        n_services = len(services)
        n_samples = int(duration / interval)
        
        # Créer la matrice via le factory
        service_names = [s.get('nom', 'unknown') for s in services]
        matrix = factory.create_matrix(n_services, n_samples, service_names)
        
        logger.info(f"Collecte Actuator: {n_samples} échantillons pour {n_services} services")
        logger.info(f"Services: {service_names}")
        
        for j in range(n_samples):
            start_time = time.time()
            logger.debug(f"Échantillon {j+1}/{n_samples}")
            
            for i, service in enumerate(services):
                service_name = service.get('nom')
                url_cpu = service.get('url_cpu')
                url_ram = service.get('url_ram')
                
                # Construire l'URL complète
                base_url = f"http://{service_name}:{base_port}"
                
                cpu_val = self._query_actuator(f"{base_url}{url_cpu}")
                ram_val = self._query_actuator(f"{base_url}{url_ram}")
                
                matrix.cpu_matrix[i, j] = cpu_val if cpu_val is not None else np.nan
                matrix.ram_matrix[i, j] = ram_val if ram_val is not None else np.nan
                
                logger.debug(f"  {service_name}: CPU={matrix.cpu_matrix[i,j]:.3f}, RAM={matrix.ram_matrix[i,j]:.2f}")
            
            # Attendre l'intervalle
            elapsed = time.time() - start_time
            sleep_time = max(0, interval - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)
        
        logger.info(f"Collecte terminée. Matrice CPU: {matrix.cpu_matrix.shape}, RAM: {matrix.ram_matrix.shape}")
        logger.info(f"  NaN CPU: {np.isnan(matrix.cpu_matrix).sum()}, NaN RAM: {np.isnan(matrix.ram_matrix).sum()}")
        
        return matrix
    
    def _query_actuator(self, url: str) -> float:
        """
        Interroge un endpoint Actuator et extrait la valeur.
        """
        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            data = response.json()
            
            # Structure Actuator: { "measurements": [ { "value": ... } ] }
            if 'measurements' in data and data['measurements']:
                return data['measurements'][0]['value']
            return None
        except requests.exceptions.ConnectionError:
            logger.warning(f"Connexion impossible: {url}")
            return None
        except requests.exceptions.Timeout:
            logger.warning(f"Timeout: {url}")
            return None
        except Exception as e:
            logger.warning(f"Erreur Actuator ({url}): {e}")
            return None
    
    def _query_actuator_with_host(self, host: str, port: int, endpoint: str) -> float:
        """
        Interroge un endpoint Actuator avec un hôte et un port personnalisés.
        """
        url = f"http://{host}:{port}{endpoint}"
        return self._query_actuator(url)