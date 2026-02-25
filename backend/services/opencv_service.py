"""OpenCV service — DNN inference, preprocessing, and camera utilities."""

import os
from typing import Optional


def get_opencv_info() -> dict:
    """Get OpenCV installation info and available backends."""
    try:
        import cv2
        build_info = cv2.getBuildInformation()
        
        backends = []
        if hasattr(cv2.dnn, 'getAvailableBackends'):
            for b in cv2.dnn.getAvailableBackends():
                backends.append({"backend": str(b[0]), "target": str(b[1])})

        targets = []
        for t in ["DNN_TARGET_CPU", "DNN_TARGET_OPENCL", "DNN_TARGET_CUDA",
                   "DNN_TARGET_CUDA_FP16", "DNN_TARGET_MYRIAD", "DNN_TARGET_FPGA"]:
            if hasattr(cv2.dnn, t):
                targets.append(t.replace("DNN_TARGET_", ""))

        return {
            "available": True,
            "version": cv2.__version__,
            "cuda_enabled": "CUDA:  YES" in build_info,
            "backends": backends,
            "targets": targets,
        }
    except ImportError:
        return {"available": False, "version": None}


def preprocess_image(image_bytes: bytes, target_size: tuple = (640, 640), normalize: bool = True):
    """Preprocess raw image bytes into a DNN-ready blob using OpenCV.
    
    Returns (blob, original_h, original_w) or raises ImportError.
    """
    import cv2
    import numpy as np

    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Failed to decode image")

    original_h, original_w = img.shape[:2]

    blob = cv2.dnn.blobFromImage(
        img,
        scalefactor=1 / 255.0 if normalize else 1.0,
        size=target_size,
        swapRB=True,
        crop=False,
    )
    return blob, original_h, original_w


def run_dnn_inference(model_path: str, image_bytes: bytes,
                      target_size: tuple = (640, 640),
                      confidence_threshold: float = 0.5,
                      backend: str = "default", target: str = "cpu"):
    """Run inference on an image using OpenCV's DNN module.
    
    Supports ONNX, Caffe, TensorFlow, and Darknet models.
    """
    import cv2
    import numpy as np

    ext = os.path.splitext(model_path)[1].lower()
    
    if ext == ".onnx":
        net = cv2.dnn.readNetFromONNX(model_path)
    elif ext in (".caffemodel", ".prototxt"):
        net = cv2.dnn.readNetFromCaffe(model_path)
    elif ext in (".pb", ".pbtxt"):
        net = cv2.dnn.readNetFromTensorflow(model_path)
    elif ext in (".weights", ".cfg"):
        net = cv2.dnn.readNetFromDarknet(model_path)
    else:
        raise ValueError(f"Unsupported model format for cv2.dnn: {ext}")

    # Set backend and target
    backend_map = {
        "default": cv2.dnn.DNN_BACKEND_DEFAULT,
        "opencv": cv2.dnn.DNN_BACKEND_OPENCV,
        "cuda": cv2.dnn.DNN_BACKEND_CUDA,
    }
    target_map = {
        "cpu": cv2.dnn.DNN_TARGET_CPU,
        "opencl": cv2.dnn.DNN_TARGET_OPENCL,
        "cuda": cv2.dnn.DNN_TARGET_CUDA,
        "cuda_fp16": cv2.dnn.DNN_TARGET_CUDA_FP16,
    }
    net.setPreferableBackend(backend_map.get(backend, cv2.dnn.DNN_BACKEND_DEFAULT))
    net.setPreferableTarget(target_map.get(target, cv2.dnn.DNN_TARGET_CPU))

    blob, orig_h, orig_w = preprocess_image(image_bytes, target_size)
    net.setInput(blob)

    outputs = net.forward(net.getUnconnectedOutLayersNames())

    return {
        "outputs": [o.tolist() for o in outputs],
        "original_size": [orig_h, orig_w],
        "inference_backend": backend,
        "inference_target": target,
    }


def list_cameras(max_check: int = 5) -> list:
    """Enumerate available cameras using OpenCV VideoCapture."""
    try:
        import cv2
    except ImportError:
        return []

    cameras = []
    for i in range(max_check):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            cameras.append({
                "index": i,
                "resolution": f"{w}x{h}",
                "fps": round(fps, 1) if fps > 0 else "N/A",
            })
            cap.release()
    return cameras
