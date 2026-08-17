"""
XiaoZhi WebSocket Transport — server side of xiaozhi-esp32's WebSocket protocol.

Endpoint: ws://host:8010/api/fleet/voice/ws

  - Text frames:   JSON control messages (hello / listen / abort / mcp / goodbye)
  - Binary frames: Opus audio (v1 raw, v2/v3 framed — see websocket.md)

Handshake headers (lowercased by Starlette):
  authorization:    "Bearer <token>"
  protocol-version: binary protocol version (1|2|3)
  device-id:        physical MAC
  client-id:        software UUID

Refs:
  https://github.com/78/xiaozhi-esp32/blob/main/docs/websocket.md

Phase 1 scope:
  - Full JSON control plane (hello handshake, listen states, abort, mcp, goodbye)
  - STT → LLM (Nirvana) → TTS text pipeline (no Opus encode yet — text TTS only)
  - Binary Opus framing parsed (v1/v2/v3) and acknowledged; audio is logged,
    not yet consumed by STT (same gap as the MQTT transport)
"""
from __future__ import annotations

import asyncio
import json
import struct
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.services.xiaozhi_server import (
    VoiceSession,
    close_session,
    create_session,
    get_device_session,
)

# LLM callback — single entry point shared with the MQTT transport
try:
    from routers.xiaozhi_router import _llm_callback  # type: ignore
except Exception:  # pragma: no cover - fallback if router import path differs
    _llm_callback = None

router = APIRouter(prefix="/api/fleet/voice", tags=["Fleet Voice"])

# Active WebSocket connections, keyed by device_id
active_ws_connections: Dict[str, WebSocket] = {}


# ═══════════════════════════════════════════════════════════
# Binary Opus framing (v1 / v2 / v3)
# ═══════════════════════════════════════════════════════════

def _parse_opus_frame(data: bytes, version: int) -> Optional[bytes]:
    """Extract the Opus payload bytes from a xiaozhi binary frame."""
    if version == 3:
        # BinaryProtocol3: type(u8) reserved(u8) payload_size(u16 LE) payload
        if len(data) < 4:
            return None
        _type, _reserved, payload_size = struct.unpack("<BBH", data[:4])
        payload = data[4:]
        return payload[:payload_size] if len(payload) >= payload_size else None
    if version == 2:
        # BinaryProtocol2: version(u16) type(u16) reserved(u32)
        #                 timestamp(u32) payload_size(u32 LE) payload
        if len(data) < 16:
            return None
        _ver, _type, _reserved, _timestamp, payload_size = struct.unpack(
            "<HHIII", data[:16]
        )
        payload = data[16:]
        return payload[:payload_size] if len(payload) >= payload_size else None
    # v1: raw Opus
    return data


def _parse_binary(data: bytes, version: int) -> Dict[str, Any]:
    """Parse a binary frame for logging/acknowledgement."""
    opus = _parse_opus_frame(data, version)
    if opus is None:
        return {"ok": False, "version": version, "frame_bytes": len(data)}
    return {
        "ok": True,
        "version": version,
        "frame_bytes": len(data),
        "opus_bytes": len(opus),
    }


# ═══════════════════════════════════════════════════════════
# JSON message handlers
# ═══════════════════════════════════════════════════════════

async def _send_json(ws: WebSocket, payload: Dict[str, Any]) -> None:
    """Send a JSON text frame to the device."""
    await ws.send_text(json.dumps(payload, ensure_ascii=False))


async def _process_llm(ws: WebSocket, session: VoiceSession, text: str) -> None:
    """Run user text through the Nirvana LLM and emit STT/LLM/TTS events."""
    print(f"[XiaoZhi-WS] LLM processing: '{text[:80]}...' from {session.device_id}")

    await _send_json(ws, {
        "session_id": session.session_id,
        "type": "llm",
        "emotion": "thinking",
    })

    try:
        if _llm_callback:
            response_text = await asyncio.to_thread(_llm_callback, text, session.device_id)
        else:
            response_text = f"Nirvana heard: {text}"

        emotion = "happy"
        if "?" in text:
            emotion = "curious"
        elif "!" in text:
            emotion = "excited"

        await _send_json(ws, {
            "session_id": session.session_id,
            "type": "llm",
            "emotion": emotion,
            "text": response_text,
        })
        await _send_json(ws, {
            "session_id": session.session_id,
            "type": "tts",
            "state": "start",
        })
        await _send_json(ws, {
            "session_id": session.session_id,
            "type": "tts",
            "state": "sentence_start",
            "text": response_text,
        })
        await _send_json(ws, {
            "session_id": session.session_id,
            "type": "tts",
            "state": "stop",
        })

        session.speaking = False
        session.emotion = emotion

    except Exception as e:
        print(f"[XiaoZhi-WS] LLM error: {e}")
        await _send_json(ws, {
            "session_id": session.session_id,
            "type": "alert",
            "status": "Error",
            "message": f"LLM processing failed: {e}",
            "emotion": "sad",
        })


