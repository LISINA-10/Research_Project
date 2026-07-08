from sqlalchemy import Column, Integer, String, Float, DateTime, Text, JSON, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from .connection import Base


class CollectionJob(Base):
    """Stocke les informations sur une collecte."""
    __tablename__ = "collection_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(100), unique=True, nullable=False, index=True)
    status = Column(String(50), default="pending")  # pending, running, completed, failed
    duration_seconds = Column(Integer)
    interval_seconds = Column(Integer)
    n_services = Column(Integer)
    n_samples = Column(Integer)
    base_port = Column(Integer, default=8080)
    started_at = Column(DateTime, default=datetime.now)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    
    # Relation avec les services
    services = relationship("ServiceMetadata", back_populates="job", cascade="all, delete-orphan")


class ServiceMetadata(Base):
    """Stocke les métadonnées des services pour une collecte."""
    __tablename__ = "service_metadata"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(100), ForeignKey("collection_jobs.job_id"), nullable=False, index=True)
    service_name = Column(String(200), nullable=False)
    url_cpu = Column(String(500), nullable=False)
    url_ram = Column(String(500), nullable=False)
    transactions_target = Column(Integer, default=0)
    cpu_file = Column(String(500), nullable=True)   # Chemin du fichier .npy
    ram_file = Column(String(500), nullable=True)   # Chemin du fichier .npy
    
    # Relation inverse
    job = relationship("CollectionJob", back_populates="services")