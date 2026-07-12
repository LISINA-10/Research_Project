from dataclasses import dataclass
from typing import List, Optional
import numpy as np


@dataclass
class Ressources:
    """Ressources globales du cluster"""
    cpu_cores: int
    ram_gb: int
    duree_collecte: int
    interval_collecte: int


@dataclass
class ServiceInfo:
    """Informations sur un microservice"""
    nom: str
    url_cpu: str
    url_ram: str
    transactions: int                  # ← Déplacé ici (sans valeur par défaut)
    url_lat: Optional[str] = None      # ← Optionnel (avec valeur par défaut)
    url_bw: Optional[str] = None       # ← Optionnel (avec valeur par défaut)


@dataclass
class CollectionConfig:
    """Configuration complète de la collecte"""
    ressources: Ressources
    services: List[ServiceInfo]
    
    @property
    def n_services(self) -> int:
        return len(self.services)
    
    @property
    def n_samples(self) -> int:
        if self.ressources.interval_collecte == 0:
            return 0
        return int(self.ressources.duree_collecte / self.ressources.interval_collecte)


@dataclass
class MetricsMatrix:
    """Matrice de métriques collectées"""
    cpu_matrix: np.ndarray          # Shape: (n_services, n_samples)
    ram_matrix: np.ndarray          # Shape: (n_services, n_samples)
    lat_matrix: np.ndarray          # ← NOUVEAU : Latence (ms)
    bw_matrix: np.ndarray           # ← NOUVEAU : Débit (octets/seconde)
    service_names: List[str]
    n_services: int
    n_samples: int
    timestamp: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "cpu": self.cpu_matrix.tolist(),
            "ram": self.ram_matrix.tolist(),
            "lat": self.lat_matrix.tolist(),      # ← NOUVEAU
            "bw": self.bw_matrix.tolist(),        # ← NOUVEAU
            "services": self.service_names,
            "n_services": self.n_services,
            "n_samples": self.n_samples,
            "timestamp": self.timestamp
        }