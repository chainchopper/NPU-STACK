"""Training router — launch and manage training jobs with real-time WebSocket progress."""

import asyncio
import os
from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db, TrainingJob, ModelRecord, SessionLocal
from services.training_service import run_training, stop_training

router = APIRouter(prefix="/api/training", tags=["training"])

MODEL_STORE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "models")

# WebSocket connections per job
_ws_connections: dict[int, list[WebSocket]] = {}


class TrainingConfig(BaseModel):
    name: str = Field(..., description="Job name")
    architecture: str = Field("simple_cnn", description="Model architecture: simple_cnn, resnet18, mobilenet_v2, efficientnet_b0")
    dataset: str = Field("cifar10", description="Dataset: mnist, fashion_mnist, cifar10")
    epochs: int = Field(10, ge=1, le=500)
    batch_size: int = Field(64, ge=1, le=512)
    learning_rate: float = Field(0.001, gt=0, le=1)
    optimizer: str = Field("adam", description="Optimizer: adam, sgd, adamw")
    weight_decay: float = Field(1e-4, ge=0)


async def _broadcast_to_job(job_id: int, data: dict):
    """Broadcast a message to all WebSocket clients watching a job."""
    import json
    connections = _ws_connections.get(job_id, [])
    dead = []
    for ws in connections:
        try:
            await ws.send_text(json.dumps(data))
        except Exception:
            dead.append(ws)
    for ws in dead:
        connections.remove(ws)


@router.post("/start")
async def start_training(config: TrainingConfig, db: Session = Depends(get_db)):
    """Launch a new training job."""
    # Create job record
    job = TrainingJob(
        name=config.name,
        architecture=config.architecture,
        dataset=config.dataset,
        status="pending",
        total_epochs=config.epochs,
        config={
            "batch_size": config.batch_size,
            "learning_rate": config.learning_rate,
            "optimizer": config.optimizer,
            "weight_decay": config.weight_decay,
        },
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    job_id = job.id

    # Start training in background
    async def _run():
        result = await run_training(
            job_id=job_id,
            architecture=config.architecture,
            dataset_name=config.dataset,
            epochs=config.epochs,
            batch_size=config.batch_size,
            learning_rate=config.learning_rate,
            optimizer_name=config.optimizer,
            weight_decay=config.weight_decay,
            db_session_factory=SessionLocal,
            broadcast_fn=_broadcast_to_job,
        )

        # Register the output model if training succeeded
        if result and result.get("onnx_path"):
            reg_db = SessionLocal()
            try:
                onnx_path = result["onnx_path"]
                model_record = ModelRecord(
                    name=f"{config.name} (ONNX)",
                    framework="onnx",
                    format="onnx",
                    file_path=onnx_path,
                    file_size=result.get("file_size", 0),
                    description=f"Auto-exported from training job {job_id}",
                )
                reg_db.add(model_record)
                reg_db.commit()
                reg_db.refresh(model_record)

                # Update job with model ID
                j = reg_db.query(TrainingJob).filter(TrainingJob.id == job_id).first()
                if j:
                    j.model_id = model_record.id
                    reg_db.commit()
            finally:
                reg_db.close()

    asyncio.create_task(_run())

    return {
        "job_id": job_id,
        "status": "pending",
        "message": f"Training job {job_id} created. Connect to /ws/training/{job_id} for real-time updates.",
    }


@router.get("/jobs")
def list_jobs(status: Optional[str] = None, db: Session = Depends(get_db)):
    """List all training jobs."""
    query = db.query(TrainingJob)
    if status:
        query = query.filter(TrainingJob.status == status)
    jobs = query.order_by(TrainingJob.created_at.desc()).all()

    return [
        {
            "id": j.id,
            "name": j.name,
            "status": j.status,
            "architecture": j.architecture,
            "dataset": j.dataset,
            "current_epoch": j.current_epoch,
            "total_epochs": j.total_epochs,
            "train_loss": j.train_loss,
            "train_accuracy": j.train_accuracy,
            "val_loss": j.val_loss,
            "val_accuracy": j.val_accuracy,
            "model_id": j.model_id,
            "created_at": str(j.created_at),
        }
        for j in jobs
    ]


@router.get("/jobs/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db)):
    """Get training job details."""
    job = db.query(TrainingJob).filter(TrainingJob.id == job_id).first()
    if not job:
        raise HTTPException(404, "Job not found")

    return {
        "id": job.id,
        "name": job.name,
        "status": job.status,
        "architecture": job.architecture,
        "dataset": job.dataset,
        "config": job.config,
        "current_epoch": job.current_epoch,
        "total_epochs": job.total_epochs,
        "train_loss": job.train_loss,
        "train_accuracy": job.train_accuracy,
        "val_loss": job.val_loss,
        "val_accuracy": job.val_accuracy,
        "metrics_history": job.metrics_history,
        "model_id": job.model_id,
        "error_message": job.error_message,
        "started_at": str(job.started_at) if job.started_at else None,
        "completed_at": str(job.completed_at) if job.completed_at else None,
        "created_at": str(job.created_at),
    }


@router.post("/jobs/{job_id}/stop")
def stop_job(job_id: int, db: Session = Depends(get_db)):
    """Stop a running training job."""
    job = db.query(TrainingJob).filter(TrainingJob.id == job_id).first()
    if not job:
        raise HTTPException(404, "Job not found")
    if job.status != "running":
        raise HTTPException(400, f"Job is not running (status: {job.status})")

    success = stop_training(job_id)
    if success:
        return {"message": f"Stop signal sent to job {job_id}"}
    else:
        raise HTTPException(400, "Job not found in active training tasks")


# WebSocket endpoint is registered in main.py
async def training_ws_endpoint(websocket: WebSocket, job_id: int):
    """WebSocket endpoint for real-time training progress."""
    await websocket.accept()

    if job_id not in _ws_connections:
        _ws_connections[job_id] = []
    _ws_connections[job_id].append(websocket)

    try:
        while True:
            # Keep connection alive; client can also send commands
            data = await websocket.receive_text()
            if data == "stop":
                stop_training(job_id)
    except WebSocketDisconnect:
        pass
    finally:
        if job_id in _ws_connections:
            try:
                _ws_connections[job_id].remove(websocket)
            except ValueError:
                pass
