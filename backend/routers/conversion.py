"""Conversion router — model format conversion and quantization endpoints."""

import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db, ModelRecord
from services.conversion_service import (
    convert_onnx_to_openvino,
    quantize_onnx_dynamic,
    quantize_onnx_static,
    compress_openvino_nncf,
    validate_onnx,
)

router = APIRouter(prefix="/api/convert", tags=["conversion"])

MODEL_STORE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "models")


class ConvertRequest(BaseModel):
    model_id: int = Field(..., description="Source model ID")
    target_format: str = Field(..., description="Target format: openvino")
    compress_fp16: bool = Field(True, description="Compress to FP16 (OpenVINO)")
    output_name: Optional[str] = Field(None, description="Custom output model name")


class QuantizeRequest(BaseModel):
    model_id: int = Field(..., description="Source model ID (must be ONNX)")
    method: str = Field("dynamic", description="Quantization method: dynamic, static, nncf_int8, nncf_int4")
    weight_type: str = Field("int8", description="Weight type for dynamic: int8, uint8")
    calibration_samples: int = Field(100, ge=10, le=1000, description="Calibration samples for static quantization")


@router.post("")
def convert_model(req: ConvertRequest, db: Session = Depends(get_db)):
    """Convert a model to a different format."""
    record = db.query(ModelRecord).filter(ModelRecord.id == req.model_id).first()
    if not record:
        raise HTTPException(404, "Model not found")

    if not os.path.exists(record.file_path):
        raise HTTPException(404, "Model file not found on disk")

    if req.target_format == "openvino":
        if record.format != "onnx":
            raise HTTPException(400, "OpenVINO conversion requires an ONNX model as source")

        result = convert_onnx_to_openvino(
            onnx_path=record.file_path,
            output_dir=MODEL_STORE,
            model_name=req.output_name,
            compress_to_fp16=req.compress_fp16,
        )

        # Register the converted model
        new_record = ModelRecord(
            name=f"{record.name} (OpenVINO IR)",
            framework="openvino",
            format="openvino_ir",
            file_path=result["xml_path"],
            file_size=result["xml_size"] + result["bin_size"],
            description=f"Converted from model {record.id} ({record.name})",
        )
        db.add(new_record)
        db.commit()
        db.refresh(new_record)

        return {
            "model_id": new_record.id,
            "name": new_record.name,
            "format": "openvino_ir",
            "xml_size": result["xml_size"],
            "bin_size": result["bin_size"],
            "total_size": result["xml_size"] + result["bin_size"],
            "message": "Model converted to OpenVINO IR format",
        }
    elif req.target_format == "tensorrt":
        if record.format != "onnx":
            raise HTTPException(400, "TensorRT conversion requires an ONNX model as source")
        try:
            import tensorrt as trt
        except ImportError:
            raise HTTPException(400, "TensorRT is not installed. Install with: pip install tensorrt")

        output_path = os.path.join(MODEL_STORE, f"{req.output_name or record.name}_trt.engine")
        try:
            logger = trt.Logger(trt.Logger.WARNING)
            builder = trt.Builder(logger)
            network = builder.create_network(1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH))
            parser = trt.OnnxParser(network, logger)
            with open(record.file_path, "rb") as f:
                if not parser.parse(f.read()):
                    errors = [parser.get_error(i).desc() for i in range(parser.num_errors)]
                    raise RuntimeError(f"ONNX parse errors: {errors}")
            config = builder.create_builder_config()
            config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, 1 << 30)
            if req.compress_fp16:
                config.set_flag(trt.BuilderFlag.FP16)
            engine = builder.build_serialized_network(network, config)
            with open(output_path, "wb") as f:
                f.write(engine)
        except Exception as e:
            raise HTTPException(500, f"TensorRT conversion failed: {e}")

        engine_size = os.path.getsize(output_path)
        new_record = ModelRecord(
            name=f"{record.name} (TensorRT)",
            framework="tensorrt",
            format="tensorrt",
            file_path=output_path,
            file_size=engine_size,
            description=f"Converted from model {record.id} ({record.name})",
        )
        db.add(new_record)
        db.commit()
        db.refresh(new_record)
        return {
            "model_id": new_record.id,
            "name": new_record.name,
            "format": "tensorrt",
            "engine_size": engine_size,
            "message": "Model converted to TensorRT engine",
        }

    elif req.target_format == "coreml":
        if record.format != "onnx":
            raise HTTPException(400, "CoreML conversion requires an ONNX model as source")
        try:
            import coremltools as ct
        except ImportError:
            raise HTTPException(400, "coremltools is not installed. Install with: pip install coremltools")

        output_path = os.path.join(MODEL_STORE, f"{req.output_name or record.name}.mlpackage")
        try:
            ml_model = ct.converters.onnx.convert(model=record.file_path)
            ml_model.save(output_path)
        except Exception as e:
            raise HTTPException(500, f"CoreML conversion failed: {e}")

        pkg_size = sum(
            os.path.getsize(os.path.join(dp, f))
            for dp, dn, fn in os.walk(output_path) for f in fn
        ) if os.path.isdir(output_path) else os.path.getsize(output_path)
        new_record = ModelRecord(
            name=f"{record.name} (CoreML)",
            framework="coreml",
            format="coreml",
            file_path=output_path,
            file_size=pkg_size,
            description=f"Converted from model {record.id} ({record.name})",
        )
        db.add(new_record)
        db.commit()
        db.refresh(new_record)
        return {
            "model_id": new_record.id,
            "name": new_record.name,
            "format": "coreml",
            "size": pkg_size,
            "message": "Model converted to CoreML format",
        }

    else:
        raise HTTPException(400, f"Unsupported target format: {req.target_format}. Supported: openvino, tensorrt, coreml")


