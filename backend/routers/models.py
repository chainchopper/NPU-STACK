"""Models router — CRUD for model registry with file upload/download."""

import os
import shutil
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db, ModelRecord
from services.conversion_service import get_onnx_model_info

router = APIRouter(prefix="/api/models", tags=["models"])

MODEL_STORE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "models")
os.makedirs(MODEL_STORE, exist_ok=True)


def _detect_framework(filename: str) -> tuple[str, str]:
    """Detect framework and format from filename."""
    ext = os.path.splitext(filename)[1].lower()
    mapping = {
        ".gguf": ("llama.cpp", "gguf"),
        ".onnx": ("onnx", "onnx"),
        ".pt": ("pytorch", "pt"),
        ".pth": ("pytorch", "pth"),
        ".safetensors": ("pytorch", "safetensors"),
        ".xml": ("openvino", "openvino_ir"),
        ".tflite": ("tflite", "tflite"),
        ".pb": ("tensorflow", "saved_model"),
    }
    return mapping.get(ext, ("unknown", ext.lstrip(".")))


def _detect_quant(filename: str) -> Optional[str]:
    """Detect quantization level from filename."""
    name_lower = filename.lower()
    quants = [
        "q2_k", "q3_k_s", "q3_k_m", "q3_k_l",
        "q4_0", "q4_1", "q4_k_s", "q4_k_m",
        "q5_0", "q5_1", "q5_k_s", "q5_k_m",
        "q6_k", "q8_0", "f16", "f32",
        "iq1_s", "iq2_xxs", "iq2_xs", "iq3_xxs", "iq4_nl",
    ]
    for q in quants:
        if q in name_lower:
            return q.upper()
    return None


