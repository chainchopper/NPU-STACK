"""
Nirvana Multimodal Router — receives camera frames + audio from AMB82 agent,
processes through AI (cloud or local), returns TTS text + optional RGB565 image.

POST /api/nirvana/multimodal
  - multipart/form-data: camera=frame.jpg, audio=mic.wav (optional)
  - Returns JSON: { status, tts_text, image_base64, image_rgb565_len }
"""
from __future__ import annotations

import base64
import io
import json
import os
import struct
import time
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from PIL import Image

router = APIRouter(prefix="/api/nirvana", tags=["nirvana-multimodal"])

# ── Config ──
SAVE_DIR = Path(__file__).resolve().parent.parent / "data" / "nirvana-captures"
SAVE_DIR.mkdir(parents=True, exist_ok=True)

# AI provider config (from env or defaults)
OPENAI_BASE_URL = os.getenv("NIRVANA_AI_BASE_URL", "https://api.openai.com/v1")
OPENAI_API_KEY = os.getenv("NIRVANA_AI_API_KEY", os.getenv("OPENAI_API_KEY", ""))
OPENAI_MODEL = os.getenv("NIRVANA_AI_MODEL", "gpt-4o-mini")
USE_LOCAL_LLM = os.getenv("NIRVANA_USE_LOCAL_LLM", "0") == "1"
LOCAL_LLM_URL = os.getenv("NIRVANA_LOCAL_LLM_URL", "http://127.0.0.1:8010/v1")


def rgb565_from_image(img: Image.Image, width: int = 240, height: int = 160) -> bytes:
    """Convert a PIL Image to RGB565 byte array for ILI9341 display."""
    img = img.convert("RGB")
    img.thumbnail((width, height), Image.Resampling.LANCZOS)

    # Center on black canvas
    canvas = Image.new("RGB", (width, height), (0, 0, 0))
    canvas.paste(
        img, ((width - img.width) // 2, (height - img.height) // 2)
    )

    buf = bytearray()
    for y in range(canvas.height):
        for x in range(canvas.width):
            r, g, b = canvas.getpixel((x, y))
            # Pack RGB888 → RGB565
            rgb565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
            buf.extend(struct.pack("<H", rgb565))
    return bytes(buf)


async def _call_ai_vision(
    image_bytes: bytes,
    prompt: str = "Describe this image in one sentence. What do you see?",
) -> str:
    """Call OpenAI Vision API (or compatible local endpoint) with an image."""
    if not OPENAI_API_KEY and not USE_LOCAL_LLM:
        return "AI vision not configured. Set NIRVANA_AI_API_KEY in .env"

    base_url = LOCAL_LLM_URL if USE_LOCAL_LLM else OPENAI_BASE_URL
    model = OPENAI_MODEL
    headers = {}
    if not USE_LOCAL_LLM and OPENAI_API_KEY:
        headers["Authorization"] = f"Bearer {OPENAI_API_KEY}"

    # Encode image as base64 data URI
    b64 = base64.b64encode(image_bytes).decode()
    data_uri = f"data:image/jpeg;base64,{b64}"

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_uri, "detail": "low"}},
                ],
            }
        ],
        "max_tokens": 200,
        "temperature": 0.7,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{base_url}/chat/completions",
            json=payload,
            headers=headers,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        return f"AI error: HTTP {resp.status_code}"


@router.post("/multimodal")
async def multimodal_process(
    camera: Optional[UploadFile] = File(None),
    audio: Optional[UploadFile] = File(None),
    prompt: Optional[str] = Form(None),
):
    """
    Receive camera frame (JPEG) and optional audio from Nirvana OS agent.
    Process through AI vision model, return TTS text + optional display image.
    """
    t0 = time.monotonic()
    image_rgb565 = b""
    tts_text = ""
    saved_files = []

    # ── Save camera frame ──
    if camera and camera.filename:
        cam_bytes = await camera.read()
        ts = int(time.time())
        cam_path = SAVE_DIR / f"capture_{ts}.jpg"
        cam_path.write_bytes(cam_bytes)
        saved_files.append(str(cam_path.name))

        # ── AI Vision processing ──
        user_prompt = prompt or "Describe this scene in one short sentence."
        tts_text = await _call_ai_vision(cam_bytes, user_prompt)

    # ── Save audio ──
    if audio and audio.filename:
        aud_bytes = await audio.read()
        ts = int(time.time())
        aud_path = SAVE_DIR / f"audio_{ts}.wav"
        aud_path.write_bytes(aud_bytes)
        saved_files.append(str(aud_path.name))

    # ── Optional: generate a display image response ──
    # If the user prompt asked for visual output, we'd call DALL-E here
    # and convert to RGB565. For now, generate a status overlay.
    if camera and tts_text:
        # Create a simple status image showing the AI response
        img = Image.new("RGB", (240, 160), (10, 10, 30))
        # Would render text here with PIL ImageDraw

    elapsed = time.monotonic() - t0

    return {
        "status": "ok",
        "elapsed_ms": int(elapsed * 1000),
        "tts_text": tts_text,
        "image_rgb565_b64": base64.b64encode(image_rgb565).decode() if image_rgb565 else "",
        "image_rgb565_len": len(image_rgb565),
        "saved_files": saved_files,
    }


@router.get("/multimodal/status")
async def multimodal_status():
    """Check if the multimodal endpoint is configured and ready."""
    return {
        "status": "ok",
        "provider": "local" if USE_LOCAL_LLM else "openai",
        "model": OPENAI_MODEL,
        "has_api_key": bool(OPENAI_API_KEY) or USE_LOCAL_LLM,
        "captures_dir": str(SAVE_DIR),
        "capture_count": len(list(SAVE_DIR.glob("*.jpg"))),
    }
