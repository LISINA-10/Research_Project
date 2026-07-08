import os
import json
import numpy as np
import logging
from typing import Tuple, List

logger = logging.getLogger(__name__)


class StorageManager:
    """
    Gère le stockage et le chargement des matrices.
    """
    
    def __init__(self, base_path: str = "./data/raw"):
        self.base_path = base_path
        os.makedirs(base_path, exist_ok=True)
    
    def save_matrices(self, M_CPU: np.ndarray, M_RAM: np.ndarray,
                      service_names: List[str], timestamp: str) -> str:
        """
        Sauvegarde les matrices et les métadonnées.
        """
        cpu_path = os.path.join(self.base_path, f"M_CPU_{timestamp}.npy")
        ram_path = os.path.join(self.base_path, f"M_RAM_{timestamp}.npy")
        
        np.save(cpu_path, M_CPU)
        np.save(ram_path, M_RAM)
        
        metadata = {
            "timestamp": timestamp,
            "services": service_names,
            "n_services": len(service_names),
            "n_samples": M_CPU.shape[1],
            "cpu_file": cpu_path,
            "ram_file": ram_path
        }
        
        meta_path = os.path.join(self.base_path, f"metadata_{timestamp}.json")
        with open(meta_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        logger.info(f"Matrices sauvegardées: {len(service_names)} services, {M_CPU.shape[1]} échantillons")
        return timestamp
    
    def load_matrices(self, timestamp: str) -> Tuple[np.ndarray, np.ndarray, List[str]]:
        """
        Charge les matrices et les métadonnées.
        """
        cpu_path = os.path.join(self.base_path, f"M_CPU_{timestamp}.npy")
        ram_path = os.path.join(self.base_path, f"M_RAM_{timestamp}.npy")
        meta_path = os.path.join(self.base_path, f"metadata_{timestamp}.json")
        
        if not os.path.exists(cpu_path):
            raise FileNotFoundError(f"Fichier CPU non trouvé: {cpu_path}")
        if not os.path.exists(ram_path):
            raise FileNotFoundError(f"Fichier RAM non trouvé: {ram_path}")
        
        M_CPU = np.load(cpu_path)
        M_RAM = np.load(ram_path)
        
        with open(meta_path, 'r') as f:
            metadata = json.load(f)
        
        service_names = metadata.get("services", [])
        
        logger.info(f"Matrices chargées: {len(service_names)} services, {M_CPU.shape[1]} échantillons")
        return M_CPU, M_RAM, service_names
    
    def list_collections(self) -> List[dict]:
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
    
    def delete_collection(self, timestamp: str) -> bool:
        """Supprime une collection."""
        import glob
        
        files = glob.glob(os.path.join(self.base_path, f"*_{timestamp}.*"))
        if not files:
            return False
        
        for file in files:
            os.remove(file)
        
        logger.info(f"Collection {timestamp} supprimée")
        return True