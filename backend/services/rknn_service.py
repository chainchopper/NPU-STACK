"""Rockchip RKNN Service — Convert ONNX models to RKNN format for Rockchip NPUs.

Supports:
  - RK3588 / RK3588S (6 TOPS NPU)
  - RK3576 (6 TOPS NPU)
  - RV1103 / RV1106 (0.5 TOPS RKNPU 4.0)
  - RK3566 / RK3568 (1 TOPS NPU)

Conversion pipeline: ONNX → RKNN (int4 / int8 / int16 / fp16 quantization)
Uses rknn_toolkit2 (PC-side) or rknn_toolkit_lite2 (on-device).
Gracefully degrades if RKNN tools are not installed.
"""

import os
import sys
import json
import subprocess
import platform
from typing import Optional


# ── Detection ───────────────────────────────────────────

def detect_rknn_environment() -> dict:
    """Detect RKNN SDK, NPU driver, and hardware info."""
    env = {
        "rknn_toolkit2_available": False,
        "rknn_toolkit2_version": None,
        "rknn_lite2_available": False,
        "rknn_lite2_version": None,
        "npu_driver_version": None,
        "soc_detected": None,
        "npu_cores": None,
        "supported_platforms": [
            "RK3588", "RK3588S", "RK3576",
            "RK3566", "RK3568",
            "RV1103", "RV1106", "RV1109", "RV1126",
        ],
    }

    # Check rknn_toolkit2 (PC-side conversion)
    try:
        from rknn.api import RKNN  # noqa: F401
        env["rknn_toolkit2_available"] = True
        try:
            import rknn
            env["rknn_toolkit2_version"] = getattr(rknn, "__version__", "unknown")
        except Exception:
            env["rknn_toolkit2_version"] = "installed"
    except ImportError:
        pass

    # Check rknn_toolkit_lite2 (on-device inference)
    try:
        from rknnlite.api import RKNNLite  # noqa: F401
        env["rknn_lite2_available"] = True
        try:
            import rknnlite
            env["rknn_lite2_version"] = getattr(rknnlite, "__version__", "unknown")
        except Exception:
            env["rknn_lite2_version"] = "installed"
    except ImportError:
        pass

    # Try detecting NPU driver on Linux (Rockchip boards)
    if platform.system() == "Linux":
        try:
            result = subprocess.run(
                ["dmesg"], capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.split("\n"):
                if "rknpu" in line.lower():
                    if "driver version" in line.lower():
                        # Extract driver version like "RKNPU driver version: 0.9.8"
                        parts = line.split("version")
                        if len(parts) > 1:
                            env["npu_driver_version"] = parts[-1].strip().rstrip(".")
                    break
        except Exception:
            pass

        # Try to detect SoC
        try:
            with open("/proc/device-tree/compatible", "r") as f:
                compat = f.read()
                for soc in ["rk3588", "rk3576", "rk3566", "rk3568", "rv1103", "rv1106"]:
                    if soc in compat.lower():
                        env["soc_detected"] = soc.upper()
                        break
        except Exception:
            pass

        # NPU usage on RK3588
        try:
            rknpu_load = "/sys/kernel/debug/rknpu/load"
            if os.path.exists(rknpu_load):
                with open(rknpu_load, "r") as f:
                    env["npu_load"] = f.read().strip()
        except Exception:
            pass

    return env


def get_npu_usage() -> dict:
    """Get real-time NPU utilization (RK3588 only, requires root or sysfs access)."""
    usage = {"available": False, "cores": []}

    try:
        # RK3588 has 3 NPU cores
        load_path = "/sys/kernel/debug/rknpu/load"
        if os.path.exists(load_path):
            with open(load_path, "r") as f:
                content = f.read().strip()
            usage["available"] = True
            usage["raw"] = content
            # Parse "NPU load: Core0: 45%, Core1: 30%, Core2: 10%"
            for part in content.split(","):
                part = part.strip()
                if "Core" in part and "%" in part:
                    try:
                        pct = int(part.split("%")[0].split(":")[-1].strip())
                        usage["cores"].append(pct)
                    except ValueError:
                        pass
            if usage["cores"]:
                usage["average_load"] = sum(usage["cores"]) / len(usage["cores"])
    except Exception:
        pass

    return usage


# ── Conversion ──────────────────────────────────────────

RKNN_QUANTIZATION_TYPES = ["int4", "int8", "int16", "fp16", "dynamic_fixed_point"]

RKNN_TARGET_PLATFORMS = {
    "rk3588": {"npu_cores": 3, "tops": 6.0, "name": "RK3588"},
    "rk3576": {"npu_cores": 2, "tops": 6.0, "name": "RK3576"},
    "rk3566": {"npu_cores": 1, "tops": 1.0, "name": "RK3566"},
    "rk3568": {"npu_cores": 1, "tops": 1.0, "name": "RK3568"},
    "rv1103": {"npu_cores": 1, "tops": 0.5, "name": "RV1103"},
    "rv1106": {"npu_cores": 1, "tops": 0.5, "name": "RV1106"},
}


def convert_onnx_to_rknn(
    onnx_path: str,
    output_dir: str,
    output_name: Optional[str] = None,
    target_platform: str = "rk3588",
    quantization: str = "int8",
    dataset_path: Optional[str] = None,
    mean_values: Optional[list] = None,
    std_values: Optional[list] = None,
    input_size: Optional[list] = None,
) -> dict:
    """Convert ONNX model to RKNN format for Rockchip NPUs.

    Args:
        onnx_path: Path to input ONNX model.
        output_dir: Output directory for .rknn file.
        output_name: Output filename (without extension).
        target_platform: Target SoC (rk3588, rk3566, rv1106, etc.)
        quantization: Quantization type (int4, int8, int16, fp16).
        dataset_path: Path to calibration dataset (text file with image paths).
        mean_values: Input mean normalization values.
        std_values: Input std normalization values.
        input_size: Model input dimensions [batch, channels, height, width].

    Returns:
        dict with success, output_path, and conversion details.
    """
    if not os.path.isfile(onnx_path):
        return {"success": False, "error": f"ONNX file not found: {onnx_path}"}

    try:
        from rknn.api import RKNN
    except ImportError:
        return {
            "success": False,
            "error": "rknn_toolkit2 is not installed. Install with: pip install rknn_toolkit2",
            "install_guide": "https://github.com/airockchip/rknn-toolkit2",
        }

    if quantization not in RKNN_QUANTIZATION_TYPES:
        return {"success": False, "error": f"Unsupported quantization: {quantization}. Use: {RKNN_QUANTIZATION_TYPES}"}

    if target_platform.lower() not in RKNN_TARGET_PLATFORMS:
        return {"success": False, "error": f"Unsupported platform: {target_platform}. Use: {list(RKNN_TARGET_PLATFORMS.keys())}"}

    os.makedirs(output_dir, exist_ok=True)

    if not output_name:
        output_name = os.path.splitext(os.path.basename(onnx_path))[0]

    output_path = os.path.join(output_dir, f"{output_name}_{target_platform}_{quantization}.rknn")

    try:
        rknn = RKNN(verbose=False)

        # Configure model
        config_kwargs = {
            "target_platform": target_platform.lower(),
        }
        if mean_values:
            config_kwargs["mean_values"] = [mean_values]
        if std_values:
            config_kwargs["std_values"] = [std_values]
        if quantization in ("int4", "int8", "int16"):
            config_kwargs["quantized_dtype"] = quantization
            config_kwargs["quantized_algorithm"] = "normal"

        ret = rknn.config(**config_kwargs)
        if ret != 0:
            return {"success": False, "error": f"RKNN config failed with code {ret}"}

        # Load ONNX model
        load_kwargs = {"model": onnx_path}
        if input_size:
            load_kwargs["inputs"] = ["input"]
            load_kwargs["input_size_list"] = [input_size]

        ret = rknn.load_onnx(**load_kwargs)
        if ret != 0:
            return {"success": False, "error": f"ONNX load failed with code {ret}"}

        # Build (quantize)
        build_kwargs = {
            "do_quantization": quantization not in ("fp16",),
        }
        if dataset_path and os.path.isfile(dataset_path):
            build_kwargs["dataset"] = dataset_path

        ret = rknn.build(**build_kwargs)
        if ret != 0:
            return {"success": False, "error": f"RKNN build/quantization failed with code {ret}"}

        # Export
        ret = rknn.export_rknn(output_path)
        if ret != 0:
            return {"success": False, "error": f"RKNN export failed with code {ret}"}

        rknn.release()

        file_size = os.path.getsize(output_path)
        platform_info = RKNN_TARGET_PLATFORMS[target_platform.lower()]

        return {
            "success": True,
            "output_path": output_path,
            "format": "rknn",
            "target_platform": target_platform,
            "quantization": quantization,
            "file_size": file_size,
            "file_size_human": _fmt_size(file_size),
            "npu_cores": platform_info["npu_cores"],
            "npu_tops": platform_info["tops"],
        }

    except Exception as e:
        return {"success": False, "error": f"RKNN conversion failed: {str(e)}"}


def verify_rknn_model(rknn_path: str, target_platform: str = "rk3588") -> dict:
    """Verify and profile an RKNN model using the simulator."""
    if not os.path.isfile(rknn_path):
        return {"success": False, "error": f"RKNN file not found: {rknn_path}"}

    try:
        from rknn.api import RKNN
    except ImportError:
        return {"success": False, "error": "rknn_toolkit2 not installed"}

    try:
        rknn = RKNN(verbose=False)
        ret = rknn.load_rknn(rknn_path)
        if ret != 0:
            return {"success": False, "error": f"Failed to load RKNN model: code {ret}"}

        # Init runtime (simulator mode)
        ret = rknn.init_runtime(target=target_platform.lower())
        if ret != 0:
            return {"success": False, "error": f"Runtime init failed: code {ret}"}

        # Get SDK version
        sdk_version = rknn.get_sdk_version()

        rknn.release()

        return {
            "success": True,
            "model_path": rknn_path,
            "target_platform": target_platform,
            "sdk_version": str(sdk_version) if sdk_version else None,
            "file_size": os.path.getsize(rknn_path),
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


# ── rk-llama.cpp Integration ───────────────────────────

def detect_rk_llama_cpp() -> dict:
    """Detect rk-llama.cpp (Rockchip NPU GGML backend) installation."""
    info = {
        "available": False,
        "server_path": None,
        "cli_path": None,
        "version": None,
        "backends": [],
    }

    # Search for rk-llama binaries
    for name in ["llama-server", "llama-cli", "rk-llama-server", "rk-llama-cli"]:
        try:
            result = subprocess.run(
                [name, "--version"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                info["available"] = True
                if "server" in name:
                    info["server_path"] = name
                else:
                    info["cli_path"] = name
                info["version"] = result.stdout.strip()[:100]
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

    # Check for RKNPU2 backend support
    if info["available"] and info["cli_path"]:
        try:
            result = subprocess.run(
                [info["cli_path"], "--help"],
                capture_output=True, text=True, timeout=5,
            )
            output = result.stdout + result.stderr
            for backend in ["RKNPU2", "CUDA", "Vulkan", "Metal", "OpenCL", "CPU"]:
                if backend.lower() in output.lower():
                    info["backends"].append(backend)
        except Exception:
            pass

    return info


def serve_gguf_on_rknpu(
    model_path: str,
    host: str = "0.0.0.0",
    port: int = 8081,
    ctx_size: int = 4096,
    n_gpu_layers: int = -1,
) -> dict:
    """Start an OpenAI-compatible server using rk-llama.cpp on Rockchip NPU.

    Returns connection info (does not block — starts in background).
    """
    rk_info = detect_rk_llama_cpp()
    if not rk_info["available"]:
        return {
            "success": False,
            "error": "rk-llama.cpp not found. Build from https://github.com/invisiofficial/rk-llama.cpp",
        }

    server_bin = rk_info.get("server_path", "llama-server")

    cmd = [
        server_bin,
        "-m", model_path,
        "--host", host,
        "--port", str(port),
        "-c", str(ctx_size),
        "-ngl", str(n_gpu_layers),
    ]

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return {
            "success": True,
            "pid": process.pid,
            "endpoint": f"http://{host}:{port}",
            "openai_base": f"http://{host}:{port}/v1",
            "model": model_path,
            "command": " ".join(cmd),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Utilities ───────────────────────────────────────────

def _fmt_size(size_bytes: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"
