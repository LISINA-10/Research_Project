import os
import logging
from fastapi import FastAPI, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from datetime import datetime
from pydantic import BaseModel
from typing import List, Optional
import uvicorn
from sqlalchemy.orm import Session

from .collector_actuator import ActuatorCollector 
from .models.matrix_factory import MatrixFactory
from .storage import StorageManager
from .database import get_db, init_db
from .database.models import CollectionJob, ServiceMetadata

# Configuration des logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Initialisation de l'application ---
app = FastAPI(
    title="Auth-Scaler Phase 1: Metrics Collection",
    description="Collecte les métriques CPU, RAM, Latence et Débit via Actuator",
    version="1.0.0"
)

# --- Initialisation des composants ---
collector = ActuatorCollector()  
factory = MatrixFactory()
storage = StorageManager()

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
    services: List[ServiceInput]
    duration_seconds: int
    interval_seconds: int
    job_id: Optional[str] = None
    base_port: int = 8080

class CollectResponse(BaseModel):
    status: str
    message: str
    timestamp: str
    job_id: str
    shape: dict

# --- Endpoints API ---
@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "phase1-collector",
        "mode": "actuator"
    }

@app.post("/api/v1/collect", response_model=CollectResponse)
async def collect(request: CollectRequest, db: Session = Depends(get_db)):
    """
    Lance la collecte des métriques depuis les URLs fournies.
    Collecte : CPU, RAM, Latence, Débit
    """
    job_id = request.job_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    logger.info(f"📊 Démarrage collecte: {job_id}")

    try:
        # 1. Créer l'entrée dans la base de données
        job = CollectionJob(
            job_id=job_id,
            status="running",
            duration_seconds=request.duration_seconds,
            interval_seconds=request.interval_seconds,
            n_services=len(request.services),
            n_samples=int(request.duration_seconds / request.interval_seconds),
            base_port=request.base_port,
            started_at=datetime.now()
        )
        db.add(job)
        db.commit()

        # 2. Collecter les métriques (CPU, RAM, LAT, BW)
        services = [s.dict() for s in request.services]
        logger.info(f"  Services: {[s['nom'] for s in services]}")

        matrix = collector.collect(
            services=services,
            duration=request.duration_seconds,
            interval=request.interval_seconds,
            factory=factory,
            base_port=request.base_port
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
            }
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
try:
    app.mount("/static", StaticFiles(directory="../frontend/static"), name="static")
    
    @app.get("/")
    async def serve_frontend():
        return FileResponse("../frontend/index.html")
    
    logger.info("Frontend servi depuis /")
except Exception as e:
    logger.warning(f"Frontend non disponible: {e}")


# --- Point d'entrée ---
def run():
    """Lance le serveur."""
    port = int(os.getenv("SERVICE_PORT", 8001))
    uvicorn.run(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    run()