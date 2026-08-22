"""Nirvana audio routing — make the agent talk via Home Assistant (no ElevenLabs).

The XIAO has no DAC, so the agent "speaks" by routing TTS to a device that can
play it: Home Assistant's `tts` service (Piper / Google / Cloud — cheap/local,
NOT ElevenLabs in production), played on any media_player / ESPHome speaker.

Config (env or .env):
    HA_BASE_URL   e.g. http://homeassistant.local:8123
    HA_TOKEN      long-lived access token

Endpoints:
    GET  /api/nirvana/say/status   -> HA config + available TTS engines
    POST /api/nirvana/say          -> {text, entity_id?} -> HA tts.speak
"""
import os

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/nirvana", tags=["nirvana-audio"])


def _ha_base() -> str:
    return os.getenv("HA_BASE_URL", "http://homeassistant.local:8123").rstrip("/")


def _ha_token() -> str:
    return os.getenv("HA_TOKEN", "").strip()


class SayRequest(BaseModel):
    text: str
    entity_id: str = ""          # optional media_player entity to target
    engine: str = ""             # e.g. "piper" — blank = HA default TTS


@router.get("/say/status")
def say_status():
    """Show HA audio-routing config and what's available."""
    base = _ha_base()
    token = _ha_token()
    engines = []
    if token:
        try:
            r = httpx.get(base + "/api/states", headers={"Authorization": "Bearer " + token}, timeout=10)
            if r.status_code == 200:
                states = r.json()
                engines = sorted({
                    s["entity_id"] for s in states
                    if s["entity_id"].startswith("tts.")
                })
        except Exception:
            pass
    return {
        "ha_base_url": base,
        "configured": bool(token),
        "tts_engines": engines,
        "default_service": "tts.speak",
        "note": "Production TTS is Home Assistant (Piper/Google/Cloud) — ElevenLabs is test-only.",
    }


@router.post("/say")
def say(req: SayRequest):
    """Speak `text` through a Home Assistant TTS engine + media player."""
    token = _ha_token()
    if not token:
        raise HTTPException(400, "HA_TOKEN not configured — set it in .env")
    base = _ha_base()
    payload: dict = {"message": req.text}
    if req.entity_id:
        payload["media_player_entity_id"] = req.entity_id
    service = "tts." + (req.engine or "speak")
    try:
        r = httpx.post(
            base + "/api/services/" + service,
            headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
            json=payload,
            timeout=30,
        )
    except httpx.HTTPError as e:
        raise HTTPException(502, "Home Assistant unreachable: " + str(e))
    if r.status_code >= 400:
        raise HTTPException(r.status_code, "HA error: " + r.text[:300])
    return {
        "ok": True,
        "service": service,
        "text": req.text,
        "entity_id": req.entity_id or "(default)",
        "ha_status": r.status_code,
    }
