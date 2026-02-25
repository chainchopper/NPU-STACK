"""Webcam router — real-time object detection via WebSocket frame streaming."""

import base64
import json
import time
import io
from typing import Optional

import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

router = APIRouter(prefix="/api/webcam", tags=["webcam"])

# Global state for loaded detection model
_detection_model = None
_detection_model_path = None
_detection_backend = None  # "onnx", "openvino", "ultralytics"


def _load_onnx_model(model_path: str):
    """Load an ONNX model for object detection inference."""
    try:
        import onnxruntime as ort
        session = ort.InferenceSession(model_path)
        return {"type": "onnx", "session": session}
    except ImportError:
        raise RuntimeError("onnxruntime is not installed")


def _load_openvino_model(model_path: str):
    """Load an OpenVINO model for object detection inference."""
    try:
        from openvino.runtime import Core
        core = Core()
        model = core.read_model(model_path)
        compiled = core.compile_model(model, "AUTO")
        return {"type": "openvino", "model": compiled}
    except ImportError:
        raise RuntimeError("openvino is not installed")


def _load_ultralytics_model(model_path: str):
    """Load a YOLO model via ultralytics for object detection."""
    try:
        from ultralytics import YOLO
        model = YOLO(model_path)
        return {"type": "ultralytics", "model": model}
    except ImportError:
        raise RuntimeError("ultralytics is not installed. Install with: pip install ultralytics")


def _decode_frame(data: bytes) -> np.ndarray:
    """Decode a JPEG/PNG image from bytes to numpy array."""
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        return np.array(img)
    except ImportError:
        # Fallback to cv2
        import cv2
        nparr = np.frombuffer(data, np.uint8)
        return cv2.imdecode(nparr, cv2.IMREAD_COLOR)


def _run_ultralytics_inference(model_info: dict, frame: np.ndarray, conf: float = 0.5) -> list:
    """Run YOLO inference via ultralytics and return detections."""
    model = model_info["model"]
    results = model(frame, conf=conf, verbose=False)
    
    detections = []
    for result in results:
        boxes = result.boxes
        if boxes is None:
            continue
        for i in range(len(boxes)):
            box = boxes.xyxy[i].cpu().numpy()
            cls_id = int(boxes.cls[i].cpu().item())
            confidence = float(boxes.conf[i].cpu().item())
            label = result.names.get(cls_id, f"class_{cls_id}")
            
            detections.append({
                "x1": float(box[0]),
                "y1": float(box[1]),
                "x2": float(box[2]),
                "y2": float(box[3]),
                "label": label,
                "confidence": round(confidence, 3),
                "class_id": cls_id,
            })
    
    return detections


def _run_onnx_inference(model_info: dict, frame: np.ndarray, conf: float = 0.5) -> list:
    """Run ONNX model inference for object detection."""
    import cv2
    session = model_info["session"]
    
    input_info = session.get_inputs()[0]
    input_name = input_info.name
    input_shape = input_info.shape  # e.g., [1, 3, 640, 640]
    
    # Preprocess: resize and normalize
    h, w = input_shape[2], input_shape[3]
    img_resized = cv2.resize(frame, (w, h))
    img_float = img_resized.astype(np.float32) / 255.0
    img_transposed = np.transpose(img_float, (2, 0, 1))  # HWC -> CHW
    img_batch = np.expand_dims(img_transposed, axis=0)  # Add batch dim
    
    outputs = session.run(None, {input_name: img_batch})
    
    # Basic YOLO-style output parsing (output shape: [1, num_boxes, 85] or similar)
    detections = []
    if len(outputs) > 0:
        output = outputs[0]
        if len(output.shape) == 3:
            # Standard YOLO output: [batch, num_detections, 5 + num_classes]
            for det in output[0]:
                obj_conf = det[4] if len(det) > 4 else 0
                if obj_conf < conf:
                    continue
                if len(det) > 5:
                    class_scores = det[5:]
                    cls_id = int(np.argmax(class_scores))
                    cls_conf = float(class_scores[cls_id])
                    final_conf = float(obj_conf * cls_conf)
                else:
                    cls_id = 0
                    final_conf = float(obj_conf)
                
                if final_conf < conf:
                    continue
                    
                cx, cy, bw, bh = det[0], det[1], det[2], det[3]
                x1 = float((cx - bw / 2) * frame.shape[1] / w)
                y1 = float((cy - bh / 2) * frame.shape[0] / h)
                x2 = float((cx + bw / 2) * frame.shape[1] / w)
                y2 = float((cy + bh / 2) * frame.shape[0] / h)
                
                detections.append({
                    "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                    "label": f"class_{cls_id}",
                    "confidence": round(final_conf, 3),
                    "class_id": cls_id,
                })
    
    return detections


