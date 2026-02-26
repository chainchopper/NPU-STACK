"""GGUF Pipeline Router — Inspect, quantize, convert, and merge GGUF models.

Endpoints for the full GGUF model lifecycle:
  - Metadata inspection (architecture, quant type, vocab, etc.)
  - Quantization (21 types: Q2_K through Q8_0 + IQ with imatrix)
  - HuggingFace/SafeTensors → GGUF conversion
  - LoRA adapter merging
  - Model split/join for large models
  - Pipeline status and tool detection
"""

import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Form

router = APIRouter(prefix="/api/gguf", tags=["gguf-pipeline"])


# ── Pipeline Status ─────────────────────────────────────

@router.get("/pipeline/status")
def pipeline_status():
    """Get GGUF pipeline capabilities, tools, and supported quant types."""
    from services.gguf_pipeline import get_pipeline_status
    return get_pipeline_status()


@router.get("/pipeline/quant-types")
def list_quant_types():
    """List all available quantization types with descriptions."""
    from services.gguf_pipeline import QUANT_TYPES
    return {
        "quant_types": [
            {"id": k, **v} for k, v in QUANT_TYPES.items()
        ],
        "total": len(QUANT_TYPES),
        "recommended": ["Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0"],
    }


@router.get("/pipeline/architectures")
def list_architectures():
    """List supported LLM architectures for GGUF conversion."""
    from services.gguf_pipeline import SUPPORTED_ARCHITECTURES
    return {
        "architectures": SUPPORTED_ARCHITECTURES,
        "total": len(SUPPORTED_ARCHITECTURES),
    }


# ── Metadata Inspection ────────────────────────────────

@router.post("/inspect")
def inspect_gguf(model_path: str = Form(...)):
    """Read GGUF file metadata without loading the model.

    Returns architecture, tensor count, quantization info, vocab size,
    context length, and all metadata key-value pairs.
    """
    from services.gguf_pipeline import read_gguf_metadata
    result = read_gguf_metadata(model_path)
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "Failed to read GGUF"))
    return result


# ── Quantization ────────────────────────────────────────

@router.post("/quantize")
def quantize_model(
    input_path: str = Form(...),
    quant_type: str = Form("Q4_K_M"),
    output_name: Optional[str] = Form(None),
    n_threads: Optional[int] = Form(None),
    imatrix_path: Optional[str] = Form(None),
):
    """Quantize a GGUF model to a lower precision.

    Requires llama-quantize in PATH. For IQ types, provide an imatrix file.
    """
    from services.gguf_pipeline import quantize_gguf
    output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "models")
    result = quantize_gguf(input_path, output_dir, quant_type, output_name, n_threads, imatrix_path)
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "Quantization failed"))
    return result


@router.post("/imatrix")
def generate_importance_matrix(
    model_path: str = Form(...),
    calibration_file: Optional[str] = Form(None),
    n_chunks: int = Form(100),
):
    """Generate an importance matrix for high-quality IQ quantization.

    Requires llama-imatrix in PATH.
    """
    from services.gguf_pipeline import generate_imatrix
    output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "models")
    result = generate_imatrix(model_path, output_dir, calibration_file, n_chunks)
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "imatrix generation failed"))
    return result


# ── Conversion ──────────────────────────────────────────

@router.post("/convert/hf-to-gguf")
def convert_huggingface_to_gguf(
    model_dir: str = Form(...),
    output_type: str = Form("f16"),
    vocab_type: Optional[str] = Form(None),
):
    """Convert a HuggingFace model directory to GGUF format.

    Requires convert_hf_to_gguf.py from llama.cpp.
    """
    from services.gguf_pipeline import convert_hf_to_gguf
    output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "models")
    result = convert_hf_to_gguf(model_dir, output_dir, output_type, vocab_type)
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "Conversion failed"))
    return result


# ── LoRA Merge ──────────────────────────────────────────

@router.post("/merge/lora")
def merge_lora(
    base_model_path: str = Form(...),
    lora_path: str = Form(...),
    output_name: Optional[str] = Form(None),
    scale: float = Form(1.0),
    n_threads: Optional[int] = Form(None),
):
    """Merge a LoRA adapter into a base GGUF model.

    Requires llama-export-lora in PATH.
    """
    from services.gguf_pipeline import merge_lora_to_gguf
    output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "models")
    result = merge_lora_to_gguf(base_model_path, lora_path, output_dir, output_name, scale, n_threads)
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "LoRA merge failed"))
    return result


# ── Split/Join ──────────────────────────────────────────

@router.post("/split")
def split_model(
    input_path: str = Form(...),
    max_size_gb: float = Form(4.0),
):
    """Split a large GGUF model into smaller shards.

    Requires llama-gguf-split in PATH.
    """
    from services.gguf_pipeline import split_gguf
    output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "models", "split")
    result = split_gguf(input_path, output_dir, max_size_gb)
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "Split failed"))
    return result
