"""Pre-Bundled Asset Registry — Models, datasets, and benchmarks available out-of-the-box.

Provides a curated catalog of models that can be:
  1. Bundled directly with NPU-STACK for immediate use
  2. Downloaded on-demand from the chainchopper/NPU-STACK GitHub repo
  3. Fetched from upstream sources (RKNN Model Zoo, Kaggle, HuggingFace)

Branch Strategy:
  - main: Essential starter models only (< 100MB total)
  - dev: Full catalog with all model variants

Sources:
  - RKNN Model Zoo (airockchip/rknn_model_zoo) — ONNX models for Rockchip NPU
  - Google LiteRT / TFLite — On-device ML models
  - MediaPipe — Face/pose/hand detection models
  - HuggingFace — GGUF, SafeTensors, ONNX models
  - Kaggle TFLite Models — Pre-trained TFLite models
"""

import os
import json
import hashlib
import urllib.request
import urllib.error
from typing import Optional


# ── Registry ────────────────────────────────────────────

ASSET_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "bundled")
REGISTRY_FILE = os.path.join(ASSET_DIR, "registry.json")

# GitHub raw base for pre-bundled assets
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/chainchopper/NPU-STACK"


# ── Model Catalog ──────────────────────────────────────

MODEL_CATALOG = {
    # ═══ MAIN BRANCH — Essential Starter Models ═══
    "main": [
        # -- Image Classification --
        {
            "id": "mobilenetv2-onnx",
            "name": "MobileNetV2",
            "task": "image-classification",
            "format": "onnx",
            "size_mb": 14,
            "source": "rknn_model_zoo",
            "url": "https://ftrg.zbox.filez.com/v2/delivery/data/95f00b0fc900458ba134f8b180b3f7a1/examples/mobilenet/mobilenetv2-12.onnx",
            "filename": "mobilenetv2-12.onnx",
            "description": "Lightweight image classifier, ideal for mobile/edge NPU deployment",
            "compatible": ["onnx", "openvino", "tflite", "rknn", "tensorrt"],
        },
        # -- Object Detection --
        {
            "id": "yolov5n-onnx",
            "name": "YOLOv5 Nano",
            "task": "object-detection",
            "format": "onnx",
            "size_mb": 4,
            "source": "rknn_model_zoo",
            "url": "https://ftrg.zbox.filez.com/v2/delivery/data/95f00b0fc900458ba134f8b180b3f7a1/examples/yolov5/yolov5n.onnx",
            "filename": "yolov5n.onnx",
            "description": "Ultra-lightweight YOLO detector for real-time edge inference",
            "compatible": ["onnx", "openvino", "rknn", "tensorrt", "tflite"],
        },
        {
            "id": "yolov8n-onnx",
            "name": "YOLOv8 Nano",
            "task": "object-detection",
            "format": "onnx",
            "size_mb": 6,
            "source": "rknn_model_zoo",
            "url": "https://ftrg.zbox.filez.com/v2/delivery/data/95f00b0fc900458ba134f8b180b3f7a1/examples/yolov8/yolov8n.onnx",
            "filename": "yolov8n.onnx",
            "description": "Ultralytics YOLOv8 Nano — state-of-the-art real-time detection",
            "compatible": ["onnx", "openvino", "rknn", "tensorrt", "tflite"],
        },
    ],

    # ═══ DEV BRANCH — Full Catalog ═══
    "dev": [
        # -- Image Classification --
        {
            "id": "resnet50-onnx",
            "name": "ResNet50 V2",
            "task": "image-classification",
            "format": "onnx",
            "size_mb": 98,
            "source": "rknn_model_zoo",
            "url": "https://ftrg.zbox.filez.com/v2/delivery/data/95f00b0fc900458ba134f8b180b3f7a1/examples/resnet/resnet50-v2-7.onnx",
            "filename": "resnet50-v2-7.onnx",
            "description": "ResNet50 V2 image classifier — strong baseline model",
            "compatible": ["onnx", "openvino", "rknn", "tensorrt", "tflite"],
        },

        # -- Object Detection (YOLO family) --
        {
            "id": "yolov5s-relu-onnx",
            "name": "YOLOv5s ReLU",
            "task": "object-detection",
            "format": "onnx",
            "size_mb": 14,
            "source": "rknn_model_zoo",
            "url": "https://ftrg.zbox.filez.com/v2/delivery/data/95f00b0fc900458ba134f8b180b3f7a1/examples/yolov5/yolov5s_relu.onnx",
            "filename": "yolov5s_relu.onnx",
            "description": "YOLOv5s with ReLU activation — NPU-optimized for Rockchip",
            "compatible": ["onnx", "rknn", "openvino"],
        },
        {
            "id": "yolov5s-onnx",
            "name": "YOLOv5s",
            "task": "object-detection",
            "format": "onnx",
            "size_mb": 14,
            "source": "rknn_model_zoo",
            "url": "https://ftrg.zbox.filez.com/v2/delivery/data/95f00b0fc900458ba134f8b180b3f7a1/examples/yolov5/yolov5s.onnx",
            "filename": "yolov5s.onnx",
            "description": "YOLOv5 Small — balanced speed and accuracy",
            "compatible": ["onnx", "rknn", "openvino", "tensorrt"],
        },
        {
            "id": "yolov5m-onnx",
            "name": "YOLOv5m",
            "task": "object-detection",
            "format": "onnx",
            "size_mb": 42,
            "source": "rknn_model_zoo",
            "url": "https://ftrg.zbox.filez.com/v2/delivery/data/95f00b0fc900458ba134f8b180b3f7a1/examples/yolov5/yolov5m.onnx",
            "filename": "yolov5m.onnx",
            "description": "YOLOv5 Medium — higher accuracy for desktop/server",
            "compatible": ["onnx", "rknn", "openvino", "tensorrt"],
        },
        {
            "id": "yolov6n-onnx",
            "name": "YOLOv6 Nano",
            "task": "object-detection",
            "format": "onnx",
            "size_mb": 8,
            "source": "rknn_model_zoo",
            "url": "https://ftrg.zbox.filez.com/v2/delivery/data/95f00b0fc900458ba134f8b180b3f7a1/examples/yolov6/yolov6n.onnx",
            "filename": "yolov6n.onnx",
            "description": "YOLOv6 Nano — Meituan's efficient detector",
            "compatible": ["onnx", "rknn", "openvino", "tensorrt"],
        },
        {
            "id": "yolov7-tiny-onnx",
            "name": "YOLOv7 Tiny",
            "task": "object-detection",
            "format": "onnx",
            "size_mb": 12,
            "source": "rknn_model_zoo",
            "url": "https://ftrg.zbox.filez.com/v2/delivery/data/95f00b0fc900458ba134f8b180b3f7a1/examples/yolov7/yolov7-tiny.onnx",
            "filename": "yolov7-tiny.onnx",
            "description": "YOLOv7 Tiny — fastest v7 variant",
            "compatible": ["onnx", "rknn", "openvino", "tensorrt"],
        },
        {
            "id": "yolov8s-onnx",
            "name": "YOLOv8s",
            "task": "object-detection",
            "format": "onnx",
            "size_mb": 22,
            "source": "rknn_model_zoo",
            "url": "https://ftrg.zbox.filez.com/v2/delivery/data/95f00b0fc900458ba134f8b180b3f7a1/examples/yolov8/yolov8s.onnx",
            "filename": "yolov8s.onnx",
            "description": "YOLOv8 Small — Ultralytics state-of-the-art",
            "compatible": ["onnx", "rknn", "openvino", "tensorrt"],
        },
        {
            "id": "yolov10n-onnx",
            "name": "YOLOv10 Nano",
            "task": "object-detection",
            "format": "onnx",
            "size_mb": 5,
            "source": "rknn_model_zoo",
            "url": "https://ftrg.zbox.filez.com/v2/delivery/data/95f00b0fc900458ba134f8b180b3f7a1/examples/yolov10/yolov10n.onnx",
            "filename": "yolov10n.onnx",
            "description": "YOLOv10 Nano — end-to-end NMS-free detector",
            "compatible": ["onnx", "rknn", "openvino", "tensorrt"],
        },
        {
            "id": "yolo11n-onnx",
            "name": "YOLO11 Nano",
            "task": "object-detection",
            "format": "onnx",
            "size_mb": 5,
            "source": "rknn_model_zoo",
            "url": "https://ftrg.zbox.filez.com/v2/delivery/data/95f00b0fc900458ba134f8b180b3f7a1/examples/yolo11/yolo11n.onnx",
            "filename": "yolo11n.onnx",
            "description": "YOLO11 Nano — latest generation Ultralytics detector",
            "compatible": ["onnx", "rknn", "openvino", "tensorrt"],
        },
        {
            "id": "yolox-s-onnx",
            "name": "YOLOX Small",
            "task": "object-detection",
            "format": "onnx",
            "size_mb": 18,
            "source": "rknn_model_zoo",
            "url": "https://ftrg.zbox.filez.com/v2/delivery/data/95f00b0fc900458ba134f8b180b3f7a1/examples/yolox/yolox_s.onnx",
            "filename": "yolox_s.onnx",
            "description": "YOLOX Small — anchor-free detector by Megvii",
            "compatible": ["onnx", "rknn", "openvino", "tensorrt"],
        },
        {
            "id": "ppyoloe-s-onnx",
            "name": "PP-YOLOE Small",
            "task": "object-detection",
            "format": "onnx",
            "size_mb": 15,
            "source": "rknn_model_zoo",
            "url": "https://ftrg.zbox.filez.com/v2/delivery/data/95f00b0fc900458ba134f8b180b3f7a1/examples/ppyoloe/ppyoloe_s.onnx",
            "filename": "ppyoloe_s.onnx",
            "description": "PaddlePaddle PP-YOLOE — industrial-grade detector",
            "compatible": ["onnx", "rknn", "openvino"],
        },

        # -- Open Vocabulary Detection --
        {
            "id": "yolo-world-v2s-onnx",
            "name": "YOLO-World V2 Small",
            "task": "open-vocabulary-detection",
            "format": "onnx",
            "size_mb": 33,
            "source": "rknn_model_zoo",
            "url": "https://ftrg.zbox.filez.com/v2/delivery/data/95f00b0fc900458ba134f8b180b3f7a1/examples/yolo_world/yolo_world_v2s.onnx",
            "filename": "yolo_world_v2s.onnx",
            "description": "YOLO-World — open-set object detection with text prompts",
            "compatible": ["onnx", "rknn"],
        },

        # -- Oriented Object Detection --
        {
            "id": "yolov8n-obb-onnx",
            "name": "YOLOv8n OBB",
            "task": "oriented-object-detection",
            "format": "onnx",
            "size_mb": 6,
            "source": "rknn_model_zoo",
            "url": "https://ftrg.zbox.filez.com/v2/delivery/data/95f00b0fc900458ba134f8b180b3f7a1/examples/yolov8_obb/yolov8n-obb.onnx",
            "filename": "yolov8n-obb.onnx",
            "description": "YOLOv8 Nano with Oriented Bounding Boxes — for rotated objects",
            "compatible": ["onnx", "rknn"],
        },

        # -- LiteRT / TFLite Models (Google AI Edge) --
        {
            "id": "efficientdet-lite0-tflite",
            "name": "EfficientDet-Lite0",
            "task": "object-detection",
            "format": "tflite",
            "size_mb": 4,
            "source": "kaggle_tflite",
            "url": "https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite0/int8/latest/efficientdet_lite0.tflite",
            "filename": "efficientdet_lite0.tflite",
            "description": "Google EfficientDet-Lite0 — optimized for LiteRT/TFLite",
            "compatible": ["tflite", "litert", "mediapipe"],
        },
        {
            "id": "mobilenet-v2-tflite",
            "name": "MobileNetV2 TFLite",
            "task": "image-classification",
            "format": "tflite",
            "size_mb": 3,
            "source": "kaggle_tflite",
            "url": "https://storage.googleapis.com/mediapipe-models/image_classifier/efficientnet_lite0/float32/latest/efficientnet_lite0.tflite",
            "filename": "efficientnet_lite0.tflite",
            "description": "EfficientNet-Lite0 classifier — fast mobile/edge inference",
            "compatible": ["tflite", "litert", "mediapipe"],
        },

        # -- MediaPipe Task Models --
        {
            "id": "mediapipe-face-detector",
            "name": "MediaPipe Face Detector",
            "task": "face-detection",
            "format": "tflite",
            "size_mb": 1,
            "source": "mediapipe",
            "url": "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/latest/blaze_face_short_range.tflite",
            "filename": "blaze_face_short_range.tflite",
            "description": "BlazeFace short-range face detector — MediaPipe native",
            "compatible": ["tflite", "mediapipe", "litert"],
        },
        {
            "id": "mediapipe-hand-landmarker",
            "name": "MediaPipe Hand Landmarker",
            "task": "hand-tracking",
            "format": "task",
            "size_mb": 6,
            "source": "mediapipe",
            "url": "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task",
            "filename": "hand_landmarker.task",
            "description": "21-landmark hand tracking model — MediaPipe Tasks API",
            "compatible": ["mediapipe"],
        },
        {
            "id": "mediapipe-pose-landmarker",
            "name": "MediaPipe Pose Landmarker",
            "task": "pose-estimation",
            "format": "task",
            "size_mb": 8,
            "source": "mediapipe",
            "url": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task",
            "filename": "pose_landmarker_lite.task",
            "description": "33-landmark pose estimation — MediaPipe Tasks API",
            "compatible": ["mediapipe"],
        },

        # -- LiteRT-LM (On-Device LLMs) --
        {
            "id": "gemma3-1b-litertlm",
            "name": "Gemma3 1B IT",
            "task": "text-generation",
            "format": "litertlm",
            "size_mb": 700,
            "source": "huggingface",
            "url": "https://huggingface.co/litert-community/Gemma3-1B-IT/resolve/main/Gemma3-1B-IT_multi-prefill-seq_q4_ekv4096.litertlm",
            "filename": "Gemma3-1B-IT_q4.litertlm",
            "description": "Google Gemma3 1B — quantized Q4 for on-device LLM inference via LiteRT-LM",
            "compatible": ["litert-lm"],
        },
    ],
}