# ─── REST Endpoints ───────────────────────────────────────────────────────────


@router.post("/load")
def load_detection_model(
    model_path: str = Query(..., description="Path to model file (.onnx, .pt, .xml)"),
    backend: str = Query("auto", description="Backend: auto, onnx, openvino, ultralytics"),
):
    """Load an object detection model for webcam inference."""
    global _detection_model, _detection_model_path, _detection_backend
    
    import os
    if not os.path.exists(model_path):
        from fastapi import HTTPException
        raise HTTPException(404, f"Model not found: {model_path}")
    
    ext = os.path.splitext(model_path)[1].lower()
    
    if backend == "auto":
        if ext == ".xml":
            backend = "openvino"
        elif ext in (".pt", ".yaml"):
            backend = "ultralytics"
        else:
            backend = "onnx"
    
    if backend == "onnx":
        _detection_model = _load_onnx_model(model_path)
    elif backend == "openvino":
        _detection_model = _load_openvino_model(model_path)
    elif backend == "ultralytics":
        _detection_model = _load_ultralytics_model(model_path)
    else:
        from fastapi import HTTPException
        raise HTTPException(400, f"Unsupported backend: {backend}")
    
    _detection_model_path = model_path
    _detection_backend = backend
    
    return {
        "status": "loaded",
        "model_path": model_path,
        "backend": backend,
    }


@router.get("/status")
def get_webcam_status():
    """Get the current webcam detection model status."""
    return {
        "model_loaded": _detection_model is not None,
        "model_path": _detection_model_path,
        "backend": _detection_backend,
    }


@router.post("/unload")
def unload_detection_model():
    """Unload the current detection model."""
    global _detection_model, _detection_model_path, _detection_backend
    _detection_model = None
    _detection_model_path = None
    _detection_backend = None
    return {"status": "unloaded"}


# ─── WebSocket Endpoint ──────────────────────────────────────────────────────


@router.websocket("/stream")
async def webcam_stream(websocket: WebSocket):
    """WebSocket endpoint for real-time webcam object detection.
    
    Protocol:
    1. Client sends binary JPEG frames
    2. Server responds with JSON detection results
    
    Client can also send JSON config messages:
    {"type": "config", "confidence": 0.5, "max_detections": 20}
    """
    await websocket.accept()
    
    confidence_threshold = 0.5
    max_detections = 50
    frame_count = 0
    
    try:
        while True:
            data = await websocket.receive()
            
            # Handle text messages (config)
            if "text" in data:
                try:
                    msg = json.loads(data["text"])
                    if msg.get("type") == "config":
                        confidence_threshold = msg.get("confidence", confidence_threshold)
                        max_detections = msg.get("max_detections", max_detections)
                        await websocket.send_json({"type": "config_ack", **msg})
                    continue
                except json.JSONDecodeError:
                    continue
            
            # Handle binary frames
            if "bytes" not in data:
                continue
            
            frame_bytes = data["bytes"]
            if not frame_bytes:
                continue
            
            if _detection_model is None:
                await websocket.send_json({
                    "type": "error",
                    "message": "No detection model loaded. POST /api/webcam/load first.",
                })
                continue
            
            start_time = time.perf_counter()
            
            try:
                frame = _decode_frame(frame_bytes)
                
                # Run inference based on backend
                if _detection_model["type"] == "ultralytics":
                    detections = _run_ultralytics_inference(
                        _detection_model, frame, conf=confidence_threshold
                    )
                elif _detection_model["type"] == "onnx":
                    detections = _run_onnx_inference(
                        _detection_model, frame, conf=confidence_threshold
                    )
                else:
                    detections = []
                
                inference_ms = (time.perf_counter() - start_time) * 1000
                frame_count += 1
                
                # Limit detections
                detections = detections[:max_detections]
                
                await websocket.send_json({
                    "type": "detections",
                    "frame": frame_count,
                    "detections": detections,
                    "count": len(detections),
                    "inference_ms": round(inference_ms, 1),
                    "resolution": {"width": frame.shape[1], "height": frame.shape[0]},
                })
            
            except Exception as e:
                await websocket.send_json({
                    "type": "error",
                    "message": str(e),
                    "frame": frame_count,
                })
    
    except WebSocketDisconnect:
        pass