@router.get("/available-formats")
def scan_available_formats():
    """Detect which conversion tools are installed on this system."""
    formats = []

    # OpenVINO
    try:
        import openvino  # noqa: F401
        formats.append({"id": "openvino", "name": "OpenVINO IR", "installed": True, "target": "Intel NPU/CPU/GPU", "source": ["onnx"]})
    except ImportError:
        formats.append({"id": "openvino", "name": "OpenVINO IR", "installed": False, "target": "Intel NPU/CPU/GPU", "source": ["onnx"], "install": "pip install openvino"})

    # TensorRT
    try:
        import tensorrt  # noqa: F401
        formats.append({"id": "tensorrt", "name": "TensorRT Engine", "installed": True, "target": "NVIDIA GPU", "source": ["onnx"]})
    except ImportError:
        formats.append({"id": "tensorrt", "name": "TensorRT Engine", "installed": False, "target": "NVIDIA GPU", "source": ["onnx"], "install": "pip install tensorrt"})

    # CoreML
    try:
        import coremltools  # noqa: F401
        formats.append({"id": "coreml", "name": "CoreML", "installed": True, "target": "Apple Silicon", "source": ["onnx"]})
    except ImportError:
        formats.append({"id": "coreml", "name": "CoreML", "installed": False, "target": "Apple Silicon", "source": ["onnx"], "install": "pip install coremltools"})

    # AMD Quark
    try:
        import quark  # noqa: F401
        formats.append({"id": "quark", "name": "AMD Quark", "installed": True, "target": "AMD NPU/FPGA", "source": ["onnx", "pytorch"]})
    except ImportError:
        formats.append({"id": "quark", "name": "AMD Quark", "installed": False, "target": "AMD NPU/FPGA", "source": ["onnx", "pytorch"], "install": "pip install quark"})

    # ONNX Runtime
    try:
        import onnxruntime  # noqa: F401
        formats.append({"id": "onnx", "name": "ONNX Runtime", "installed": True, "target": "Cross-platform", "source": ["pytorch", "safetensors"]})
    except ImportError:
        formats.append({"id": "onnx", "name": "ONNX Runtime", "installed": False, "target": "Cross-platform", "source": ["pytorch", "safetensors"], "install": "pip install onnxruntime"})

    # llama-cpp-python
    try:
        import llama_cpp  # noqa: F401
        formats.append({"id": "gguf", "name": "GGUF (llama.cpp)", "installed": True, "target": "CPU/GPU (LLM)", "source": ["gguf"]})
    except ImportError:
        formats.append({"id": "gguf", "name": "GGUF (llama.cpp)", "installed": False, "target": "CPU/GPU (LLM)", "source": ["gguf"], "install": "pip install llama-cpp-python"})

    return {"formats": formats, "total": len(formats), "installed": sum(1 for f in formats if f["installed"])}


