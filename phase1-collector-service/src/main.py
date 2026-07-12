import os
import logging
from pathlib import Path
from fastapi import FastAPI, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from datetime import datetime
from pydantic import BaseModel, Field
from typing import List, Optional
import uvicorn
from sqlalchemy.orm import Session

from .collector_actuator import ActuatorCollector 
from .models.matrix_factory import MatrixFactory
from .models.config_builder import ConfigBuilder
from .storage import StorageManager
from .database import get_db, init_db
from .database.models import CollectionJob, ServiceMetadata

# Configuration des logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

APP_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = APP_ROOT.parent
FRONTEND_DIR = Path(os.getenv("FRONTEND_DIR", PROJECT_ROOT / "frontend"))
CONFIG_PATH = os.getenv("CONFIG_PATH", str(PROJECT_ROOT / "config" / "config.json"))
DATA_PATH = os.getenv("DATA_PATH", str(PROJECT_ROOT / "data" / "raw"))

# --- Initialisation de l'application ---
app = FastAPI(
    title="Auth-Scaler Phase 1: Metrics Collection",
    description="Collecte les métriques CPU, RAM, Latence et Débit via Actuator",
    version="1.1.0"
)

# --- Initialisation des composants ---
collector = ActuatorCollector()  
factory = MatrixFactory(config_path=CONFIG_PATH, base_path=DATA_PATH)
storage = StorageManager(base_path=DATA_PATH)

# --- Initialisation de la base de données ---
@app.on_event("startup")
async def startup_event():
    """Initialise la base de données au démarrage."""
    try:
        init_db()
        logger.info("✅ Base de données initialisée avec succès")
    except Exception as e:
        logger.error(f"❌ Erreur d'initialisation de la DB: {e}")

# --- Models pour l'API ---
class ServiceInput(BaseModel):
    nom: str
    url_cpu: str
    url_ram: str
    url_lat: Optional[str] = "/actuator/health"   # ← NOUVEAU
    url_bw: Optional[str] = "/actuator/health"    # ← NOUVEAU
    transactions: int

class CollectRequest(BaseModel):
    services: List[ServiceInput] = Field(default_factory=list)
    duration_seconds: Optional[int] = None
    interval_seconds: Optional[int] = None
    job_id: Optional[str] = None
    base_port: int = 8080
    use_config: bool = False

class CollectResponse(BaseModel):
    status: str
    message: str
    timestamp: str
    job_id: str
    shape: dict
    load_enabled: bool = False


def _resolve_collection_params(request: CollectRequest) -> dict:
    """Fusionne la requête API et config.json si demandé."""
    config = factory.get_config()

    duration = request.duration_seconds or config.ressources.duree_collecte or 30
    interval = request.interval_seconds or config.ressources.interval_collecte or 5
    base_port = request.base_port

    if request.services:
        services = [s.dict() for s in request.services]
    elif request.use_config and config.services:
        services = [
            {
                "nom": s.nom,
                "url_cpu": s.url_cpu,
                "url_ram": s.url_ram,
                "url_lat": s.url_lat or "/actuator/health",
                "url_bw": s.url_bw or "/actuator/health",
                "transactions": s.transactions,
            }
            for s in config.services
            if s.nom
        ]
    else:
        raise HTTPException(
            status_code=400,
            detail="Aucun service fourni. Envoyez une liste services ou activez use_config=true."
        )

    if duration <= 0 or interval <= 0:
        raise HTTPException(status_code=400, detail="duration_seconds et interval_seconds doivent être > 0")

    return {
        "services": services,
        "duration_seconds": duration,
        "interval_seconds": interval,
        "base_port": base_port,
        "load_enabled": any(s.get("transactions", 0) > 0 for s in services),
    }

# --- Endpoints API ---
@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "phase1-collector",
        "mode": "actuator"
    }

@app.get("/api/v1/config")
async def get_config():
    """Retourne la configuration chargée depuis config.json."""
    config = factory.get_config()
    return {
        "ressources": {
            "cpu_cores": config.ressources.cpu_cores,
            "ram_gb": config.ressources.ram_gb,
            "duree_collecte": config.ressources.duree_collecte,
            "interval_collecte": config.ressources.interval_collecte,
        },
        "services": [
            {
                "nom": s.nom,
                "url_cpu": s.url_cpu,
                "url_ram": s.url_ram,
                "url_lat": s.url_lat,
                "url_bw": s.url_bw,
                "transactions": s.transactions,
            }
            for s in config.services
        ],
    }


