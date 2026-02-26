"""Benchmark service — real inference benchmarking across runtimes and devices."""

import os
import time
import tracemalloc
from typing import Optional

import numpy as np

MODEL_STORE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "models")


def _generate_random_input(session_or_model, runtime: str, batch_size: int = 1):
    """Generate random input data matching model input requirements."""
    if runtime == "onnxruntime":
        import onnxruntime as ort
        inp = session_or_model.get_inputs()[0]
        shape = list(inp.shape)
        # Replace dynamic dims
        shape = [batch_size if i == 0 else (s if isinstance(s, int) and s > 0 else 224) for i, s in enumerate(shape)]
        return {inp.name: np.random.randn(*shape).astype(np.float32)}
    elif runtime == "openvino":
        import openvino as ov
        input_layer = session_or_model.input(0)
        shape = list(input_layer.shape)
        shape = [batch_size if i == 0 else (s if s > 0 else 224) for i, s in enumerate(shape)]
        return np.random.randn(*shape).astype(np.float32)
    raise ValueError(f"Unknown runtime: {runtime}")


def benchmark_onnxruntime(
    model_path: str,
    device: str = "cpu",
    batch_size: int = 1,
    warmup_runs: int = 10,
    num_iterations: int = 100,
) -> dict:
    """
    Benchmark an ONNX model using ONNX Runtime.
    
    Supports CPU and OpenVINO execution providers for NPU inference.
    """
    import onnxruntime as ort

    # Select execution provider
    providers = []
    if device == "npu" or device == "openvino":
        providers.append(("OpenVINOExecutionProvider", {"device_type": "NPU"}))
        providers.append("CPUExecutionProvider")
    elif device == "cuda":
        providers.append("CUDAExecutionProvider")
        providers.append("CPUExecutionProvider")
    else:
        providers.append("CPUExecutionProvider")

    try:
        session = ort.InferenceSession(model_path, providers=providers)
    except Exception:
        # Fall back to CPU if requested provider not available
        session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
        device = "cpu (fallback)"

    active_provider = session.get_providers()[0]
    input_data = _generate_random_input(session, "onnxruntime", batch_size)

    # Warmup
    for _ in range(warmup_runs):
        session.run(None, input_data)

    # Benchmark
    tracemalloc.start()
    latencies = []
    for _ in range(num_iterations):
        start = time.perf_counter()
        session.run(None, input_data)
        latencies.append((time.perf_counter() - start) * 1000)  # ms

    _, peak_memory = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    latencies_arr = np.array(latencies)

    return {
        "runtime": "onnxruntime",
        "active_provider": active_provider,
        "device": device,
        "batch_size": batch_size,
        "warmup_runs": warmup_runs,
        "num_iterations": num_iterations,
        "latency_mean_ms": round(float(np.mean(latencies_arr)), 3),
        "latency_p50_ms": round(float(np.percentile(latencies_arr, 50)), 3),
        "latency_p95_ms": round(float(np.percentile(latencies_arr, 95)), 3),
        "latency_p99_ms": round(float(np.percentile(latencies_arr, 99)), 3),
        "latency_min_ms": round(float(np.min(latencies_arr)), 3),
        "latency_max_ms": round(float(np.max(latencies_arr)), 3),
        "throughput_fps": round(1000.0 / float(np.mean(latencies_arr)) * batch_size, 2),
        "memory_peak_mb": round(peak_memory / 1024 / 1024, 2),
    }


