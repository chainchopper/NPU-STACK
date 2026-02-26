"""LiteRT Service — Google LiteRT (successor to TFLite) integration.

Supports:
  - LiteRT runtime for .tflite model inference
  - litert-torch: PyTorch → TFLite conversion
  - LiteRT-LM: On-device LLM inference (.litertlm format)
  - XNNPACK: CPU acceleration for ARM/x86/WebAssembly

Gracefully degrades when dependencies are not installed.
"""

import os
import subprocess
import platform
from typing import Optional


# ── Detection ───────────────────────────────────────────

def detect_litert() -> dict:
    """Detect LiteRT / TFLite / litert-torch ecosystem."""
    info = {
        "litert_available": False,
        "litert_version": None,
        "tflite_available": False,
        "tflite_version": None,
        "litert_torch_available": False,
        "litert_torch_version": None,
        "litert_lm_available": False,
        "litert_lm_version": None,
        "xnnpack_available": False,
        "delegates": [],
        "supported_formats": [],
    }

    # Check LiteRT (new package)
    try:
        import litert  # noqa: F401
        info["litert_available"] = True
        info["litert_version"] = getattr(litert, "__version__", "installed")
        info["supported_formats"].append("tflite")
    except ImportError:
        pass

    # Check TensorFlow Lite (original)
    try:
        import tflite_runtime.interpreter as tflite  # noqa: F401
        info["tflite_available"] = True
        info["tflite_version"] = "tflite_runtime"
        if not info["litert_available"]:
            info["supported_formats"].append("tflite")
    except ImportError:
        try:
            import tensorflow as tf
            if hasattr(tf, 'lite'):
                info["tflite_available"] = True
                info["tflite_version"] = f"tf {tf.__version__}"
                if not info["litert_available"]:
                    info["supported_formats"].append("tflite")
        except ImportError:
            pass

    # Check litert-torch (PyTorch → TFLite converter)
    try:
        import litert_torch  # noqa: F401
        info["litert_torch_available"] = True
        info["litert_torch_version"] = getattr(litert_torch, "__version__", "installed")
    except ImportError:
        pass

    # Check LiteRT-LM (on-device LLM)
    try:
        # LiteRT-LM may have CLI tool
        result = subprocess.run(
            ["lit", "--version"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            info["litert_lm_available"] = True
            info["litert_lm_version"] = result.stdout.strip()[:50]
            info["supported_formats"].append("litertlm")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Detect available delegates
    delegates = ["CPU"]
    if info["tflite_available"] or info["litert_available"]:
        # GPU delegate
        try:
            if platform.system() == "Android" or platform.system() == "Linux":
                delegates.append("GPU (OpenGL)")
            elif platform.system() == "Darwin":
                delegates.append("GPU (Metal)")
        except Exception:
            pass

        # XNNPACK (built into TFLite by default)
        info["xnnpack_available"] = True
        delegates.append("XNNPACK")

        # Edge TPU
        try:
            import tflite_runtime.interpreter as tflite
            tflite.load_delegate("libedgetpu.so.1", {})
            delegates.append("Edge TPU")
        except Exception:
            try:
                import tflite_runtime.interpreter as tflite
                tflite.load_delegate("edgetpu.dll", {})
                delegates.append("Edge TPU")
            except Exception:
                pass

        # NNAPI (Android)
        if platform.system() == "Linux":
            if os.path.exists("/dev/mali0") or os.path.exists("/sys/kernel/debug/rknpu"):
                delegates.append("NNAPI (NPU)")

    info["delegates"] = delegates
    return info


# ── Conversion ──────────────────────────────────────────

def convert_pytorch_to_tflite(
    model_path: str,
    output_dir: str,
    output_name: Optional[str] = None,
    sample_input_shape: list = None,
) -> dict:
    """Convert PyTorch model to TFLite using litert-torch.

    This uses the official Google LiteRT Torch Converter.
    """
    try:
        import litert_torch
    except ImportError:
        return {
            "success": False,
            "error": "litert-torch not installed. Install: pip install litert-torch",
            "install": "pip install ai-edge-litert-torch",
        }

    try:
        import torch
    except ImportError:
        return {"success": False, "error": "PyTorch not installed: pip install torch"}

    if not os.path.isfile(model_path):
        return {"success": False, "error": f"Model not found: {model_path}"}

    os.makedirs(output_dir, exist_ok=True)
    if not output_name:
        output_name = os.path.splitext(os.path.basename(model_path))[0]
    output_path = os.path.join(output_dir, f"{output_name}.tflite")

    try:
        # Load PyTorch model
        model = torch.load(model_path, map_location="cpu", weights_only=False)
        if isinstance(model, dict):
            return {"success": False, "error": "File contains state_dict only. Need full model for LiteRT conversion."}
        model.eval()

        # Create sample input
        if not sample_input_shape:
            sample_input_shape = [1, 3, 224, 224]
        sample_inputs = (torch.randn(*sample_input_shape),)

        # Convert using litert-torch
        edge_model = litert_torch.convert(model, sample_inputs)
        edge_model.export(output_path)

        return {
            "success": True,
            "output_path": output_path,
            "format": "tflite",
            "converter": "litert-torch",
            "file_size": os.path.getsize(output_path),
        }

    except Exception as e:
        return {"success": False, "error": f"LiteRT conversion failed: {str(e)}"}


def run_tflite_inference(
    model_path: str,
    input_data=None,
) -> dict:
    """Run inference on a TFLite model using LiteRT or tflite_runtime."""
    interpreter = None

    # Try LiteRT first, then tflite_runtime, then full tensorflow
    try:
        import litert
        interpreter = litert.Interpreter(model_path=model_path)
    except (ImportError, Exception):
        try:
            import tflite_runtime.interpreter as tflite
            interpreter = tflite.Interpreter(model_path=model_path)
        except ImportError:
            try:
                import tensorflow as tf
                interpreter = tf.lite.Interpreter(model_path=model_path)
            except ImportError:
                return {"success": False, "error": "No TFLite runtime found. Install: pip install ai-edge-litert"}

    if interpreter is None:
        return {"success": False, "error": "Failed to create interpreter"}

    try:
        interpreter.allocate_tensors()

        input_details = interpreter.get_input_details()
        output_details = interpreter.get_output_details()

        # Model info
        info = {
            "success": True,
            "model_path": model_path,
            "inputs": [
                {
                    "name": d["name"],
                    "shape": d["shape"].tolist(),
                    "dtype": str(d["dtype"]),
                    "index": d["index"],
                }
                for d in input_details
            ],
            "outputs": [
                {
                    "name": d["name"],
                    "shape": d["shape"].tolist(),
                    "dtype": str(d["dtype"]),
                    "index": d["index"],
                }
                for d in output_details
            ],
        }

        # Run inference if input provided
        if input_data is not None:
            import numpy as np
            if not isinstance(input_data, np.ndarray):
                input_data = np.array(input_data, dtype=input_details[0]["dtype"])
            interpreter.set_tensor(input_details[0]["index"], input_data)
            interpreter.invoke()
            output = interpreter.get_tensor(output_details[0]["index"])
            info["output_shape"] = output.shape
            info["output_preview"] = output.flatten()[:10].tolist()

        return info

    except Exception as e:
        return {"success": False, "error": str(e)}


def get_tflite_model_info(model_path: str) -> dict:
    """Get metadata from a TFLite model without running inference."""
    return run_tflite_inference(model_path, input_data=None)
