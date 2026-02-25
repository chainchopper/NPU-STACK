"""Cross-Format Model Converter — Convert between any two model formats.

Supports: PyTorch ↔ ONNX ↔ SafeTensors ↔ GGUF ↔ TFLite ↔ OpenVINO ↔ TensorRT ↔ Keras
All conversions degrade gracefully when libraries are missing.
"""

import os
import shutil
from typing import Optional


# ── Conversion Registry ─────────────────────────────────
CONVERSION_PATHS = {
    "pytorch_to_onnx": {"from": "PyTorch", "to": "ONNX", "extensions": [".pt", ".pth", ".bin"]},
    "onnx_to_pytorch": {"from": "ONNX", "to": "PyTorch", "extensions": [".onnx"]},
    "safetensors_to_pytorch": {"from": "SafeTensors", "to": "PyTorch", "extensions": [".safetensors"]},
    "pytorch_to_safetensors": {"from": "PyTorch", "to": "SafeTensors", "extensions": [".pt", ".pth", ".bin"]},
    "onnx_to_tflite": {"from": "ONNX", "to": "TFLite", "extensions": [".onnx"]},
    "onnx_to_tensorrt": {"from": "ONNX", "to": "TensorRT", "extensions": [".onnx"]},
    "keras_to_onnx": {"from": "Keras", "to": "ONNX", "extensions": [".h5", ".keras"]},
    "onnx_to_keras": {"from": "ONNX", "to": "Keras", "extensions": [".onnx"]},
    "pytorch_to_gguf": {"from": "PyTorch", "to": "GGUF", "extensions": [".pt", ".pth", ".bin"]},
    "gguf_to_onnx": {"from": "GGUF", "to": "ONNX", "extensions": [".gguf"]},
    "onnx_to_openvino": {"from": "ONNX", "to": "OpenVINO", "extensions": [".onnx"]},
    "onnx_to_vitis": {"from": "ONNX", "to": "Vitis AI", "extensions": [".onnx"]},
}


def get_conversion_paths() -> list:
    """Return all available conversion paths with availability status."""
    paths = []
    for key, info in CONVERSION_PATHS.items():
        available, note = _check_availability(key)
        paths.append({
            "id": key,
            "from_format": info["from"],
            "to_format": info["to"],
            "source_extensions": info["extensions"],
            "available": available,
            "note": note,
        })
    return paths


def convert_model(
    model_path: str,
    target_format: str,
    output_dir: str = None,
    output_name: str = None,
    **kwargs,
) -> dict:
    """Convert a model from one format to another.

    Args:
        model_path: Path to source model file.
        target_format: Target format key (e.g., "onnx", "safetensors", "gguf", "tflite").
        output_dir: Output directory (defaults to same dir as source).
        output_name: Output filename (without extension).
        **kwargs: Format-specific options (opset_version, quantize, etc.)

    Returns:
        dict with success, output_path, format info.
    """
    if not os.path.exists(model_path):
        return {"success": False, "error": f"Source file not found: {model_path}"}

    src_ext = os.path.splitext(model_path)[1].lower()
    if not output_dir:
        output_dir = os.path.dirname(model_path)
    if not output_name:
        output_name = os.path.splitext(os.path.basename(model_path))[0]

    os.makedirs(output_dir, exist_ok=True)
    target = target_format.lower()

    try:
        if target == "onnx":
            if src_ext in (".pt", ".pth", ".bin"):
                return _pytorch_to_onnx(model_path, output_dir, output_name, **kwargs)
            elif src_ext in (".h5", ".keras"):
                return _keras_to_onnx(model_path, output_dir, output_name, **kwargs)
            else:
                return {"success": False, "error": f"Cannot convert {src_ext} to ONNX"}

        elif target == "pytorch":
            if src_ext == ".onnx":
                return _onnx_to_pytorch(model_path, output_dir, output_name, **kwargs)
            elif src_ext == ".safetensors":
                return _safetensors_to_pytorch(model_path, output_dir, output_name, **kwargs)
            else:
                return {"success": False, "error": f"Cannot convert {src_ext} to PyTorch"}

        elif target == "safetensors":
            if src_ext in (".pt", ".pth", ".bin"):
                return _pytorch_to_safetensors(model_path, output_dir, output_name, **kwargs)
            else:
                return {"success": False, "error": f"Cannot convert {src_ext} to SafeTensors"}

        elif target == "tflite":
            if src_ext == ".onnx":
                return _onnx_to_tflite(model_path, output_dir, output_name, **kwargs)
            else:
                return {"success": False, "error": f"Cannot convert {src_ext} to TFLite. Convert to ONNX first."}

        elif target == "tensorrt":
            if src_ext == ".onnx":
                return _onnx_to_tensorrt(model_path, output_dir, output_name, **kwargs)
            else:
                return {"success": False, "error": f"Cannot convert {src_ext} to TensorRT. Convert to ONNX first."}

        elif target == "keras":
            if src_ext == ".onnx":
                return _onnx_to_keras(model_path, output_dir, output_name, **kwargs)
            else:
                return {"success": False, "error": f"Cannot convert {src_ext} to Keras"}

        elif target == "gguf":
            return _to_gguf(model_path, output_dir, output_name, **kwargs)

        elif target == "openvino":
            if src_ext == ".onnx":
                return _onnx_to_openvino(model_path, output_dir, output_name, **kwargs)
            else:
                return {"success": False, "error": f"Cannot convert {src_ext} to OpenVINO. Convert to ONNX first."}

        elif target == "vitis":
            if src_ext == ".onnx":
                return _onnx_to_vitis(model_path, output_dir, output_name, **kwargs)
            else:
                return {"success": False, "error": f"Cannot convert {src_ext} to Vitis AI. Convert to ONNX first."}

        else:
            return {"success": False, "error": f"Unknown target format: {target_format}"}

    except Exception as e:
        return {"success": False, "error": str(e)}


