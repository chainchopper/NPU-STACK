"""
XiaoZhi Fleet Voice Router — REST API for fleet voice control.

Endpoints:
  GET  /api/fleet/voice/sessions       — list active voice sessions
  POST /api/fleet/voice/{device_id}/tts  — send TTS to device
  POST /api/fleet/voice/{device_id}/alert — send alert to device
  POST /api/fleet/voice/{device_id}/mcp  — send MCP command
  POST /api/fleet/voice/{device_id}/system — send system command
  POST /api/fleet/voice/{device_id}/llm  — process text through LLM
"""

from __future__ import annotations

import threading
from typing import Any, Dict, Optional

import requests as _requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.services.xiaozhi_server import (
    get_xiaozhi_server,
    get_device_session,
    list_sessions,
    close_session,
    VoiceSession,
)

router = APIRouter(prefix="/api/fleet/voice", tags=["Fleet Voice"])

# ═══════════════════════════════════════════════════════════
# Nirvana LLM Client (DeepSeek or local)
# ═══════════════════════════════════════════════════════════

class NirvanaLLM:
    """Simple LLM client for voice pipeline — wraps the Nirvana chat API."""

    def __init__(self):
        self.api_base = "http://127.0.0.1:8010"
        self.model = "deepseek-v4-flash"

    def chat(self, text: str, device_id: str = "") -> str:
        """Send one message to the LLM and get the response."""
        try:
            url = f"{self.api_base}/v1/chat/completions"
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are Nirvana, the NPU-STACK fleet AI. You speak through a voice assistant device. Keep responses brief, conversational, and under 2 sentences. You can control IoT devices via MCP."},
                    {"role": "user", "content": text},
                ],
                "max_tokens": 150,
                "temperature": 0.7,
            }
            resp = _requests.post(url, json=payload, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"[NirvanaLLM] Error: {e}")
            return f"I had trouble understanding that. ({str(e)[:50]})"


_nirvana_llm = NirvanaLLM()


def _llm_callback(text: str, device_id: str) -> str:
    """Callback for xiaozhi_server — returns LLM response for user text."""
    return _nirvana_llm.chat(text, device_id)


# ═══════════════════════════════════════════════════════════
# Pydantic Models
# ═══════════════════════════════════════════════════════════

class TTSRequest(BaseModel):
    text: str
    emotion: str = "neutral"

class AlertRequest(BaseModel):
    status: str = "Info"
    message: str
    emotion: str = "neutral"

class MCPRequest(BaseModel):
    payload: Dict[str, Any]

class SystemRequest(BaseModel):
    command: str  # reboot, shutdown, update, etc.

class LLMRequest(BaseModel):
    text: str


# ═══════════════════════════════════════════════════════════
# REST Endpoints
# ═══════════════════════════════════════════════════════════

@router.get("/sessions")
async def voice_sessions():
    """List all active voice sessions."""
    return {
        "sessions": list_sessions(),
        "count": len(list_sessions()),
    }

@router.get("/sessions/{device_id}")
async def voice_session_status(device_id: str):
    """Get session status for a specific device."""
    session = get_device_session(device_id)
    if not session:
        raise HTTPException(404, f"No active session for device '{device_id}'")
    return {
        "device_id": session.device_id,
        "session_id": session.session_id,
        "listening": session.listening,
        "speaking": session.speaking,
        "emotion": session.emotion,
        "features": session.features,
        "created_at": session.created_at,
        "last_activity": session.last_activity,
    }

@router.post("/{device_id}/tts")
async def send_tts(device_id: str, req: TTSRequest):
    """Send text-to-speech to a device."""
    server = get_xiaozhi_server()
    if not server:
        raise HTTPException(503, "XiaoZhi voice server not running")

    ok = server.send_tts(device_id, req.text)
    if not ok:
        raise HTTPException(404, f"No active session for device '{device_id}'")
    return {"device_id": device_id, "tts_sent": True, "text": req.text[:100]}

@router.post("/{device_id}/alert")
async def send_alert(device_id: str, req: AlertRequest):
    """Send an alert/notification to a device."""
    server = get_xiaozhi_server()
    if not server:
        raise HTTPException(503, "XiaoZhi voice server not running")

    ok = server.send_alert(device_id, req.status, req.message, req.emotion)
    if not ok:
        raise HTTPException(404, f"No active session for device '{device_id}'")
    return {"device_id": device_id, "alert_sent": True, "status": req.status}

@router.post("/{device_id}/mcp")
async def send_mcp(device_id: str, req: MCPRequest):
    """Send MCP device control command."""
    server = get_xiaozhi_server()
    if not server:
        raise HTTPException(503, "XiaoZhi voice server not running")

    ok = server.send_mcp(device_id, req.payload)
    if not ok:
        raise HTTPException(404, f"No active session for device '{device_id}'")
    return {"device_id": device_id, "mcp_sent": True}

@router.post("/{device_id}/system")
async def send_system(device_id: str, req: SystemRequest):
    """Send system command (reboot, etc.) to device."""
    server = get_xiaozhi_server()
    if not server:
        raise HTTPException(503, "XiaoZhi voice server not running")

    ok = server.send_system(device_id, req.command)
    if not ok:
        raise HTTPException(404, f"No active session for device '{device_id}'")
    return {"device_id": device_id, "command_sent": True, "command": req.command}

@router.post("/{device_id}/llm")
async def send_llm(device_id: str, req: LLMRequest):
    """Process text through Nirvana LLM and respond via TTS to device."""
    server = get_xiaozhi_server()
    if not server:
        raise HTTPException(503, "XiaoZhi voice server not running")

    session = get_device_session(device_id)
    if not session:
        raise HTTPException(404, f"No active session for device '{device_id}'")

    # Run LLM in thread to not block
    response_text = _nirvana_llm.chat(req.text, device_id)

    # Send LLM emotion + TTS
    import json
    topic = session.device_topic
    server._client.publish(topic, json.dumps({
        "session_id": session.session_id,
        "type": "llm",
        "emotion": "happy",
        "text": response_text,
    }))

    ok = server.send_tts(device_id, response_text)
    return {
        "device_id": device_id,
        "user_text": req.text[:200],
        "nirvana_response": response_text[:500],
        "tts_sent": ok,
    }
