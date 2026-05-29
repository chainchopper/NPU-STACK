"""NPU-STACK Backend — FastAPI server for NPU/TPU model development platform."""

import os
import sys

# Disable hf_transfer globally to prevent Windows I/O cache errors during model downloads
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"
# Disable symlinks warning on Windows for non-admin users
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

# Load environment variables from .env
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
except ImportError:
    pass

# Ensure HF cache and home are in a safe place inside the project to avoid Windows path/permission errors
base_data_dir = os.path.join(os.path.dirname(__file__), "data")
if not os.getenv("HF_HOME"):
    os.environ["HF_HOME"] = os.path.join(base_data_dir, "hf_home")
if not os.getenv("HUGGINGFACE_HUB_CACHE"):
    os.environ["HUGGINGFACE_HUB_CACHE"] = os.path.join(base_data_dir, "hf_cache")

# Suppress Xet-core logging errors on Windows (often tries to write to H:\ or D:\)
os.environ["XET_LOG_LEVEL"] = "off"
if not os.getenv("XET_TMP_DIR"):
    os.environ["XET_TMP_DIR"] = os.path.join(base_data_dir, "xet_tmp")
    os.makedirs(os.environ["XET_TMP_DIR"], exist_ok=True)

from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Ensure backend directory is importable
sys.path.insert(0, os.path.dirname(__file__))

from database import init_db
from routers.models import router as models_router
from routers.training import router as training_router, training_ws_endpoint
from routers.conversion import router as conversion_router
from routers.benchmark import router as benchmark_router
from routers.inference import router as inference_router
from routers.huggingface import router as huggingface_router
from routers.datasets import router as datasets_router
from routers.serving import router as serving_router
from routers.finetuning import router as finetuning_router
from routers.scanner import router as scanner_router
from routers.webcam import router as webcam_router
from routers.filebrowser import router as filebrowser_router
from routers.ingest import router as ingest_router
from routers.assets import router as assets_router
from routers.gguf_pipeline import router as gguf_pipeline_router
from routers.finetune_publish import router as finetune_publish_router
from routers.nim import router as nim_router
from routers.cvedia import router as cvedia_router
from routers.vitis_compiler import router as vitis_compiler_router
from routers.agent import router as agent_router
from routers.civitai import router as civitai_router
from routers.flm import router as flm_router
from routers.devices import router as devices_router

# Create directories
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
MODEL_STORE = os.path.join(DATA_DIR, "models")
os.makedirs(MODEL_STORE, exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "datasets"), exist_ok=True)

DEFAULT_BACKEND_PORT = int(os.getenv("NPU_STACK_BACKEND_PORT", "8010"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Modern lifespan handler — replaces deprecated on_event('startup')."""
    init_db()
    backend_port = int(os.getenv("NPU_STACK_BACKEND_PORT", str(DEFAULT_BACKEND_PORT)))
    print("=" * 60)
    print("  NPU-STACK Backend Server")
    print(f"  API Docs:    http://localhost:{backend_port}/api/docs")
    print(f"  OpenAI API:  http://localhost:{backend_port}/v1")
    print("=" * 60)
    yield  # App runs here
    print("NPU-STACK Backend shutting down...")


app = FastAPI(
    title="NPU-STACK API",
    description="Full-stack platform for training, converting, quantizing, and benchmarking ML models on NPU/TPU hardware.",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    lifespan=lifespan,
)

# CORS — allow frontend origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global exception handler to ensure CORS headers are returned on 500 errors
from fastapi.responses import JSONResponse
from fastapi import Request

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch unhandled exceptions and return a proper JSON 500 with CORS headers."""
    import traceback
    traceback.print_exc()
    response = JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
    )
    # Manually add CORS headers because middleware doesn't run for custom handlers in some versions
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "*"
    return response

# Include routers
app.include_router(models_router)
app.include_router(training_router)
app.include_router(conversion_router)
app.include_router(benchmark_router)
app.include_router(inference_router)
app.include_router(huggingface_router)
app.include_router(datasets_router)
app.include_router(serving_router)
app.include_router(finetuning_router)
app.include_router(scanner_router)
app.include_router(webcam_router)
app.include_router(filebrowser_router)
app.include_router(ingest_router)
app.include_router(assets_router)
app.include_router(gguf_pipeline_router)
app.include_router(finetune_publish_router)
app.include_router(nim_router)
app.include_router(cvedia_router)
app.include_router(vitis_compiler_router)
app.include_router(devices_router)
app.include_router(agent_router)
app.include_router(civitai_router)
app.include_router(flm_router)


@app.get("/api/health")
def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "npu-stack-backend",
        "version": "1.0.0",
    }


@app.get("/api/status")
def system_status():
    """Get system status including model and job counts."""
    from database import SessionLocal, ModelRecord, TrainingJob, BenchmarkResult

    db = SessionLocal()
    try:
        model_count = db.query(ModelRecord).count()
        job_count = db.query(TrainingJob).count()
        running_jobs = db.query(TrainingJob).filter(TrainingJob.status == "running").count()
        benchmark_count = db.query(BenchmarkResult).count()

        return {
            "models": model_count,
            "training_jobs": job_count,
            "running_jobs": running_jobs,
            "benchmarks": benchmark_count,
        }
    finally:
        db.close()


@app.post("/api/v1/sentinel/push")
async def sentinel_push_ack(payload: dict | None = None):
    """Acknowledge external sentinel pushes so noisy integrations stop generating 404s."""
    return {
        "status": "acknowledged",
        "received": bool(payload),
        "message": "Sentinel push accepted by NPU-STACK.",
    }


# WebSocket endpoint for training progress
@app.websocket("/ws/training/{job_id}")
async def ws_training(websocket: WebSocket, job_id: int):
    await training_ws_endpoint(websocket, job_id)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=DEFAULT_BACKEND_PORT,
        reload=True,
        reload_dirs=[os.path.dirname(__file__)],
    )