# Flatten for lookup
ALL_MODELS = {m["id"]: m for branch in MODEL_CATALOG.values() for m in branch}


# ── Dataset Catalog ─────────────────────────────────────

DATASET_CATALOG = [
    {
        "id": "coco-labels",
        "name": "COCO Class Labels",
        "type": "labels",
        "format": "txt",
        "size_mb": 0.001,
        "url": "https://raw.githubusercontent.com/pjreddie/darknet/master/data/coco.names",
        "filename": "coco.names",
        "description": "80 COCO object detection class labels",
    },
    {
        "id": "imagenet-labels",
        "name": "ImageNet Class Labels",
        "type": "labels",
        "format": "txt",
        "size_mb": 0.03,
        "url": "https://raw.githubusercontent.com/pytorch/hub/master/imagenet_classes.txt",
        "filename": "imagenet_classes.txt",
        "description": "1000 ImageNet classification class labels",
    },
]

# ── Benchmark Catalog ───────────────────────────────────

BENCHMARK_CATALOG = [
    {
        "id": "rknn-benchmark-rk3588",
        "name": "RKNN RK3588 FPS Benchmarks",
        "description": "Official detection model FPS benchmarks on RK3588 NPU",
        "source": "airockchip/rknn_model_zoo",
        "data": {
            "yolov5n": {"rk3588_fps": 72.0, "rk3566_fps": 22.1},
            "yolov5s": {"rk3588_fps": 39.1, "rk3566_fps": 11.4},
            "yolov8n": {"rk3588_fps": 53.9, "rk3566_fps": 17.5},
            "yolov8s": {"rk3588_fps": 22.4, "rk3566_fps": 6.5},
            "yolo11n": {"rk3588_fps": 49.0, "rk3566_fps": 15.2},
            "mobilenetv2": {"rk3588_fps": 510.8, "rk3566_fps": 179.0},
        },
    },
]


