"""LuckFox RV1103/RV1106 NPU Service — RKNN model deployment & inference management.

Handles RKNN model detection, loading, and inference on LuckFox Pico boards
with the built-in NPU (0.5 TOPS RV1103 / 1 TOPS RV1106).

Requires LuckFox board running Linux (Buildroot) with RKNN toolkit installed.
Communication via SSH/SCP for model push, MQTT for inference control.
"""

from __future__ import annotations

import json, os, subprocess, sys, time
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parents[2]
MODELS_DIR = REPO / "backend" / "data" / "rknn_models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

# ── LuckFox NPU Capabilities ──────────────────────────────────────────────

NPU_SPECS = {
    "rv1103": {
        "chip": "RV1103",
        "tops": 0.5,
        "memory": "64MB DDR2",
        "frameworks": ["rknn", "tflite", "onnx"],
        "supported_models": ["mobilenet", "yolo-nano", "efficientnet-lite", "resnet18"],
        "max_input": "640x640",
    },
    "rv1106": {
        "chip": "RV1106",
        "tops": 1.0,
        "memory": "256MB DDR3",
        "frameworks": ["rknn", "tflite", "onnx", "caffe"],
        "supported_models": ["mobilenet", "yolo-fastest", "efficientnet", "resnet50", "yolov5n"],
        "max_input": "1920x1080",
    },
    "rk3588": {
        "chip": "RK3588",
        "tops": 6.0,
        "memory": "4GB+ LPDDR4",
        "frameworks": ["rknn", "tflite", "onnx", "caffe", "pytorch"],
        "supported_models": ["yolov8", "resnet101", "bert-tiny", "whisper-tiny"],
        "max_input": "4096x4096",
    },
}


def detect_luckfox_npu(chip: str = "auto") -> Dict[str, Any]:
    """Get NPU specs for a LuckFox chip variant.

    Returns capabilities: TOPS, memory, supported frameworks and models.
    """
    if chip in NPU_SPECS:
        return {"success": True, **NPU_SPECS[chip]}

    # Try to detect via SSH
    if chip == "auto":
        for variant in ["rv1106", "rv1103"]:
            specs = NPU_SPECS[variant]
            # Check if /usr/lib/librknn_api.so exists via rockusb or MQTT
            # For now, return all variants for catalog display
            pass

    return {
        "success": True,
        "variants": NPU_SPECS,
        "note": "Connect LuckFox board to auto-detect exact variant",
    }


def list_rknn_models() -> List[Dict[str, Any]]:
    """List downloaded RKNN model files."""
    models = []
    for f in sorted(MODELS_DIR.glob("*.rknn"), key=lambda x: x.stat().st_mtime, reverse=True):
        models.append({
            "name": f.stem,
            "path": str(f),
            "size_kb": round(f.stat().st_size / 1024, 1),
            "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(f.stat().st_mtime)),
        })
    return models


def push_model_to_luckfox(
    model_path: str,
    device_ip: str,
    target_dir: str = "/userdata/models/",
) -> Dict[str, Any]:
    """Push an RKNN model to a LuckFox board via SCP."""
    src = Path(model_path)
    if not src.exists():
        return {"success": False, "error": f"Model not found: {model_path}"}

    try:
        r = subprocess.run(
            ["scp", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=10",
             str(src), f"root@{device_ip}:{target_dir}{src.name}"],
            capture_output=True, text=True, timeout=60,
        )
        if r.returncode == 0:
            return {
                "success": True,
                "model": src.name,
                "device": device_ip,
                "target": f"{target_dir}{src.name}",
            }
        return {"success": False, "error": r.stderr.strip()[-300:]}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "SCP push timed out"}
    except FileNotFoundError:
        # Fallback: provide curl command the device can use to download
        return {
            "success": False,
            "error": "scp not found on this system",
            "alternative": "Use the fleet download endpoint to trigger device-side download",
        }


def run_rknn_inference(
    device_ip: str,
    model_name: str,
    input_source: str = "camera",
) -> Dict[str, Any]:
    """Trigger RKNN inference on a LuckFox device.

    Sends an MQTT command to start inference with the specified model.
    The device streams results back via MQTT.
    """
    import paho.mqtt.client as mqtt

    cmd = {
        "command": "RUN_RKNN",
        "model": model_name,
        "input": input_source,  # "camera" or "file:<path>"
    }

    try:
        client = mqtt.Client(client_id="npu-stack-rknn", protocol=mqtt.MQTTv311)
        client.connect("127.0.0.1", 1883, 5)
        client.publish(f"fleet/cmd/{device_ip}/rknn", json.dumps(cmd))
        client.disconnect()
        return {"success": True, "command": cmd, "note": "Inference queued - results via fleet/response topic"}
    except Exception as e:
        return {"success": False, "error": f"MQTT publish failed: {e}"}