def benchmark_openvino(
    model_path: str,
    device: str = "CPU",
    batch_size: int = 1,
    warmup_runs: int = 10,
    num_iterations: int = 100,
) -> dict:
    """
    Benchmark a model using OpenVINO Runtime.
    
    Supports CPU and NPU devices for Intel Core Ultra processors.
    """
    import openvino as ov

    core = ov.Core()
    available_devices = core.available_devices

    # Load model (ONNX or OpenVINO IR)
    if model_path.endswith(".onnx"):
        model = core.read_model(model_path)
    else:
        model = core.read_model(model_path)

    # Compile for target device
    target_device = device.upper()
    if target_device not in available_devices and target_device != "AUTO":
        target_device = "CPU"

    compiled = core.compile_model(model, target_device)
    infer_request = compiled.create_infer_request()

    # Generate input
    input_layer = compiled.input(0)
    shape = list(input_layer.shape)
    shape = [batch_size if i == 0 else (s if s > 0 else 224) for i, s in enumerate(shape)]
    input_data = np.random.randn(*shape).astype(np.float32)

    # Warmup
    for _ in range(warmup_runs):
        infer_request.infer({0: input_data})

    # Benchmark
    tracemalloc.start()
    latencies = []
    for _ in range(num_iterations):
        start = time.perf_counter()
        infer_request.infer({0: input_data})
        latencies.append((time.perf_counter() - start) * 1000)

    _, peak_memory = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    latencies_arr = np.array(latencies)

    return {
        "runtime": "openvino",
        "device": target_device,
        "available_devices": available_devices,
        "batch_size": batch_size,
        "warmup_runs": warmup_runs,
        "num_iterations": num_iterations,
        "latency_mean_ms": round(float(np.mean(latencies_arr)), 3),
        "latency_p50_ms": round(float(np.percentile(latencies_arr, 50)), 3),
        "latency_p95_ms": round(float(np.percentile(latencies_arr, 95)), 3),
        "latency_p99_ms": round(float(np.percentile(latencies_arr, 99)), 3),
        "latency_min_ms": round(float(np.min(latencies_arr)), 3),
        "latency_max_ms": round(float(np.max(latencies_arr)), 3),
        "throughput_fps": round(1000.0 / float(np.mean(latencies_arr)) * batch_size, 2),
        "memory_peak_mb": round(peak_memory / 1024 / 1024, 2),
    }


