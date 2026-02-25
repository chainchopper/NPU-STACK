"""Benchmark router — run and compare model inference benchmarks."""

import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db, ModelRecord, BenchmarkResult
from services.benchmark_service import (
    benchmark_onnxruntime,
    benchmark_openvino,
    get_system_info,
)

router = APIRouter(prefix="/api/benchmark", tags=["benchmark"])


class BenchmarkRequest(BaseModel):
    model_id: int = Field(..., description="Model ID to benchmark")
    runtime: str = Field("onnxruntime", description="Runtime: onnxruntime, openvino")
    device: str = Field("cpu", description="Device: cpu, npu, cuda, auto")
    batch_size: int = Field(1, ge=1, le=64)
    warmup_runs: int = Field(10, ge=0, le=100)
    num_iterations: int = Field(100, ge=10, le=10000)


@router.post("/run")
def run_benchmark(req: BenchmarkRequest, db: Session = Depends(get_db)):
    """Run an inference benchmark on a model."""
    record = db.query(ModelRecord).filter(ModelRecord.id == req.model_id).first()
    if not record:
        raise HTTPException(404, "Model not found")

    if not os.path.exists(record.file_path):
        raise HTTPException(404, "Model file not found on disk")

    try:
        if req.runtime == "onnxruntime":
            if record.format not in ("onnx",):
                raise HTTPException(400, "ONNX Runtime requires an ONNX model")

            result = benchmark_onnxruntime(
                model_path=record.file_path,
                device=req.device,
                batch_size=req.batch_size,
                warmup_runs=req.warmup_runs,
                num_iterations=req.num_iterations,
            )

        elif req.runtime == "openvino":
            if record.format not in ("onnx", "openvino_ir"):
                raise HTTPException(400, "OpenVINO requires ONNX or OpenVINO IR model")

            result = benchmark_openvino(
                model_path=record.file_path,
                device=req.device,
                batch_size=req.batch_size,
                warmup_runs=req.warmup_runs,
                num_iterations=req.num_iterations,
            )
        else:
            raise HTTPException(400, f"Unsupported runtime: {req.runtime}")

        # Detect precision from model name
        precision = "fp32"
        name_lower = record.name.lower()
        if "int4" in name_lower or "nncf_int4" in name_lower:
            precision = "int4"
        elif "int8" in name_lower or "quantized" in name_lower:
            precision = "int8"
        elif "fp16" in name_lower:
            precision = "fp16"

        # Store result in DB
        bench = BenchmarkResult(
            model_id=record.id,
            model_name=record.name,
            device=result.get("device", req.device),
            runtime=req.runtime,
            precision=precision,
            batch_size=req.batch_size,
            warmup_runs=req.warmup_runs,
            num_iterations=req.num_iterations,
            latency_mean_ms=result.get("latency_mean_ms"),
            latency_p50_ms=result.get("latency_p50_ms"),
            latency_p95_ms=result.get("latency_p95_ms"),
            latency_p99_ms=result.get("latency_p99_ms"),
            throughput_fps=result.get("throughput_fps"),
            memory_peak_mb=result.get("memory_peak_mb"),
        )
        db.add(bench)
        db.commit()
        db.refresh(bench)

        return {
            "benchmark_id": bench.id,
            "model": record.name,
            **result,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Benchmark failed: {str(e)}")


@router.get("/results")
def list_results(
    model_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """List benchmark results."""
    query = db.query(BenchmarkResult)
    if model_id:
        query = query.filter(BenchmarkResult.model_id == model_id)
    results = query.order_by(BenchmarkResult.created_at.desc()).all()

    return [
        {
            "id": r.id,
            "model_id": r.model_id,
            "model_name": r.model_name,
            "device": r.device,
            "runtime": r.runtime,
            "precision": r.precision,
            "batch_size": r.batch_size,
            "latency_mean_ms": r.latency_mean_ms,
            "latency_p50_ms": r.latency_p50_ms,
            "latency_p95_ms": r.latency_p95_ms,
            "latency_p99_ms": r.latency_p99_ms,
            "throughput_fps": r.throughput_fps,
            "memory_peak_mb": r.memory_peak_mb,
            "created_at": str(r.created_at),
        }
        for r in results
    ]


@router.get("/compare")
def compare_benchmarks(
    ids: str = "",
    db: Session = Depends(get_db),
):
    """Compare benchmark results by IDs (comma-separated)."""
    if not ids:
        raise HTTPException(400, "Provide benchmark IDs as comma-separated 'ids' param")

    try:
        id_list = [int(x.strip()) for x in ids.split(",")]
    except ValueError:
        raise HTTPException(400, "Invalid ID format")

    results = db.query(BenchmarkResult).filter(BenchmarkResult.id.in_(id_list)).all()
    if not results:
        raise HTTPException(404, "No benchmark results found")

    return {
        "comparisons": [
            {
                "id": r.id,
                "model_name": r.model_name,
                "device": r.device,
                "runtime": r.runtime,
                "precision": r.precision,
                "latency_mean_ms": r.latency_mean_ms,
                "latency_p95_ms": r.latency_p95_ms,
                "throughput_fps": r.throughput_fps,
                "memory_peak_mb": r.memory_peak_mb,
            }
            for r in results
        ]
    }


@router.get("/system-info")
def system_info():
    """Get system hardware capabilities for NPU/TPU detection."""
    return get_system_info()