@app.post("/api/v1/collect", response_model=CollectResponse)
async def collect(request: CollectRequest, db: Session = Depends(get_db)):
    """
    Lance la collecte des métriques depuis les URLs fournies.
    Collecte : CPU, RAM, Latence, Débit
    """
    params = _resolve_collection_params(request)
    job_id = request.job_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    logger.info(f"📊 Démarrage collecte: {job_id}")

    try:
        job = CollectionJob(
            job_id=job_id,
            status="running",
            duration_seconds=params["duration_seconds"],
            interval_seconds=params["interval_seconds"],
            n_services=len(params["services"]),
            n_samples=max(1, int(params["duration_seconds"] / params["interval_seconds"])),
            base_port=params["base_port"],
            started_at=datetime.now()
        )
        db.add(job)
        db.commit()

        services = params["services"]
        logger.info(f"  Services: {[s['nom'] for s in services]}")
        if params["load_enabled"]:
            logger.info("  Générateur de charge activé (transactions > 0)")

        matrix = collector.collect(
            services=services,
            duration=params["duration_seconds"],
            interval=params["interval_seconds"],
            factory=factory,
            base_port=params["base_port"]
        )

        # 3. Sauvegarder les 4 matrices sur le disque
        factory.save_to_file(matrix, job_id)

        # 4. Enregistrer les métadonnées des services en base
        for service in services:
            metadata = ServiceMetadata(
                job_id=job_id,
                service_name=service['nom'],
                url_cpu=service['url_cpu'],
                url_ram=service['url_ram'],
                url_lat=service.get('url_lat', '/actuator/health'),   # ← NOUVEAU
                url_bw=service.get('url_bw', '/actuator/health'),     # ← NOUVEAU
                transactions_target=service['transactions'],
                cpu_file=f"M_CPU_{job_id}.npy",
                ram_file=f"M_RAM_{job_id}.npy",
                lat_file=f"M_LAT_{job_id}.npy",     # ← NOUVEAU
                bw_file=f"M_BW_{job_id}.npy"        # ← NOUVEAU
            )
            db.add(metadata)

        # 5. Mettre à jour le statut du job
        job.status = "completed"
        job.completed_at = datetime.now()
        db.commit()

        return CollectResponse(
            status="success",
            message="Collecte terminée avec succès",
            timestamp=job_id,
            job_id=job_id,
            shape={
                "services": matrix.n_services,
                "samples": matrix.n_samples
            },
            load_enabled=params["load_enabled"],
        )

    except Exception as e:
        logger.error(f"Erreur lors de la collecte: {e}", exc_info=True)
        job = db.query(CollectionJob).filter(CollectionJob.job_id == job_id).first()
        if job:
            job.status = "failed"
            job.error_message = str(e)
            db.commit()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/jobs")
async def list_jobs(db: Session = Depends(get_db)):
    """Liste tous les jobs de collecte."""
    jobs = db.query(CollectionJob).order_by(CollectionJob.started_at.desc()).all()
    return {
        "jobs": [
            {
                "job_id": j.job_id,
                "status": j.status,
                "services": j.n_services,
                "samples": j.n_samples,
                "started_at": j.started_at.isoformat() if j.started_at else None,
                "completed_at": j.completed_at.isoformat() if j.completed_at else None
            }
            for j in jobs
        ]
    }


@app.get("/api/v1/jobs/{job_id}")
async def get_job(job_id: str, db: Session = Depends(get_db)):
    """Récupère les détails d'un job."""
    job = db.query(CollectionJob).filter(CollectionJob.job_id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job non trouvé")
    
    services = db.query(ServiceMetadata).filter(ServiceMetadata.job_id == job_id).all()
    
    return {
        "job": {
            "job_id": job.job_id,
            "status": job.status,
            "duration_seconds": job.duration_seconds,
            "interval_seconds": job.interval_seconds,
            "n_services": job.n_services,
            "n_samples": job.n_samples,
            "base_port": job.base_port,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "error_message": job.error_message
        },
        "services": [
            {
                "name": s.service_name,
                "url_cpu": s.url_cpu,
                "url_ram": s.url_ram,
                "url_lat": s.url_lat,      # ← NOUVEAU
                "url_bw": s.url_bw,        # ← NOUVEAU
                "transactions_target": s.transactions_target
            }
            for s in services
        ]
    }


@app.get("/api/v1/list")
async def list_collections():
    """Liste toutes les collections disponibles (fichiers)."""
    collections = storage.list_collections()
    return {"collections": collections}


@app.get("/api/v1/status/{job_id}")
async def get_status(job_id: str):
    """Récupère le statut d'une collection à partir des fichiers."""
    try:
        # Charger les 4 matrices
        M_CPU, M_RAM, M_LAT, M_BW, services = storage.load_matrices(job_id)
        return {
            "job_id": job_id,
            "status": "completed",
            "services": services,
            "n_services": len(services),
            "n_samples": M_CPU.shape[1],
            "matrices": {
                "cpu": M_CPU.shape,
                "ram": M_RAM.shape,
                "lat": M_LAT.shape,
                "bw": M_BW.shape
            }
        }
    except FileNotFoundError:
        return {
            "job_id": job_id,
            "status": "not_found",
            "message": "Collection non trouvée"
        }


@app.delete("/api/v1/delete/{job_id}")
async def delete_collection(job_id: str, db: Session = Depends(get_db)):
    """Supprime une collection (fichiers et base de données)."""
    # Supprimer les entrées en base
    db.query(ServiceMetadata).filter(ServiceMetadata.job_id == job_id).delete()
    db.query(CollectionJob).filter(CollectionJob.job_id == job_id).delete()
    db.commit()
    
    # Supprimer les fichiers
    success = storage.delete_collection(job_id)
    if success:
        return {"status": "success", "message": f"Collection {job_id} supprimée"}
    else:
        return {"status": "partial", "message": f"Collection {job_id} supprimée de la DB mais fichiers non trouvés"}


# --- Frontend (optionnel) ---
STATIC_DIR = FRONTEND_DIR / "static"
INDEX_FILE = FRONTEND_DIR / "index.html"

if STATIC_DIR.exists() and INDEX_FILE.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    async def serve_frontend():
        return FileResponse(str(INDEX_FILE))

    logger.info("Frontend servi depuis %s", FRONTEND_DIR)
else:
    logger.warning("Frontend non disponible (%s)", FRONTEND_DIR)


# --- Point d'entrée ---
def run():
    """Lance le serveur."""
    port = int(os.getenv("SERVICE_PORT", 8001))
    uvicorn.run(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    run()