def get_system_info() -> dict:
    """Get system hardware info relevant to NPU/TPU/GPU capabilities."""
    import psutil
    import platform

    info = {
        "platform": platform.platform(),
        "processor": platform.processor(),
        "cpu_count": psutil.cpu_count(logical=True),
        "cpu_count_physical": psutil.cpu_count(logical=False),
        "memory_total_gb": round(psutil.virtual_memory().total / (1024 ** 3), 1),
        "memory_available_gb": round(psutil.virtual_memory().available / (1024 ** 3), 1),
    }

    # ── Enumerate all CUDA GPUs ──────────────────────────
    gpus = []
    try:
        import torch
        info["cuda_available"] = torch.cuda.is_available()
        info["cuda_version"] = getattr(torch.version, "cuda", None)
        info["torch_version"] = torch.__version__

        # cuDNN
        try:
            if torch.backends.cudnn.is_available():
                info["cudnn_version"] = str(torch.backends.cudnn.version())
                info["cudnn_enabled"] = torch.backends.cudnn.enabled
            else:
                info["cudnn_version"] = None
        except Exception:
            info["cudnn_version"] = None

        if torch.cuda.is_available():
            gpu_count = torch.cuda.device_count()
            info["cuda_device_count"] = gpu_count
            for i in range(gpu_count):
                name = torch.cuda.get_device_name(i)
                props = torch.cuda.get_device_properties(i)
                mem = getattr(props, 'total_memory', None) or getattr(props, 'total_mem', 0)
                gpus.append({
                    "index": i,
                    "name": name,
                    "type": "CUDA",
                    "memory_gb": round(mem / (1024 ** 3), 1) if mem else 0,
                    "compute_capability": f"{props.major}.{props.minor}",
                    "status": "online",
                })
            # Backward compat
            info["cuda_device"] = gpus[0]["name"] if gpus else None
            info["cuda_memory_gb"] = gpus[0]["memory_gb"] if gpus else 0
    except (ImportError, Exception):
        info["cuda_available"] = False
        info["cuda_version"] = None

    # ── NVIDIA driver version + live GPU stats via NVML ──
    try:
        import subprocess
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=driver_version,temperature.gpu,utilization.gpu,power.draw",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            for idx, line in enumerate(result.stdout.strip().split("\n")):
                parts = [p.strip() for p in line.split(",")]
                if idx == 0:
                    info["nvidia_driver_version"] = parts[0]
                if idx < len(gpus):
                    try:
                        gpus[idx]["temperature_c"] = int(parts[1]) if len(parts) > 1 else None
                        gpus[idx]["utilization_pct"] = int(parts[2]) if len(parts) > 2 else None
                        gpus[idx]["power_draw_w"] = float(parts[3]) if len(parts) > 3 else None
                    except (ValueError, IndexError):
                        pass
    except Exception:
        pass

    # ── AMD ROCm / HIP detection ─────────────────────────
    info["rocm_available"] = False
    try:
        import torch
        if hasattr(torch.version, 'hip') and torch.version.hip is not None:
            info["rocm_available"] = True
            info["rocm_version"] = torch.version.hip
            if torch.cuda.is_available():  # ROCm uses CUDA API
                for i in range(torch.cuda.device_count()):
                    name = torch.cuda.get_device_name(i)
                    if not any(g["name"] == name for g in gpus):
                        props = torch.cuda.get_device_properties(i)
                        mem = getattr(props, 'total_memory', None) or getattr(props, 'total_mem', 0)
                        gpus.append({
                            "index": i,
                            "name": name,
                            "type": "ROCm (AMD)",
                            "memory_gb": round(mem / (1024 ** 3), 1) if mem else 0,
                            "compute_capability": f"gfx{props.gcnArchName}" if hasattr(props, 'gcnArchName') else "RDNA/CDNA",
                            "status": "online",
                        })
    except Exception:
        pass

    info["gpus"] = gpus

    # ── AMD Vitis AI / Alveo FPGA detection ──────────────
    info["vitis_ai_available"] = False
    try:
        import vai_q_onnx
        info["vitis_ai_available"] = True
        info["vitis_ai_version"] = getattr(vai_q_onnx, "__version__", "installed")
    except ImportError:
        pass

    info["alveo_available"] = False
    try:
        import subprocess
        # Check for Xilinx runtime tools
        result = subprocess.run(["xbutil", "examine"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            info["alveo_available"] = True
            info["alveo_info"] = result.stdout[:500]
    except Exception:
        pass

    # Check for Quark quantizer (AMD's newer quantization tool)
    info["quark_available"] = False
    try:
        import quark
        info["quark_available"] = True
        info["quark_version"] = getattr(quark, "__version__", "installed")
    except ImportError:
        pass

    # ── OpenVINO devices (Intel NPU, GPU, GNA) ───────────
    try:
        import openvino as ov
        core = ov.Core()
        info["openvino_devices"] = core.available_devices
        info["npu_available"] = "NPU" in core.available_devices
        info["openvino_version"] = ov.__version__
    except ImportError:
        info["openvino_devices"] = []
        info["npu_available"] = False

    # ── Google Coral Edge TPU ────────────────────────────
    info["coral_tpu_available"] = False
    try:
        import tflite_runtime.interpreter as tflite
        delegates = tflite.load_delegate('libedgetpu.so.1', {})
        info["coral_tpu_available"] = True
        info["coral_tpu_delegate"] = "Edge TPU"
    except Exception:
        try:
            # Windows path
            import tflite_runtime.interpreter as tflite
            delegates = tflite.load_delegate('edgetpu.dll', {})
            info["coral_tpu_available"] = True
            info["coral_tpu_delegate"] = "Edge TPU (Windows)"
        except Exception:
            pass

    # ── Rockchip RKNN NPU (RK3588, RV1103, etc.) ────────
    info["rknn_available"] = False
    try:
        from services.rknn_service import detect_rknn_environment, detect_rk_llama_cpp
        rknn_env = detect_rknn_environment()
        info["rknn_available"] = rknn_env["rknn_toolkit2_available"] or rknn_env["rknn_lite2_available"]
        info["rknn_toolkit2_version"] = rknn_env.get("rknn_toolkit2_version")
        info["rknn_soc"] = rknn_env.get("soc_detected")
        info["rknn_npu_driver"] = rknn_env.get("npu_driver_version")
        info["rknn_supported_platforms"] = rknn_env.get("supported_platforms", [])

        rk_llama = detect_rk_llama_cpp()
        info["rk_llama_cpp_available"] = rk_llama["available"]
        info["rk_llama_cpp_backends"] = rk_llama.get("backends", [])
    except Exception:
        pass

    # ── ONNX Runtime providers ───────────────────────────
    try:
        import onnxruntime as ort
        info["onnxruntime_providers"] = ort.get_available_providers()
        info["onnxruntime_version"] = ort.__version__
    except ImportError:
        info["onnxruntime_providers"] = []

    # ── DirectML (Windows GPU fallback for AMD/Intel/NVIDIA) ──
    info["directml_available"] = "DmlExecutionProvider" in info.get("onnxruntime_providers", [])

    # ── OpenCV detection ─────────────────────────────────
    info["opencv_available"] = False
    try:
        import cv2
        info["opencv_available"] = True
        info["opencv_version"] = cv2.__version__

        # Check for CUDA-enabled OpenCV
        build_info = cv2.getBuildInformation()
        info["opencv_cuda"] = "CUDA:  YES" in build_info
        info["opencv_dnn_backends"] = []
        if hasattr(cv2.dnn, 'getAvailableBackends'):
            backends = cv2.dnn.getAvailableBackends()
            info["opencv_dnn_backends"] = [
                {"backend": str(b[0]), "target": str(b[1])} for b in backends
            ]
        # DNN inference targets
        info["opencv_dnn_targets"] = []
        for target_name in ["DNN_TARGET_CPU", "DNN_TARGET_OPENCL", "DNN_TARGET_CUDA",
                            "DNN_TARGET_CUDA_FP16", "DNN_TARGET_MYRIAD", "DNN_TARGET_FPGA"]:
            if hasattr(cv2.dnn, target_name):
                info["opencv_dnn_targets"].append(target_name.replace("DNN_TARGET_", ""))
    except ImportError:
        pass

    # ── MediaPipe (Google AI Edge) ────────────────────────
    info["mediapipe_available"] = False
    try:
        from services.mediapipe_service import detect_mediapipe
        mp_info = detect_mediapipe()
        info["mediapipe_available"] = mp_info["available"]
        info["mediapipe_version"] = mp_info.get("version")
        info["mediapipe_gpu"] = mp_info.get("gpu_available", False)
        info["mediapipe_tasks"] = mp_info.get("tasks", [])
    except Exception:
        pass

    # ── GPU Compute: CUPTI, NVCC, OpenGL ES, MESA, Vulkan ──
    try:
        from services.mediapipe_service import detect_gpu_compute
        gpu_info = detect_gpu_compute()
        info["opengl_es_version"] = gpu_info.get("opengl_es_version")
        info["mesa_version"] = gpu_info.get("mesa_version")
        info["vulkan_available"] = gpu_info.get("vulkan_available", False)
        info["vulkan_version"] = gpu_info.get("vulkan_version")
        info["cupti_available"] = gpu_info.get("cupti_available", False)
        info["cupti_version"] = gpu_info.get("cupti_version")
        info["nvcc_available"] = gpu_info.get("nvcc_available", False)
        info["nvcc_version"] = gpu_info.get("nvcc_version")
    except Exception:
        pass

    # ── LiteRT / TFLite Ecosystem ────────────────────────
    try:
        from services.litert_service import detect_litert
        lt_info = detect_litert()
        info["litert_available"] = lt_info.get("litert_available", False)
        info["litert_version"] = lt_info.get("litert_version")
        info["tflite_available"] = lt_info.get("tflite_available", False)
        info["litert_torch_available"] = lt_info.get("litert_torch_available", False)
        info["litert_lm_available"] = lt_info.get("litert_lm_available", False)
        info["xnnpack_available"] = lt_info.get("xnnpack_available", False)
        info["litert_delegates"] = lt_info.get("delegates", [])
    except Exception:
        pass

    # ── Pre-bundled Assets ────────────────────────────────
    try:
        from services.model_registry import get_catalog
        cat = get_catalog("all")
        info["bundled_models_available"] = cat.get("total_models", 0)
        info["bundled_models_downloaded"] = cat.get("downloaded_models", 0)
    except Exception:
        pass

    # ── Capabilities summary with check/cross marks ──────
    info["capabilities"] = {
        "cuda_gpu": {"available": info.get("cuda_available", False), "label": f"NVIDIA CUDA GPU (CUDA {info.get('cuda_version', 'N/A')})"},
        "rocm_gpu": {"available": info.get("rocm_available", False), "label": "AMD ROCm GPU (RDNA/CDNA)"},
        "vitis_ai": {"available": info.get("vitis_ai_available", False), "label": "AMD Vitis AI Quantization"},
        "alveo_fpga": {"available": info.get("alveo_available", False), "label": "AMD/Xilinx Alveo FPGA"},
        "quark": {"available": info.get("quark_available", False), "label": "AMD Quark Quantizer"},
        "intel_npu": {"available": info.get("npu_available", False), "label": "Intel NPU"},
        "coral_tpu": {"available": info.get("coral_tpu_available", False), "label": "Google Coral Edge TPU"},
        "rknn_npu": {"available": info.get("rknn_available", False), "label": "Rockchip RKNN NPU"},
        "rk_llama": {"available": info.get("rk_llama_cpp_available", False), "label": "rk-llama.cpp (NPU LLM)"},
        "mediapipe": {"available": info.get("mediapipe_available", False), "label": f"MediaPipe ({info.get('mediapipe_version', 'N/A')})"},
        "directml": {"available": info.get("directml_available", False), "label": "DirectML (Windows GPU)"},
        "openvino": {"available": len(info.get("openvino_devices", [])) > 0, "label": f"OpenVINO Runtime ({info.get('openvino_version', 'N/A')})"},
        "onnxruntime": {"available": len(info.get("onnxruntime_providers", [])) > 0, "label": f"ONNX Runtime ({info.get('onnxruntime_version', 'N/A')})"},
        "opencv": {"available": info.get("opencv_available", False), "label": f"OpenCV ({info.get('opencv_version', 'N/A')})"},
        "cupti": {"available": info.get("cupti_available", False), "label": "NVIDIA CUPTI (Profiling)"},
        "nvcc": {"available": info.get("nvcc_available", False), "label": f"NVCC Compiler ({info.get('nvcc_version', 'N/A')})"},
        "vulkan": {"available": info.get("vulkan_available", False), "label": f"Vulkan ({info.get('vulkan_version', 'N/A')})"},
        "litert": {"available": info.get("litert_available", False) or info.get("tflite_available", False), "label": f"LiteRT/TFLite ({info.get('litert_version') or info.get('tflite_version', 'N/A')})"},
        "litert_torch": {"available": info.get("litert_torch_available", False), "label": "litert-torch (PyTorch→TFLite)"},
        "litert_lm": {"available": info.get("litert_lm_available", False), "label": "LiteRT-LM (On-Device LLM)"},
        "xnnpack": {"available": info.get("xnnpack_available", False), "label": "XNNPACK (CPU Acceleration)"},
        "bundled_models": {"available": info.get("bundled_models_downloaded", 0) > 0, "label": f"Pre-bundled Models ({info.get('bundled_models_downloaded', 0)}/{info.get('bundled_models_available', 0)})"},
        "cpu": {"available": True, "label": "CPU Inference"},
    }

    return info
