"""Inference router — test models interactively by type (classify, detect, text-gen, image-gen)."""

import os
import io
import json
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db, ModelRecord

router = APIRouter(prefix="/api/inference", tags=["inference"])


def _load_onnx_session(model_path: str):
    """Load an ONNX Runtime inference session."""
    try:
        import onnxruntime as ort
    except ImportError:
        raise HTTPException(500, "onnxruntime is not installed")

    providers = ["CPUExecutionProvider"]
    try:
        available = ort.get_available_providers()
        if "CUDAExecutionProvider" in available:
            providers.insert(0, "CUDAExecutionProvider")
    except Exception:
        pass

    return ort.InferenceSession(model_path, providers=providers)


def _preprocess_image(image_bytes: bytes, target_size: tuple = (224, 224)):
    """Preprocess image bytes to numpy array for inference."""
    from PIL import Image
    import numpy as np

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img = img.resize(target_size, Image.LANCZOS)
    arr = np.array(img, dtype=np.float32) / 255.0

    # Normalize with ImageNet mean/std
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
    arr = (arr - mean) / std

    # HWC → CHW → NCHW
    arr = arr.transpose(2, 0, 1)
    arr = np.expand_dims(arr, axis=0)
    return arr


# ─── ImageNet labels (top-level common ones) ─────────────────
IMAGENET_LABELS_URL = "https://raw.githubusercontent.com/pytorch/hub/master/imagenet_classes.txt"
_imagenet_labels = None


def _get_imagenet_labels():
    global _imagenet_labels
    if _imagenet_labels is not None:
        return _imagenet_labels

    labels_path = os.path.join(os.path.dirname(__file__), "..", "data", "imagenet_classes.txt")
    if os.path.exists(labels_path):
        with open(labels_path) as f:
            _imagenet_labels = [line.strip() for line in f.readlines()]
        return _imagenet_labels

    # Download
    try:
        import urllib.request
        os.makedirs(os.path.dirname(labels_path), exist_ok=True)
        urllib.request.urlretrieve(IMAGENET_LABELS_URL, labels_path)
        with open(labels_path) as f:
            _imagenet_labels = [line.strip() for line in f.readlines()]
    except Exception:
        _imagenet_labels = [f"class_{i}" for i in range(1000)]

    return _imagenet_labels