def batch_convert(model_paths: list, target_format: str, output_dir: str, **kwargs) -> dict:
    """Convert multiple models to the same target format."""
    results = []
    for path in model_paths:
        result = convert_model(path, target_format, output_dir, **kwargs)
        result["source"] = path
        results.append(result)

    return {
        "results": results,
        "total": len(results),
        "success_count": sum(1 for r in results if r.get("success")),
        "error_count": sum(1 for r in results if not r.get("success")),
    }


# ── Converters ──────────────────────────────────────────

def _pytorch_to_onnx(model_path, output_dir, output_name, **kwargs):
    try:
        import torch
    except ImportError:
        return {"success": False, "error": "Install PyTorch: pip install torch"}

    opset = kwargs.get("opset_version", 17)
    output_path = os.path.join(output_dir, f"{output_name}.onnx")

    # Try loading as full model first
    try:
        model = torch.load(model_path, map_location="cpu", weights_only=False)
        if isinstance(model, dict):
            return {"success": False, "error": "File contains state_dict only. Need full model or model class to export to ONNX."}
        model.eval()
    except Exception as e:
        return {"success": False, "error": f"Cannot load PyTorch model: {e}. Provide a full model (not just state_dict)."}

    # Infer input shape
    input_shape = kwargs.get("input_shape", [1, 3, 224, 224])
    dummy_input = torch.randn(*input_shape)

    try:
        torch.onnx.export(
            model,
            dummy_input,
            output_path,
            opset_version=opset,
            input_names=["input"],
            output_names=["output"],
            dynamic_axes={"input": {0: "batch_size"}, "output": {0: "batch_size"}},
        )
    except Exception as e:
        return {"success": False, "error": f"ONNX export failed: {e}"}

    return {
        "success": True,
        "output_path": output_path,
        "format": "onnx",
        "opset_version": opset,
        "file_size": os.path.getsize(output_path),
    }


def _onnx_to_pytorch(model_path, output_dir, output_name, **kwargs):
    try:
        import onnx
        from onnx2torch import convert as onnx_to_torch
    except ImportError:
        return {"success": False, "error": "Install onnx2torch: pip install onnx2torch"}

    import torch

    onnx_model = onnx.load(model_path)
    pytorch_model = onnx_to_torch(onnx_model)
    output_path = os.path.join(output_dir, f"{output_name}.pt")
    torch.save(pytorch_model, output_path)

    return {
        "success": True,
        "output_path": output_path,
        "format": "pytorch",
        "file_size": os.path.getsize(output_path),
    }


def _pytorch_to_safetensors(model_path, output_dir, output_name, **kwargs):
    try:
        import torch
        from safetensors.torch import save_file
    except ImportError:
        return {"success": False, "error": "Install safetensors: pip install safetensors"}

    output_path = os.path.join(output_dir, f"{output_name}.safetensors")

    checkpoint = torch.load(model_path, map_location="cpu", weights_only=True)
    if isinstance(checkpoint, dict) and "state_dict" in checkpoint:
        state_dict = checkpoint["state_dict"]
    elif isinstance(checkpoint, dict) and "model" in checkpoint:
        state_dict = checkpoint["model"]
    elif isinstance(checkpoint, dict):
        state_dict = checkpoint
    else:
        # Full model — extract state_dict
        state_dict = checkpoint.state_dict() if hasattr(checkpoint, "state_dict") else {}

    if not state_dict:
        return {"success": False, "error": "Could not extract state_dict from model file"}

    save_file(state_dict, output_path)

    return {
        "success": True,
        "output_path": output_path,
        "format": "safetensors",
        "param_count": len(state_dict),
        "file_size": os.path.getsize(output_path),
    }


