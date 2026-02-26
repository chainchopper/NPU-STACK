"""Database models and connection for NPU-STACK."""

import os
from datetime import datetime, timezone
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, JSON
from sqlalchemy.orm import declarative_base, sessionmaker, Session

DATABASE_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DATABASE_DIR, exist_ok=True)
DATABASE_URL = f"sqlite:///{os.path.join(DATABASE_DIR, 'npu_stack.db')}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def utcnow():
    return datetime.now(timezone.utc)


class ModelRecord(Base):
    """Registered ML model metadata."""
    __tablename__ = "models"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(255), nullable=False, index=True)
    framework = Column(String(50), nullable=False)  # pytorch, onnx, openvino, tflite
    format = Column(String(50), nullable=False)  # .pt, .onnx, .xml, .tflite
    file_path = Column(String(1024), nullable=False)
    file_size = Column(Integer, default=0)  # bytes
    input_shape = Column(String(255), nullable=True)
    output_shape = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    architecture = Column(String(100), nullable=True)
    quant_type = Column(String(50), nullable=True)
    size_mb = Column(Float, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class TrainingJob(Base):
    """Training job tracking."""
    __tablename__ = "training_jobs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    status = Column(String(50), default="pending")  # pending, running, completed, failed, stopped
    architecture = Column(String(100), nullable=False)
    dataset = Column(String(100), nullable=False)
    config = Column(JSON, nullable=True)  # hyperparameters
    current_epoch = Column(Integer, default=0)
    total_epochs = Column(Integer, default=10)
    train_loss = Column(Float, nullable=True)
    train_accuracy = Column(Float, nullable=True)
    val_loss = Column(Float, nullable=True)
    val_accuracy = Column(Float, nullable=True)
    metrics_history = Column(JSON, nullable=True)  # per-epoch metrics
    model_id = Column(Integer, nullable=True)  # resulting model
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)


class BenchmarkResult(Base):
    """Inference benchmark results."""
    __tablename__ = "benchmark_results"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    model_id = Column(Integer, nullable=False)
    model_name = Column(String(255), nullable=False)
    device = Column(String(50), nullable=False)  # cpu, npu, cuda
    runtime = Column(String(50), nullable=False)  # onnxruntime, openvino
    precision = Column(String(20), nullable=True)  # fp32, fp16, int8, int4
    batch_size = Column(Integer, default=1)
    warmup_runs = Column(Integer, default=10)
    num_iterations = Column(Integer, default=100)
    latency_mean_ms = Column(Float, nullable=True)
    latency_p50_ms = Column(Float, nullable=True)
    latency_p95_ms = Column(Float, nullable=True)
    latency_p99_ms = Column(Float, nullable=True)
    throughput_fps = Column(Float, nullable=True)
    memory_peak_mb = Column(Float, nullable=True)
    created_at = Column(DateTime, default=utcnow)


def init_db():
    """Create all tables."""
    Base.metadata.create_all(bind=engine)


def get_db() -> Session:
    """Dependency to get DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