async def _handle_json(ws: WebSocket, raw: str, device_id: str) -> None:
    """Dispatch a JSON text frame by its 'type' field."""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return

    msg_type = payload.get("type", "")
    if not msg_type:
        return

    session = get_device_session(device_id)

    if msg_type == "hello":
        session = create_session(device_id, f"ws://{device_id}")
        session.features = payload.get("features", {})
        ap = payload.get("audio_params", {})
        session.audio_format = ap.get("format", "opus")
        session.audio_sample_rate = ap.get("sample_rate", 16000)
        session.audio_channels = ap.get("channels", 1)
        session.audio_frame_ms = ap.get("frame_duration", 60)

        await _send_json(ws, {
            "type": "hello",
            "transport": "websocket",
            "session_id": session.session_id,
            "audio_params": {
                "format": "opus",
                "sample_rate": 24000,
                "channels": 1,
                "frame_duration": 60,
            },
        })
        print(f"[XiaoZhi-WS] HELLO → {device_id} (session {session.session_id})")

    elif msg_type == "listen":
        state = payload.get("state", "")
        if state == "start":
            if session:
                session.listening = True
                session.last_activity = time.time()
            print(f"[XiaoZhi-WS] LISTEN START — {device_id}")
            if session:
                await _send_json(ws, {
                    "session_id": session.session_id,
                    "type": "tts",
                    "state": "start",
                })
        elif state == "stop":
            if session:
                session.listening = False
            print(f"[XiaoZhi-WS] LISTEN STOP — {device_id}")
        elif state == "detect":
            text = payload.get("text", "")
            print(f"[XiaoZhi-WS] LISTEN DETECT: '{text}' from {device_id}")
            if session and text.strip():
                await _process_llm(ws, session, text)

    elif msg_type == "abort":
        if session:
            session.listening = False
            session.speaking = False
            print(f"[XiaoZhi-WS] ABORT — {device_id}")

    elif msg_type == "mcp":
        print(f"[XiaoZhi-WS] MCP from {device_id}: {payload.get('payload')}")

    elif msg_type == "goodbye":
        if session:
            print(f"[XiaoZhi-WS] GOODBYE — {device_id}")
            close_session(session.session_id)

    else:
        print(f"[XiaoZhi-WS] Unknown type '{msg_type}' from {device_id}")


# ═══════════════════════════════════════════════════════════
# WebSocket endpoint
# ═══════════════════════════════════════════════════════════

@router.websocket("/ws")
async def xiaozhi_websocket_endpoint(ws: WebSocket) -> None:
    """Accept a xiaozhi device and service its voice session over WebSocket."""
    # Handshake headers (Starlette lowercases them)
    auth = ws.headers.get("authorization", "")
    protocol_version = int(ws.headers.get("protocol-version", "1") or "1")
    device_mac = ws.headers.get("device-id", "")
    client_uuid = ws.headers.get("client-id", "")

    device_id = device_mac or client_uuid or f"ws-{int(time.time() * 1000) % 100000}"

    await ws.accept()
    active_ws_connections[device_id] = ws
    print(
        f"[XiaoZhi-WS] Connected: device={device_id} "
        f"ver={protocol_version} auth={'set' if auth else 'none'}"
    )

    try:
        while True:
            message = await ws.receive()

            if message["type"] == "websocket.disconnect":
                break
            if message.get("text") is not None:
                await _handle_json(ws, message["text"], device_id)
            elif message.get("bytes") is not None:
                info = _parse_binary(message["bytes"], protocol_version)
                if not info["ok"]:
                    print(f"[XiaoZhi-WS] Bad binary frame ({info['frame_bytes']}B) from {device_id}")
                # Opus audio acknowledged — STT consumption is a later phase
                # (mirrors the MQTT transport's current audio gap).

    except WebSocketDisconnect:
        pass
    finally:
        active_ws_connections.pop(device_id, None)
        session = get_device_session(device_id)
        if session:
            close_session(session.session_id)
        print(f"[XiaoZhi-WS] Disconnected: {device_id}")


# ═══════════════════════════════════════════════════════════
# Public helpers (for future REST → WebSocket device push)
# ═══════════════════════════════════════════════════════════

def send_json_to_device(device_id: str, payload: Dict[str, Any]) -> bool:
    """Return True if a WebSocket connection exists for the device.

    Actual send is async — use from an async context via `active_ws_connections`.
    """
    return device_id in active_ws_connections