def _safetensors_to_pytorch(model_path, output_dir, output_name, **kwargs):
    try:
        import torch
        from safetensors.torch import load_file
    except ImportError:
        return {"success": False, "error": "Install safetensors: pip install safetensors"}

    state_dict = load_file(model_path)
    output_path = os.path.join(output_dir, f"{output_name}.pt")
    torch.save(state_dict, output_path)

    return {
        "success": True,
        "output_path": output_path,
        "format": "pytorch",
        "param_count": len(state_dict),
        "file_size": os.path.getsize(output_path),
    }


def _onnx_to_tflite(model_path, output_dir, output_name, **kwargs):
    try:
        import onnx
        from onnx_tf.backend import prepare
        import tensorflow as tf
    except ImportError:
        return {"success": False, "error": "Install onnx-tf and tensorflow: pip install onnx-tf tensorflow"}

    # ONNX → TF SavedModel → TFLite
    onnx_model = onnx.load(model_path)
    tf_rep = prepare(onnx_model)
    saved_model_dir = os.path.join(output_dir, f"{output_name}_saved_model")
    tf_rep.export_graph(saved_model_dir)

    # SavedModel → TFLite
    converter = tf.lite.TFLiteConverter.from_saved_model(saved_model_dir)
    if kwargs.get("quantize"):
        converter.optimizations = [tf.lite.Optimize.DEFAULT]
    tflite_model = converter.convert()

    output_path = os.path.join(output_dir, f"{output_name}.tflite")
    with open(output_path, "wb") as f:
        f.write(tflite_model)

    # Cleanup saved model
    shutil.rmtree(saved_model_dir, ignore_errors=True)

    return {
        "success": True,
        "output_path": output_path,
        "format": "tflite",
        "quantized": bool(kwargs.get("quantize")),
        "file_size": os.path.getsize(output_path),
    }


def _onnx_to_tensorrt(model_path, output_dir, output_name, **kwargs):
    try:
        import tensorrt as trt
    except ImportError:
        # Try trtexec CLI as fallback
        import subprocess
        output_path = os.path.join(output_dir, f"{output_name}.engine")
        try:
            cmd = ["trtexec", f"--onnx={model_path}", f"--saveEngine={output_path}"]
            if kwargs.get("fp16"):
                cmd.append("--fp16")
            if kwargs.get("int8"):
                cmd.append("--int8")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if result.returncode != 0:
                return {"success": False, "error": f"trtexec failed: {result.stderr[:500]}"}
            return {
                "success": True,
                "output_path": output_path,
                "format": "tensorrt",
                "file_size": os.path.getsize(output_path),
            }
        except FileNotFoundError:
            return {"success": False, "error": "Install TensorRT: pip install tensorrt (or ensure trtexec is in PATH)"}

    # TRT Python API
    logger = trt.Logger(trt.Logger.WARNING)
    builder = trt.Builder(logger)
    network = builder.create_network(1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH))
    parser = trt.OnnxParser(network, logger)

    with open(model_path, "rb") as f:
        if not parser.parse(f.read()):
            errors = [parser.get_error(i).desc() for i in range(parser.num_errors)]
            return {"success": False, "error": f"ONNX parse errors: {errors[:3]}"}

    config = builder.create_builder_config()
    config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, 1 << 30)
    if kwargs.get("fp16"):
        config.set_flag(trt.BuilderFlag.FP16)

    engine = builder.build_serialized_network(network, config)
    output_path = os.path.join(output_dir, f"{output_name}.engine")
    with open(output_path, "wb") as f:
        f.write(engine)

    return {
        "success": True,
        "output_path": output_path,
        "format": "tensorrt",
        "file_size": os.path.getsize(output_path),
    }


def _keras_to_onnx(model_path, output_dir, output_name, **kwargs):
    try:
        import tensorflow as tf
        import tf2onnx
    except ImportError:
        return {"success": False, "error": "Install tf2onnx: pip install tf2onnx tensorflow"}

    model = tf.keras.models.load_model(model_path)
    opset = kwargs.get("opset_version", 17)
    output_path = os.path.join(output_dir, f"{output_name}.onnx")

    spec = [tf.TensorSpec(shape=inp.shape, dtype=inp.dtype, name=inp.name) for inp in model.inputs]
    onnx_model, _ = tf2onnx.convert.from_keras(model, input_signature=spec, opset=opset)

    import onnx
    onnx.save(onnx_model, output_path)

    return {
        "success": True,
        "output_path": output_path,
        "format": "onnx",
        "opset_version": opset,
        "file_size": os.path.getsize(output_path),
    }


