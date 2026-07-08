import json
import logging
from typing import Optional
from .matrix_models import Ressources, ServiceInfo, CollectionConfig

logger = logging.getLogger(__name__)


class ConfigBuilder:
    """
    Construit les objets de configuration à partir du fichier JSON.
    """
    
    def __init__(self, config_path: str = "config/config.json"):
        self.config_path = config_path
        self.data = None
    
    def load(self) -> 'ConfigBuilder':
        """Charge le fichier JSON."""
        try:
            with open(self.config_path, 'r') as f:
                self.data = json.load(f)
            logger.info(f"Configuration chargée depuis {self.config_path}")
        except FileNotFoundError:
            logger.warning(f"Fichier {self.config_path} non trouvé, utilisation des valeurs par défaut")
            self.data = self._get_default_data()
        except json.JSONDecodeError as e:
            logger.error(f"Erreur de parsing JSON: {e}")
            self.data = self._get_default_data()
        return self
    
    def _get_default_data(self) -> dict:
        """Retourne des données par défaut."""
        return {
            "ressources": {
                "cpu_cores": 0,
                "ram_gb": 0,
                "duree_collecte": 0,
                "interval_collecte": 0
            },
            "services": []
        }
    
    def build_ressources(self) -> Ressources:
        """Crée l'objet Ressources."""
        r = self.data.get("ressources", {})
        return Ressources(
            cpu_cores=r.get("cpu_cores", 0),
            ram_gb=r.get("ram_gb", 0),
            duree_collecte=r.get("duree_collecte", 0),
            interval_collecte=r.get("interval_collecte", 0)
        )
    
    def build_services(self) -> list:
        """Crée la liste des objets ServiceInfo."""
        services_data = self.data.get("services", [])
        services = []
        for s in services_data:
            service = ServiceInfo(
                nom=s.get("nom", ""),
                url_cpu=s.get("url_cpu", ""),
                url_ram=s.get("url_ram", ""),
                transactions=s.get("transactions", 0)
            )
            services.append(service)
        return services
    
    def build_config(self) -> CollectionConfig:
        """Construit la configuration complète."""
        ressources = self.build_ressources()
        services = self.build_services()
        return CollectionConfig(ressources=ressources, services=services)
    
    def get_raw_data(self) -> dict:
        """Retourne les données brutes du JSON."""
        return self.data