import os
import json
import numpy as np
import logging
from typing import Optional
from .matrix_models import MetricsMatrix, CollectionConfig
from .config_builder import ConfigBuilder

logger = logging.getLogger(__name__)


class MatrixFactory:
    """
    Factory pour créer et gérer les matrices de métriques.
    """
    
    def __init__(self, config_path: str = "config/config.json", base_path: str = "./data/raw"):
        self.config_path = config_path
        self.base_path = base_path
        self.config: Optional[CollectionConfig] = None
        self._load_config()
    
    def _load_config(self) -> 'MatrixFactory':
        """Charge la configuration."""
        builder = ConfigBuilder(self.config_path)
        self.config = builder.load().build_config()
        return self
    
    def get_config(self) -> CollectionConfig:
        """Retourne la configuration."""
        if self.config is None:
            self._load_config()
        return self.config
    
    def create_empty_matrix(self) -> MetricsMatrix:
        """
        Crée une matrice vide à partir de la configuration.
        """
        config = self.get_config()
        n_services = config.n_services
        n_samples = config.n_samples
        
        return MetricsMatrix(
            cpu_matrix=np.zeros((n_services, n_samples)),
            ram_matrix=np.zeros((n_services, n_samples)),
            service_names=[s.nom for s in config.services],
            n_services=n_services,
            n_samples=n_samples
        )
    
    def create_matrix(self, n_services: int, n_samples: int, service_names: list) -> MetricsMatrix:
        """
        Crée une matrice avec des dimensions personnalisées.
        """
        return MetricsMatrix(
            cpu_matrix=np.zeros((n_services, n_samples)),
            ram_matrix=np.zeros((n_services, n_samples)),
            service_names=service_names,
            n_services=n_services,
            n_samples=n_samples
        )
    
    def save_to_file(self, matrix: MetricsMatrix, timestamp: str) -> str:
        """
        Sauvegarde la matrice sur le disque.
        """
        os.makedirs(self.base_path, exist_ok=True)
        
        cpu_path = os.path.join(self.base_path, f"M_CPU_{timestamp}.npy")
        ram_path = os.path.join(self.base_path, f"M_RAM_{timestamp}.npy")
        
        np.save(cpu_path, matrix.cpu_matrix)
        np.save(ram_path, matrix.ram_matrix)
        
        # Métadonnées
        metadata = {
            "timestamp": timestamp,
            "services": matrix.service_names,
            "n_services": matrix.n_services,
            "n_samples": matrix.n_samples,
            "cpu_file": cpu_path,
            "ram_file": ram_path
        }
        
        meta_path = os.path.join(self.base_path, f"metadata_{timestamp}.json")
        with open(meta_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        logger.info(f"Matrice sauvegardée: {matrix.n_services} services, {matrix.n_samples} échantillons")
        return timestamp
    
    def load_from_file(self, timestamp: str) -> MetricsMatrix:
        """
        Charge une matrice depuis le disque.
        """
        cpu_path = os.path.join(self.base_path, f"M_CPU_{timestamp}.npy")
        ram_path = os.path.join(self.base_path, f"M_RAM_{timestamp}.npy")
        meta_path = os.path.join(self.base_path, f"metadata_{timestamp}.json")
        
        if not os.path.exists(cpu_path) or not os.path.exists(ram_path):
            raise FileNotFoundError(f"Matrices pour {timestamp} non trouvées")
        
        cpu_matrix = np.load(cpu_path)
        ram_matrix = np.load(ram_path)
        
        with open(meta_path, 'r') as f:
            metadata = json.load(f)
        
        return MetricsMatrix(
            cpu_matrix=cpu_matrix,
            ram_matrix=ram_matrix,
            service_names=metadata.get("services", []),
            n_services=metadata.get("n_services", 0),
            n_samples=metadata.get("n_samples", 0),
            timestamp=timestamp
        )
    
    def list_collections(self) -> list:
        """Liste toutes les collections disponibles."""
        import glob
        
        meta_files = glob.glob(os.path.join(self.base_path, "metadata_*.json"))
        collections = []
        for meta_path in meta_files:
            with open(meta_path, 'r') as f:
                metadata = json.load(f)
            collections.append({
                "timestamp": metadata.get("timestamp"),
                "services": metadata.get("services", []),
                "n_samples": metadata.get("n_samples", 0)
            })
        return collections