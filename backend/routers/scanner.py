"""Scanner router — discover and import local model files from configured directories."""

import os
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db, ModelRecord

router = APIRouter(prefix="/api/scan", tags=["scanner"])

MODEL_STORE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "models")

# Supported model file extensions and their metadata
FORMAT_MAP = {
    ".gguf": {"framework": "llama.cpp", "format": "gguf", "category": "LLM"},
    ".safetensors": {"framework": "pytorch", "format": "safetensors", "category": "Diffusion/LLM"},
    ".ckpt": {"framework": "pytorch", "format": "checkpoint", "category": "Diffusion"},
    ".onnx": {"framework": "onnx", "format": "onnx", "category": "Universal"},
    ".bin": {"framework": "pytorch", "format": "pytorch_bin", "category": "Transformers"},
    ".pt": {"framework": "pytorch", "format": "pytorch", "category": "PyTorch"},
    ".pth": {"framework": "pytorch", "format": "pytorch", "category": "PyTorch"},
    ".tflite": {"framework": "tflite", "format": "tflite", "category": "Edge/Mobile"},
    ".xml": {"framework": "openvino", "format": "openvino_ir", "category": "Intel NPU"},
    ".engine": {"framework": "tensorrt", "format": "tensorrt", "category": "NVIDIA GPU"},
    ".mlmodel": {"framework": "coreml", "format": "coreml", "category": "Apple"},
    ".mlpackage": {"framework": "coreml", "format": "coreml", "category": "Apple"},
}

# Well-known directories to check
DEFAULT_SCAN_HINTS = [
    # ComfyUI
    "C:/ComfyUI/models",
    "D:/ComfyUI/models",
    "C:/Users/{user}/ComfyUI/models",
    # Automatic1111
    "C:/stable-diffusion-webui/models",
    # LM Studio
    "C:/Users/{user}/.cache/lm-studio/models",
    # Ollama
    "C:/Users/{user}/.ollama/models",
    # HuggingFace cache
    "C:/Users/{user}/.cache/huggingface/hub",
]