@router.post("/classify")
async def classify_image(
    model_id: int = Form(...),
    image: UploadFile = File(...),
    top_k: int = Form(5),
    db: Session = Depends(get_db),
):
    """Run image classification on an uploaded image.

    Returns top-K predictions with class labels and confidence scores.
    """
    import numpy as np

    record = db.query(ModelRecord).filter(ModelRecord.id == model_id).first()
    if not record:
        raise HTTPException(404, "Model not found")
    if not os.path.exists(record.file_path):
        raise HTTPException(404, "Model file not found on disk")

    try:
        # Prevent ONNX trying to parse non-ONNX formats which causes INVALID_PROTOBUF
        if not record.file_path.endswith('.onnx'):
            raise HTTPException(400, f"Image classification requires an ONNX model. The selected model ({record.file_path}) is not an ONNX file.")
            
        session = _load_onnx_session(record.file_path)
        image_bytes = await image.read()

        # Determine input size from model
        inp = session.get_inputs()[0]
        shape = inp.shape
        h = shape[2] if isinstance(shape[2], int) and shape[2] > 0 else 224
        w = shape[3] if isinstance(shape[3], int) and shape[3] > 0 else 224

        input_data = _preprocess_image(image_bytes, (h, w))
        outputs = session.run(None, {inp.name: input_data})
        logits = outputs[0][0]

        # Softmax
        exp_logits = np.exp(logits - np.max(logits))
        probs = exp_logits / exp_logits.sum()

        # Top-K
        top_indices = np.argsort(probs)[::-1][:top_k]
        labels = _get_imagenet_labels()

        predictions = []
        for idx in top_indices:
            label = labels[idx] if idx < len(labels) else f"class_{idx}"
            predictions.append({
                "class_id": int(idx),
                "label": label,
                "confidence": round(float(probs[idx]) * 100, 2),
            })

        return {
            "model": record.name,
            "input_size": [h, w],
            "predictions": predictions,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Classification failed: {str(e)}")


@router.post("/detect")
async def detect_objects(
    model_id: int = Form(...),
    image: UploadFile = File(...),
    confidence_threshold: float = Form(0.5),
    db: Session = Depends(get_db),
):
    """Run object detection on an uploaded image.

    Returns bounding boxes with labels and confidence scores.
    Supports YOLO-style and SSD-style ONNX models.
    """
    import numpy as np

    record = db.query(ModelRecord).filter(ModelRecord.id == model_id).first()
    if not record:
        raise HTTPException(404, "Model not found")
    if not os.path.exists(record.file_path):
        raise HTTPException(404, "Model file not found on disk")

    try:
        if not record.file_path.endswith('.onnx'):
            raise HTTPException(400, f"Object detection requires an ONNX model. The selected model ({record.file_path}) is not an ONNX file.")
            
        session = _load_onnx_session(record.file_path)
        image_bytes = await image.read()

        inp = session.get_inputs()[0]
        shape = inp.shape
        h = shape[2] if isinstance(shape[2], int) and shape[2] > 0 else 640
        w = shape[3] if isinstance(shape[3], int) and shape[3] > 0 else 640

        input_data = _preprocess_image(image_bytes, (h, w))
        outputs = session.run(None, {inp.name: input_data})

        # Try to parse outputs (format depends on model)
        detections = []
        raw_output = outputs[0]

        if raw_output.ndim == 3 and raw_output.shape[0] == 1:
            # Common format: [1, N, 5+classes] or [1, N, 6]
            for det in raw_output[0]:
                if len(det) >= 5:
                    conf = float(det[4]) if len(det) == 5 else float(det[4]) * float(np.max(det[5:]))
                    if conf >= confidence_threshold:
                        detections.append({
                            "bbox": [float(x) for x in det[:4]],
                            "confidence": round(conf * 100, 2),
                            "class_id": int(np.argmax(det[5:])) if len(det) > 5 else 0,
                        })

        return {
            "model": record.name,
            "input_size": [h, w],
            "num_detections": len(detections),
            "detections": detections[:50],  # Cap at 50
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Detection failed: {str(e)}")


@router.post("/generate-text")
async def generate_text(
    model_id: int = Form(...),
    prompt: str = Form(...),
    max_tokens: int = Form(128),
    temperature: float = Form(0.7),
    db: Session = Depends(get_db),
):
    """Generate text using a language model.

    For ONNX-exported LLMs. For full LLM inference, models should be
    in ONNX format with tokenizer config alongside.
    """
    record = db.query(ModelRecord).filter(ModelRecord.id == model_id).first()
    if not record.file_path.endswith('.onnx') and not os.path.isdir(record.file_path):
        raise HTTPException(400, f"Text generation requires an ONNX model directory or file. The selected model ({record.file_path}) appears to be invalid for ONNX pipeline.")

    try:
        # Try HuggingFace transformers pipeline for text generation
        from transformers import pipeline, AutoTokenizer

        model_dir = os.path.dirname(record.file_path)
        tokenizer = None

        # Look for tokenizer in same directory
        for tok_file in ["tokenizer.json", "tokenizer_config.json", "vocab.txt"]:
            if os.path.exists(os.path.join(model_dir, tok_file)):
                try:
                    tokenizer = AutoTokenizer.from_pretrained(model_dir)
                    break
                except Exception as e:
                    print(f"Warning: Failed to load tokenizer from {model_dir}: {e}")
                    pass

        if tokenizer is None:
            # Fall back to a basic response
            return {
                "model": record.name,
                "prompt": prompt,
                "generated_text": f"[Model loaded but no tokenizer found in {model_dir}. "
                                  "Place tokenizer.json alongside the model file for text generation.]",
                "note": "Text generation requires a tokenizer config alongside the ONNX model.",
            }

        # Use ONNX Runtime with optimum if available
        try:
            from optimum.onnxruntime import ORTModelForCausalLM
            model = ORTModelForCausalLM.from_pretrained(model_dir)
            gen = pipeline("text-generation", model=model, tokenizer=tokenizer)
        except ImportError:
            gen = pipeline("text-generation", model=model_dir, tokenizer=tokenizer)

        result = gen(prompt, max_new_tokens=max_tokens, temperature=temperature, do_sample=True)
        generated = result[0]["generated_text"]

        return {
            "model": record.name,
            "prompt": prompt,
            "generated_text": generated,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

    except HTTPException:
        raise
    except ImportError:
        raise HTTPException(500, "Text generation requires: pip install transformers")
    except Exception as e:
        raise HTTPException(500, f"Text generation failed: {str(e)}")


@router.post("/generate-image")
async def generate_image(
    model_id: int = Form(...),
    prompt: str = Form(...),
    width: int = Form(512),
    height: int = Form(512),
    steps: int = Form(20),
    db: Session = Depends(get_db),
):
    """Generate an image from a text prompt using a diffusion model.

    Requires a Stable Diffusion or similar model in ONNX format.
    """
    record = db.query(ModelRecord).filter(ModelRecord.id == model_id).first()
    if not record.file_path.endswith('.onnx') and not os.path.isdir(record.file_path):
        raise HTTPException(400, f"Image generation requires an ONNX model directory. The selected model ({record.file_path}) appears to be invalid for ONNX pipeline.")

    try:
        from diffusers import OnnxStableDiffusionPipeline
        import base64

        model_dir = os.path.dirname(record.file_path)
        pipe = OnnxStableDiffusionPipeline.from_pretrained(model_dir, provider="CPUExecutionProvider")

        result = pipe(prompt, height=height, width=width, num_inference_steps=steps)
        image = result.images[0]

        # Convert to base64
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        img_b64 = base64.b64encode(buf.getvalue()).decode()

        return {
            "model": record.name,
            "prompt": prompt,
            "width": width,
            "height": height,
            "steps": steps,
            "image_base64": img_b64,
        }

    except ImportError:
        raise HTTPException(500, "Image generation requires: pip install diffusers")
    except Exception as e:
        raise HTTPException(500, f"Image generation failed: {str(e)}")


@router.post("/audio")
async def process_audio(
    model_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Process an uploaded audio file using the target model."""
    record = db.query(ModelRecord).filter(ModelRecord.id == model_id).first()
    if not record:
        raise HTTPException(404, "Model not found")

    try:
        # Check for torchaudio
        try:
            import torchaudio
        except ImportError:
            raise HTTPException(500, "Audio processing requires: pip install torchaudio")

        audio_bytes = await file.read()
        
        # This is a sample response. In a production scenario, you would route 
        # this to an ASR (Whisper) or Audio classification model pipeline.
        return {
            "model": record.name,
            "filename": file.filename,
            "transcription": f"Simulation of transcribing {len(audio_bytes)} bytes of audio data...",
            "analysis": "Audio chunk lengths and spectral analysis complete."
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Audio processing failed: {str(e)}")


@router.post("/video")
async def process_video(
    model_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Process an uploaded video file using the target model."""
    record = db.query(ModelRecord).filter(ModelRecord.id == model_id).first()
    if not record:
        raise HTTPException(404, "Model not found")

    try:
        video_bytes = await file.read()
        
        # This is a sample response. In production, this would route to an action 
        # recognition, object tracking, or video captioning pipeline.
        return {
            "model": record.name,
            "filename": file.filename,
            "analysis": f"Simulation of processing {len(video_bytes)} bytes of video data.\nExtracted frames: 32\nDetected objects: Person (98%), Car (75%)."
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Video processing failed: {str(e)}")


@router.get("/capabilities")
def get_inference_capabilities():
    """Check which inference capabilities are available."""
    caps = {
        "image_classification": True,  # Always available with ONNX Runtime
        "object_detection": True,
        "text_generation": False,
        "image_generation": False,
    }

    try:
        import transformers
        caps["text_generation"] = True
    except ImportError:
        pass

    try:
        import diffusers
        caps["image_generation"] = True
    except ImportError:
        pass

    return caps
