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

    # ── OpenVINO devices (Intel NPU, GPU, GNA) ───────────
    try:
        import openvino as ov
        core = ov.Core()
        info["openvino_devices"] = core.available_devices
        info["npu_available"] = "NPU" in core.available_devices
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

    # ── ONNX Runtime providers ───────────────────────────
    try:
        import onnxruntime as ort
        info["onnxruntime_providers"] = ort.get_available_providers()
    except ImportError:
        info["onnxruntime_providers"] = []

    # ── DirectML (Windows GPU fallback for AMD/Intel/NVIDIA) ──
    info["directml_available"] = "DmlExecutionProvider" in info.get("onnxruntime_providers", [])

    # ── Capabilities summary with check/cross marks ──────
    info["capabilities"] = {
        "cuda_gpu": {"available": info.get("cuda_available", False), "label": "NVIDIA CUDA GPU"},
        "rocm_gpu": {"available": info.get("rocm_available", False), "label": "AMD ROCm GPU (RDNA/CDNA)"},
        "intel_npu": {"available": info.get("npu_available", False), "label": "Intel NPU"},
        "coral_tpu": {"available": info.get("coral_tpu_available", False), "label": "Google Coral Edge TPU"},
        "directml": {"available": info.get("directml_available", False), "label": "DirectML (Windows GPU)"},
        "openvino": {"available": len(info.get("openvino_devices", [])) > 0, "label": "OpenVINO Runtime"},
        "onnxruntime": {"available": len(info.get("onnxruntime_providers", [])) > 0, "label": "ONNX Runtime"},
        "cpu": {"available": True, "label": "CPU Inference"},
    }

    return info