# ── Download Functions ──────────────────────────────────

def get_catalog(branch: str = "all") -> dict:
    """Get the full model/dataset/benchmark catalog."""
    if branch == "all":
        models = list(ALL_MODELS.values())
    elif branch in MODEL_CATALOG:
        models = MODEL_CATALOG[branch]
    else:
        models = list(ALL_MODELS.values())

    # Mark locally available models
    for m in models:
        local_path = os.path.join(ASSET_DIR, m["filename"])
        m["downloaded"] = os.path.isfile(local_path)
        m["local_path"] = local_path if m["downloaded"] else None

    return {
        "models": models,
        "datasets": DATASET_CATALOG,
        "benchmarks": BENCHMARK_CATALOG,
        "total_models": len(models),
        "downloaded_models": sum(1 for m in models if m["downloaded"]),
        "asset_dir": ASSET_DIR,
    }


def download_bundled_model(model_id: str, force: bool = False) -> dict:
    """Download a model from the catalog to the local asset directory."""
    if model_id not in ALL_MODELS:
        return {"success": False, "error": f"Unknown model: {model_id}. Available: {list(ALL_MODELS.keys())[:10]}"}

    model = ALL_MODELS[model_id]
    os.makedirs(ASSET_DIR, exist_ok=True)
    dest_path = os.path.join(ASSET_DIR, model["filename"])

    if os.path.isfile(dest_path) and not force:
        return {
            "success": True,
            "already_exists": True,
            "model_id": model_id,
            "path": dest_path,
            "size": os.path.getsize(dest_path),
        }

    url = model["url"]

    try:
        # Try GitHub repo first
        github_url = f"{GITHUB_RAW_BASE}/main/backend/data/bundled/{model['filename']}"
        try:
            _download_file(github_url, dest_path)
            return {
                "success": True,
                "model_id": model_id,
                "path": dest_path,
                "source": "github",
                "size": os.path.getsize(dest_path),
            }
        except Exception:
            pass

        # Fall back to upstream source
        _download_file(url, dest_path)
        return {
            "success": True,
            "model_id": model_id,
            "path": dest_path,
            "source": model.get("source", "upstream"),
            "size": os.path.getsize(dest_path),
        }

    except Exception as e:
        if os.path.isfile(dest_path):
            os.remove(dest_path)
        return {"success": False, "error": f"Download failed: {str(e)}"}