@router.post("/quantize")
def quantize_model(req: QuantizeRequest, db: Session = Depends(get_db)):
    """Quantize a model for NPU deployment."""
    record = db.query(ModelRecord).filter(ModelRecord.id == req.model_id).first()
    if not record:
        raise HTTPException(404, "Model not found")

    if not os.path.exists(record.file_path):
        raise HTTPException(404, "Model file not found on disk")

    if req.method == "dynamic":
        if record.format != "onnx":
            raise HTTPException(400, "Dynamic quantization requires an ONNX model")

        result = quantize_onnx_dynamic(
            onnx_path=record.file_path,
            weight_type=req.weight_type,
        )

        new_record = ModelRecord(
            name=f"{record.name} (Quantized {req.weight_type.upper()})",
            framework="onnx",
            format="onnx",
            file_path=result["output_path"],
            file_size=result["quantized_size"],
            description=f"Dynamic quantized from model {record.id}. Compression ratio: {result['compression_ratio']}x",
        )
        db.add(new_record)
        db.commit()
        db.refresh(new_record)

        return {
            "model_id": new_record.id,
            "name": new_record.name,
            **result,
        }

    elif req.method == "static":
        if record.format != "onnx":
            raise HTTPException(400, "Static quantization requires an ONNX model")

        result = quantize_onnx_static(
            onnx_path=record.file_path,
            num_calibration_samples=req.calibration_samples,
        )

        new_record = ModelRecord(
            name=f"{record.name} (Static INT8)",
            framework="onnx",
            format="onnx",
            file_path=result["output_path"],
            file_size=result["quantized_size"],
            description=f"Static quantized from model {record.id}. Compression ratio: {result['compression_ratio']}x",
        )
        db.add(new_record)
        db.commit()
        db.refresh(new_record)

        return {
            "model_id": new_record.id,
            "name": new_record.name,
            **result,
        }

    elif req.method in ("nncf_int8", "nncf_int4"):
        mode = "int8" if req.method == "nncf_int8" else "int4"
        result = compress_openvino_nncf(
            model_path=record.file_path,
            output_dir=MODEL_STORE,
            mode=mode,
        )

        xml_size = os.path.getsize(result["xml_path"]) if os.path.exists(result["xml_path"]) else 0
        bin_size = os.path.getsize(result["bin_path"]) if os.path.exists(result["bin_path"]) else 0

        new_record = ModelRecord(
            name=f"{record.name} (NNCF {mode.upper()})",
            framework="openvino",
            format="openvino_ir",
            file_path=result["xml_path"],
            file_size=xml_size + bin_size,
            description=f"NNCF {mode.upper()} compressed from model {record.id}",
        )
        db.add(new_record)
        db.commit()
        db.refresh(new_record)

        return {
            "model_id": new_record.id,
            "name": new_record.name,
            **result,
            "total_size": xml_size + bin_size,
        }
    else:
        raise HTTPException(400, f"Unsupported quantization method: {req.method}")


@router.get("/validate/{model_id}")
def validate_model(model_id: int, db: Session = Depends(get_db)):
    """Validate an ONNX model and return graph information."""
    record = db.query(ModelRecord).filter(ModelRecord.id == model_id).first()
    if not record:
        raise HTTPException(404, "Model not found")

    if record.format != "onnx":
        raise HTTPException(400, "Validation is only supported for ONNX models")

    try:
        info = validate_onnx(record.file_path)
        return {"valid": True, **info}
    except Exception as e:
        return {"valid": False, "error": str(e)}
