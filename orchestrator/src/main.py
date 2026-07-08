import os
import logging
import requests
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Auth-Scaler Orchestrator",
    description="Orchestrates all phases of the Auth-Scaler framework",
    version="1.0.0"
)

COLLECTOR_URL = os.getenv("COLLECTOR_URL", "http://phase1-collector:8001")
PREDICTOR_URL = os.getenv("PREDICTOR_URL", "http://phase2-predictor:8002")
OPTIMIZER_URL = os.getenv("OPTIMIZER_URL", "http://phase3-optimizer:8003")
DEPLOYER_URL = os.getenv("DEPLOYER_URL", "http://phase4-deployer:8004")
REPORTER_URL = os.getenv("REPORTER_URL", "http://phase5-reporter:8005")

class PipelineRequest(BaseModel):
    job_id: Optional[str] = None

class PipelineResponse(BaseModel):
    status: str
    job_id: str
    phases: dict
    error: Optional[str] = None

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "orchestrator"}

@app.post("/api/v1/run", response_model=PipelineResponse)
async def run_pipeline(request: PipelineRequest, background_tasks: BackgroundTasks):
    job_id = request.job_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    background_tasks.add_task(execute_pipeline, job_id)
    return PipelineResponse(
        status="running",
        job_id=job_id,
        phases={}
    )

async def execute_pipeline(job_id: str):
    phases = {}
    try:
        logger.info(f"Starting Auth-Scaler pipeline {job_id}")
        
        # Phase 1
        logger.info("Phase 1: Collecting metrics...")
        resp1 = requests.post(
            f"{COLLECTOR_URL}/api/v1/collect",
            json={
                "prometheus_url": "http://prometheus:9090",
                "services": [
                    {"name": "order-service"},
                    {"name": "payment-service"},
                    {"name": "notification-service"}
                ],
                "duration_seconds": 30,
                "interval_seconds": 5,
                "job_id": job_id
            }
        )
        phases["phase1"] = resp1.json()
        logger.info(f"Phase 1: {phases['phase1']}")
        
        # Phase 2
        logger.info("Phase 2: Running predictions...")
        resp2 = requests.post(
            f"{PREDICTOR_URL}/api/v1/predict",
            json={"timestamp": job_id}
        )
        phases["phase2"] = resp2.json()
        logger.info(f"Phase 2: {phases['phase2']}")
        
        # Phase 3
        logger.info("Phase 3: Running PSO optimization...")
        resp3 = requests.post(
            f"{OPTIMIZER_URL}/api/v1/optimize",
            json={"timestamp": job_id}
        )
        phases["phase3"] = resp3.json()
        logger.info(f"Phase 3: {phases['phase3']}")
        
        # Phase 4
        logger.info("Phase 4: Generating deployment...")
        resp4 = requests.post(
            f"{DEPLOYER_URL}/api/v1/generate",
            json={"timestamp": job_id}
        )
        phases["phase4"] = resp4.json()
        logger.info(f"Phase 4: {phases['phase4']}")
        
        # Phase 5
        logger.info("Phase 5: Generating report...")
        resp5 = requests.post(
            f"{REPORTER_URL}/api/v1/report",
            json={"timestamp": job_id}
        )
        phases["phase5"] = resp5.json()
        logger.info(f"Phase 5: {phases['phase5']}")
        
        logger.info(f"Pipeline {job_id} completed successfully!")
        
    except Exception as e:
        logger.error(f"Pipeline {job_id} failed: {e}")