def _format_size(size_bytes: int) -> str:
    """Format bytes to human-readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


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


def scan_directory(directory: str, recursive: bool = True) -> List[dict]:
    """Scan a directory for model files.
    
    Returns list of dicts with file info.
    """
    if not os.path.isdir(directory):
        return []
    
    results = []
    
    if recursive:
        for root, dirs, files in os.walk(directory):
            # Skip hidden dirs and __pycache__
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in FORMAT_MAP:
                    full_path = os.path.join(root, f)
                    try:
                        size = os.path.getsize(full_path)
                    except OSError:
                        size = 0
                    
                    info = {
                        "filename": f,
                        "path": full_path,
                        "extension": ext,
                        "size_bytes": size,
                        "size_human": _format_size(size),
                        "quantization": _detect_quant(f),
                        **FORMAT_MAP[ext],
                    }
                    results.append(info)
    else:
        for f in os.listdir(directory):
            full_path = os.path.join(directory, f)
            if not os.path.isfile(full_path):
                continue
            ext = os.path.splitext(f)[1].lower()
            if ext in FORMAT_MAP:
                try:
                    size = os.path.getsize(full_path)
                except OSError:
                    size = 0
                info = {
                    "filename": f,
                    "path": full_path,
                    "extension": ext,
                    "size_bytes": size,
                    "size_human": _format_size(size),
                    "quantization": _detect_quant(f),
                    **FORMAT_MAP[ext],
                }
                results.append(info)
    
    return results


# ─── API Endpoints ────────────────────────────────────────────────────────────


@router.get("")
def scan_models(
    directory: str = Query(..., description="Directory path to scan for model files"),
    recursive: bool = Query(True, description="Scan subdirectories recursively"),
):
    """Scan a directory for model files."""
    if not os.path.isdir(directory):
        raise HTTPException(404, f"Directory not found: {directory}")
    
    results = scan_directory(directory, recursive=recursive)
    
    # Group by format
    by_format = {}
    for r in results:
        fmt = r["format"]
        by_format.setdefault(fmt, []).append(r)
    
    return {
        "directory": directory,
        "total_files": len(results),
        "by_format": {k: len(v) for k, v in by_format.items()},
        "models": results,
    }


@router.get("/hints")
def get_scan_hints():
    """Get suggested directories to scan based on common model locations."""
    import getpass
    username = getpass.getuser()
    
    hints = []
    for hint in DEFAULT_SCAN_HINTS:
        path = hint.replace("{user}", username)
        exists = os.path.isdir(path)
        hints.append({
            "path": path,
            "exists": exists,
            "source": _identify_source(path),
        })
    
    # Also include the NPU-STACK model store
    hints.insert(0, {
        "path": MODEL_STORE,
        "exists": os.path.isdir(MODEL_STORE),
        "source": "NPU-STACK",
    })
    
    return {"hints": hints}


def _identify_source(path: str) -> str:
    """Identify which application a model directory belongs to."""
    p = path.lower()
    if "comfyui" in p:
        return "ComfyUI"
    elif "stable-diffusion" in p or "a1111" in p:
        return "Automatic1111"
    elif "lm-studio" in p:
        return "LM Studio"
    elif "ollama" in p:
        return "Ollama"
    elif "huggingface" in p:
        return "HuggingFace Cache"
    return "Unknown"


class ImportRequest(BaseModel):
    file_path: str = Field(..., description="Full path to the model file to import")
    name: Optional[str] = Field(None, description="Custom name for the model (auto-generated if omitted)")
    copy_file: bool = Field(False, description="If true, copy file to NPU-STACK model store. If false, reference in-place.")


@router.post("/import")
def import_model(req: ImportRequest, db: Session = Depends(get_db)):
    """Import a discovered model file into the NPU-STACK registry."""
    if not os.path.exists(req.file_path):
        raise HTTPException(404, f"File not found: {req.file_path}")
    
    ext = os.path.splitext(req.file_path)[1].lower()
    if ext not in FORMAT_MAP:
        raise HTTPException(400, f"Unsupported format: {ext}")
    
    fmt_info = FORMAT_MAP[ext]
    filename = os.path.basename(req.file_path)
    model_name = req.name or os.path.splitext(filename)[0]
    
    # Check if already imported
    existing = db.query(ModelRecord).filter(ModelRecord.file_path == req.file_path).first()
    if existing:
        return {
            "status": "already_exists",
            "model_id": existing.id,
            "name": existing.name,
            "message": "This model is already in the registry",
        }
    
    # Optionally copy to model store
    target_path = req.file_path
    if req.copy_file:
        os.makedirs(MODEL_STORE, exist_ok=True)
        target_path = os.path.join(MODEL_STORE, filename)
        if not os.path.exists(target_path):
            import shutil
            shutil.copy2(req.file_path, target_path)
    
    file_size = os.path.getsize(target_path)
    quant = _detect_quant(filename)
    
    record = ModelRecord(
        name=model_name,
        framework=fmt_info["framework"],
        format=fmt_info["format"],
        file_path=target_path,
        file_size=file_size,
        description=f"Imported from {req.file_path}. "
                    f"Format: {fmt_info['format']}. "
                    f"Category: {fmt_info['category']}."
                    + (f" Quantization: {quant}." if quant else ""),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    
    return {
        "status": "imported",
        "model_id": record.id,
        "name": record.name,
        "format": record.format,
        "framework": record.framework,
        "size_human": _format_size(file_size),
        "quantization": quant,
        "copied": req.copy_file,
    }


@router.get("/formats")
def list_supported_formats():
    """List all supported model file formats."""
    formats = []
    for ext, info in FORMAT_MAP.items():
        formats.append({
            "extension": ext,
            **info,
        })
    return {"formats": formats}