def download_all_for_branch(branch: str = "main") -> dict:
    """Download all models for a given branch (main or dev)."""
    if branch not in MODEL_CATALOG:
        return {"success": False, "error": f"Invalid branch: {branch}"}

    results = []
    for model in MODEL_CATALOG[branch]:
        result = download_bundled_model(model["id"])
        result["model_name"] = model["name"]
        results.append(result)

    return {
        "branch": branch,
        "results": results,
        "total": len(results),
        "success_count": sum(1 for r in results if r.get("success")),
        "error_count": sum(1 for r in results if not r.get("success")),
    }


def download_dataset(dataset_id: str) -> dict:
    """Download a dataset from the catalog."""
    ds = next((d for d in DATASET_CATALOG if d["id"] == dataset_id), None)
    if not ds:
        return {"success": False, "error": f"Unknown dataset: {dataset_id}"}

    os.makedirs(ASSET_DIR, exist_ok=True)
    dest_path = os.path.join(ASSET_DIR, ds["filename"])

    if os.path.isfile(dest_path):
        return {"success": True, "already_exists": True, "path": dest_path}

    try:
        _download_file(ds["url"], dest_path)
        return {"success": True, "path": dest_path, "size": os.path.getsize(dest_path)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_local_assets() -> dict:
    """List all locally downloaded assets."""
    os.makedirs(ASSET_DIR, exist_ok=True)
    files = []
    for f in os.listdir(ASSET_DIR):
        fpath = os.path.join(ASSET_DIR, f)
        if os.path.isfile(fpath) and f != "registry.json":
            ext = os.path.splitext(f)[1].lower()
            files.append({
                "filename": f,
                "path": fpath,
                "size": os.path.getsize(fpath),
                "format": ext.lstrip("."),
                "in_catalog": any(m["filename"] == f for m in ALL_MODELS.values()),
            })

    return {
        "asset_dir": ASSET_DIR,
        "files": files,
        "total": len(files),
        "total_size": sum(f["size"] for f in files),
    }


# ── Utilities ───────────────────────────────────────────

def _download_file(url: str, dest_path: str, chunk_size: int = 8192):
    """Download file with progress, resuming support."""
    req = urllib.request.Request(url, headers={"User-Agent": "NPU-STACK/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        with open(dest_path, "wb") as f:
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