@router.post("/upload")
async def upload_model(
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """Upload a model file to the registry."""
    if not file.filename:
        raise HTTPException(400, "No filename")

    framework, fmt = _detect_framework(file.filename)
    model_name = name or os.path.splitext(file.filename)[0]

    # Save file
    safe_filename = file.filename.replace(" ", "_")
    file_path = os.path.join(MODEL_STORE, safe_filename)
    counter = 1
    while os.path.exists(file_path):
        base, ext = os.path.splitext(safe_filename)
        file_path = os.path.join(MODEL_STORE, f"{base}_{counter}{ext}")
        counter += 1

    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    file_size = os.path.getsize(file_path)

    # Get model metadata if ONNX
    metadata = None
    input_shape = None
    output_shape = None
    if fmt == "onnx":
        try:
            info = get_onnx_model_info(file_path)
            metadata = info
            if info.get("inputs"):
                input_shape = str(info["inputs"][0].get("shape", []))
            if info.get("outputs"):
                output_shape = str(info["outputs"][0].get("shape", []))
        except Exception:
            pass

    record = ModelRecord(
        name=model_name,
        framework=framework,
        format=fmt,
        file_path=file_path,
        file_size=file_size,
        size_mb=file_size / (1024 * 1024),
        quant_type=_detect_quant(os.path.basename(file_path)) if fmt == "gguf" else None,
        input_shape=input_shape,
        output_shape=output_shape,
        description=description,
        metadata_json=metadata,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return {
        "id": record.id,
        "name": record.name,
        "framework": record.framework,
        "format": record.format,
        "file_size": record.file_size,
        "input_shape": record.input_shape,
        "output_shape": record.output_shape,
        "metadata": record.metadata_json,
        "created_at": str(record.created_at),
    }


@router.get("")
def list_models(
    framework: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """List all registered models."""
    query = db.query(ModelRecord)
    if framework:
        query = query.filter(ModelRecord.framework == framework)
    records = query.order_by(ModelRecord.created_at.desc()).all()

    return [
        {
            "id": r.id,
            "name": r.name,
            "framework": r.framework,
            "format": r.format,
            "file_size": r.file_size,
            "input_shape": r.input_shape,
            "output_shape": r.output_shape,
            "description": r.description,
            "created_at": str(r.created_at),
        }
        for r in records
    ]


@router.get("/{model_id}")
def get_model(model_id: int, db: Session = Depends(get_db)):
    """Get model details by ID."""
    record = db.query(ModelRecord).filter(ModelRecord.id == model_id).first()
    if not record:
        raise HTTPException(404, "Model not found")

    return {
        "id": record.id,
        "name": record.name,
        "framework": record.framework,
        "format": record.format,
        "file_path": record.file_path,
        "file_size": record.file_size,
        "input_shape": record.input_shape,
        "output_shape": record.output_shape,
        "description": record.description,
        "metadata": record.metadata_json,
        "created_at": str(record.created_at),
        "updated_at": str(record.updated_at),
    }


@router.delete("/{model_id}")
def delete_model(model_id: int, db: Session = Depends(get_db)):
    """Delete a model from the registry and file system."""
    record = db.query(ModelRecord).filter(ModelRecord.id == model_id).first()
    if not record:
        raise HTTPException(404, "Model not found")

    # Delete file
    if os.path.exists(record.file_path):
        os.remove(record.file_path)

    db.delete(record)
    db.commit()
    return {"message": f"Model {model_id} deleted"}


@router.get("/{model_id}/download")
def download_model(model_id: int, db: Session = Depends(get_db)):
    """Download a model file."""
    from fastapi.responses import FileResponse

    record = db.query(ModelRecord).filter(ModelRecord.id == model_id).first()
    if not record:
        raise HTTPException(404, "Model not found")
    if not os.path.exists(record.file_path):
        raise HTTPException(404, "Model file not found on disk")

    return FileResponse(
        record.file_path,
        filename=os.path.basename(record.file_path),
        media_type="application/octet-stream",
    )


@router.post("/huggingface/download")
def download_from_huggingface(
    repo_id: str = Form(...),
    filename: str = Form(None),
    revision: str = Form("main"),
    db: Session = Depends(get_db),
):
    """Download a model from HuggingFace Hub and register it.

    Example: repo_id=microsoft/resnet-50, filename=model.onnx
    """
    try:
        from huggingface_hub import hf_hub_download, list_repo_files
    except ImportError:
        raise HTTPException(500, "huggingface_hub is not installed. Run: pip install huggingface_hub")

    token = os.environ.get("HUGGINGFACE_TOKEN") or None

    try:
        # If no filename specified, find the first ONNX or GGUF file
        if not filename:
            files = list_repo_files(repo_id, revision=revision, token=token)
            for ext in [".gguf", ".onnx", ".safetensors", ".pt", ".pth", ".bin"]:
                matches = [f for f in files if f.endswith(ext)]
                if matches:
                    filename = matches[0]
                    break
            if not filename:
                raise HTTPException(400, f"No model files found in {repo_id}. Available: {files[:20]}")

        # Download directly to MODEL_STORE to bypass the deep caching structure which causes I/O tree errors on Windows
        local_path = hf_hub_download(
            repo_id=repo_id,
            filename=filename,
            revision=revision,
            token=token,
            local_dir=MODEL_STORE,
        )

        # Resolve symlinks — older huggingface_hub versions may return a symlink
        if os.path.islink(local_path):
            real_path = os.path.realpath(local_path)
            if os.path.isfile(real_path):
                local_path = real_path

        # Rename to our safe name if it differs
        safe_name = f"{repo_id.replace('/', '_')}_{os.path.basename(filename)}"
        dest_path = os.path.join(MODEL_STORE, safe_name)

        if os.path.abspath(local_path) != os.path.abspath(dest_path):
            if os.path.exists(dest_path):
                os.remove(dest_path)
            try:
                shutil.move(local_path, dest_path)
            except Exception:
                shutil.copy2(local_path, dest_path)

        # Clean up cache directories left behind by hf_hub_download inside MODEL_STORE
        for cache_dir_name in [".cache", repo_id.split("/")[0] if "/" in repo_id else ""]:
            if cache_dir_name:
                cache_dir_path = os.path.join(MODEL_STORE, cache_dir_name)
                if os.path.isdir(cache_dir_path) and cache_dir_path != MODEL_STORE:
                    shutil.rmtree(cache_dir_path, ignore_errors=True)

        file_size = os.path.getsize(dest_path)
        
        ext = os.path.splitext(filename)[1].lower()
        if ext == ".gguf":
            framework, fmt = "llama.cpp", "gguf"
        else:
            framework, fmt = _detect_framework(filename)

        # Get metadata if ONNX
        metadata = None
        input_shape = None
        output_shape = None
        if fmt == "onnx":
            try:
                info = get_onnx_model_info(dest_path)
                metadata = info
                if info.get("inputs"):
                    input_shape = str(info["inputs"][0].get("shape", []))
                if info.get("outputs"):
                    output_shape = str(info["outputs"][0].get("shape", []))
            except Exception:
                pass

        record = ModelRecord(
            name=f"{repo_id.split('/')[-1]}",
            framework=framework,
            format=fmt,
            file_path=dest_path,
            file_size=file_size,
            input_shape=input_shape,
            output_shape=output_shape,
            description=f"Downloaded from HuggingFace: {repo_id}/{filename}",
            metadata_json=metadata,
        )
        db.add(record)
        db.commit()
        db.refresh(record)

        return {
            "id": record.id,
            "name": record.name,
            "framework": record.framework,
            "format": record.format,
            "file_size": record.file_size,
            "source": f"huggingface:{repo_id}/{filename}",
            "message": f"Successfully downloaded {filename} from {repo_id}",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"HuggingFace download failed: {str(e)}")