def _onnx_to_keras(model_path, output_dir, output_name, **kwargs):
    try:
        import onnx
        from onnx_tf.backend import prepare
    except ImportError:
        return {"success": False, "error": "Install onnx-tf: pip install onnx-tf tensorflow"}

    onnx_model = onnx.load(model_path)
    tf_rep = prepare(onnx_model)
    output_path = os.path.join(output_dir, f"{output_name}_keras")
    tf_rep.export_graph(output_path)

    return {
        "success": True,
        "output_path": output_path,
        "format": "keras_savedmodel",
        "note": "Exported as TensorFlow SavedModel (Keras-compatible)",
    }


def _to_gguf(model_path, output_dir, output_name, **kwargs):
    """Convert to GGUF using llama.cpp convert script."""
    import subprocess

    quantization = kwargs.get("quantization", "Q4_K_M")
    output_path = os.path.join(output_dir, f"{output_name}-{quantization}.gguf")

    # Check if llama.cpp convert tools are available
    convert_script = None
    for candidate in ["llama-quantize", "quantize"]:
        try:
            result = subprocess.run([candidate, "--help"], capture_output=True, text=True, timeout=5)
            convert_script = candidate
            break
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

    if not convert_script:
        return {
            "success": False,
            "error": "llama.cpp quantize tool not found in PATH. Install llama.cpp: https://github.com/ggerganov/llama.cpp",
        }

    # If source is already GGUF, re-quantize
    src_ext = os.path.splitext(model_path)[1].lower()
    if src_ext == ".gguf":
        cmd = [convert_script, model_path, output_path, quantization]
    else:
        return {
            "success": False,
            "error": f"Direct {src_ext}→GGUF conversion requires the model in HuggingFace format. Use llama.cpp's convert_hf_to_gguf.py script.",
            "suggestion": "Convert to HuggingFace format first, then use llama.cpp convert_hf_to_gguf.py → quantize",
        }

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            return {"success": False, "error": f"Quantize failed: {result.stderr[:500]}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

    return {
        "success": True,
        "output_path": output_path,
        "format": "gguf",
        "quantization": quantization,
        "file_size": os.path.getsize(output_path),
    }


def _onnx_to_openvino(model_path, output_dir, output_name, **kwargs):
    """Use existing conversion_service for OpenVINO."""
    try:
        from services.conversion_service import convert_onnx_to_openvino
        result = convert_onnx_to_openvino(model_path, output_dir, compress=kwargs.get("compress", "none"))
        return {
            "success": True,
            "output_path": result.get("xml_path", ""),
            "format": "openvino",
            "compression": result.get("compression"),
        }
    except ImportError:
        return {"success": False, "error": "OpenVINO not installed: pip install openvino-dev"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _onnx_to_vitis(model_path, output_dir, output_name, **kwargs):
    """Use existing conversion_service for Vitis AI."""
    try:
        from services.conversion_service import quantize_vitis
        result = quantize_vitis(model_path, output_dir)
        return {
            "success": True,
            "output_path": result.get("output_path", ""),
            "format": "vitis_ai",
        }
    except ImportError:
        return {"success": False, "error": "Vitis AI tools not installed"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Availability Checker ────────────────────────────────

def _check_availability(conversion_key: str) -> tuple:
    """Check if required libraries for a conversion are installed."""
    checks = {
        "pytorch_to_onnx": ("torch", "PyTorch"),
        "onnx_to_pytorch": ("onnx2torch", "onnx2torch"),
        "safetensors_to_pytorch": ("safetensors", "safetensors"),
        "pytorch_to_safetensors": ("safetensors", "safetensors"),
        "onnx_to_tflite": ("tensorflow", "tensorflow + onnx-tf"),
        "onnx_to_tensorrt": ("tensorrt", "tensorrt"),
        "keras_to_onnx": ("tf2onnx", "tf2onnx"),
        "onnx_to_keras": ("onnx_tf", "onnx-tf"),
        "pytorch_to_gguf": (None, "llama.cpp CLI"),
        "gguf_to_onnx": (None, "llama.cpp CLI"),
        "onnx_to_openvino": ("openvino", "openvino-dev"),
        "onnx_to_vitis": (None, "Vitis AI tools"),
    }

    entry = checks.get(conversion_key)
    if not entry:
        return False, "Unknown conversion"

    module, pkg_name = entry
    if module is None:
        return True, f"Requires {pkg_name} in PATH"

    try:
        __import__(module)
        return True, "Available"
    except ImportError:
        return False, f"pip install {pkg_name}"
