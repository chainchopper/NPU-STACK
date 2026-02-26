"""Asset Management Router — Pre-bundled models, datasets, and benchmarks.

Provides API endpoints for the model registry, LiteRT integration,
and on-demand asset downloads from the NPU-STACK GitHub repo.
"""

import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Form

router = APIRouter(prefix="/api/assets", tags=["assets"])


# ── Catalog ─────────────────────────────────────────────

@router.get("/catalog")
def get_catalog(branch: str = "all"):
    """Get the full model/dataset/benchmark catalog."""
    from services.model_registry import get_catalog
    return get_catalog(branch)


@router.get("/catalog/models")
def get_models(
    branch: str = "all",
    task: Optional[str] = None,
    format: Optional[str] = None,
):
    """List available models, optionally filtered by task or format."""
    from services.model_registry import get_catalog
    catalog = get_catalog(branch)
    models = catalog["models"]

    if task:
        models = [m for m in models if m.get("task") == task]
    if format:
        models = [m for m in models if m.get("format") == format]

    return {"models": models, "total": len(models)}


@router.get("/catalog/datasets")
def get_datasets():
    """List available datasets."""
    from services.model_registry import DATASET_CATALOG
    return {"datasets": DATASET_CATALOG, "total": len(DATASET_CATALOG)}


@router.get("/catalog/benchmarks")
def get_benchmarks():
    """List available benchmark data."""
    from services.model_registry import BENCHMARK_CATALOG
    return {"benchmarks": BENCHMARK_CATALOG, "total": len(BENCHMARK_CATALOG)}


# ── Downloads ───────────────────────────────────────────

@router.post("/download/model")
def download_model(
    model_id: str = Form(...),
    force: bool = Form(False),
):
    """Download a specific model from the catalog."""
    from services.model_registry import download_bundled_model
    result = download_bundled_model(model_id, force=force)
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "Download failed"))
    return result


@router.post("/download/branch")
def download_branch_models(branch: str = Form("main")):
    """Download all models for a branch (main or dev)."""
    from services.model_registry import download_all_for_branch
    return download_all_for_branch(branch)


@router.post("/download/dataset")
def download_dataset(dataset_id: str = Form(...)):
    """Download a dataset from the catalog."""
    from services.model_registry import download_dataset as dl_dataset
    result = dl_dataset(dataset_id)
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "Download failed"))
    return result


# ── Local Assets ────────────────────────────────────────

@router.get("/local")
def list_local_assets():
    """List all locally downloaded assets."""
    from services.model_registry import get_local_assets
    return get_local_assets()


# ── LiteRT / TFLite ─────────────────────────────────────

@router.get("/litert/info")
def get_litert_info():
    """Detect LiteRT / TFLite ecosystem and capabilities."""
    from services.litert_service import detect_litert
    return detect_litert()


@router.post("/litert/convert")
def convert_to_tflite(
    model_path: str = Form(...),
    output_name: Optional[str] = Form(None),
):
    """Convert a PyTorch model to TFLite using litert-torch."""
    from services.litert_service import convert_pytorch_to_tflite
    output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "models")
    result = convert_pytorch_to_tflite(model_path, output_dir, output_name)
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "Conversion failed"))
    return result


@router.post("/litert/inspect")
def inspect_tflite_model(model_path: str = Form(...)):
    """Get metadata and structure from a TFLite model."""
    from services.litert_service import get_tflite_model_info
    result = get_tflite_model_info(model_path)
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "Inspection failed"))
    return result
