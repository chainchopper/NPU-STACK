"""
Nirvana Stream — WebSocket audio endpoint for real-time voice streaming
Pairs with nirvana_stream.h on AMB82 agent.

ws://host:8010/api/nirvana/stream
  - Client sends: int16_t PCM binary frames (16kHz mono mic)
  - Server sends: int16_t PCM binary frames (TTS response)
  - RMS amplitude computed server-side, returned for orb visualization
"""
from __future__ import annotations

import math
import struct
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(prefix="/api/nirvana", tags=["nirvana-stream"])

# Connected clients
active_streams: dict[str, WebSocket] = {}


def _compute_rms(samples: list[int]) -> float:
    """Compute RMS amplitude from PCM samples (0.0 - 1.0)."""
    if not samples:
        return 0.0
    squared = sum(s * s for s in samples)
    return math.sqrt(squared / len(samples)) / 32768.0


def _generate_sine(freq: float = 440.0, duration_ms: int = 100,
                   sample_rate: int = 16000) -> bytes:
    """Generate a sine wave PCM buffer as test TTS response."""
    count = int(sample_rate * duration_ms / 1000)
    buf = bytearray()
    for i in range(count):
        val = int(16000 * math.sin(2 * math.pi * freq * (i / sample_rate)))
        buf.extend(struct.pack("<h", max(-32768, min(32767, val))))
    return bytes(buf)


@router.websocket("/stream")
async def nirvana_stream_endpoint(ws: WebSocket):
    """Bi-directional audio WebSocket — mic in, TTS out."""
    await ws.accept()
    client_id = f"amb82-{int(time.time() * 1000) % 100000}"
    active_streams[client_id] = ws
    print(f"[WS-STREAM] Client connected: {client_id}")

    try:
        while True:
            # Receive binary PCM from device mic
            data = await ws.receive_bytes()
            if not data:
                continue

            # Parse 16-bit PCM samples
            sample_count = len(data) // 2
            samples = struct.unpack(f"<{sample_count}h", data)

            # Compute RMS for real-time visualization
            rms = _compute_rms(list(samples))

            # ── TODO: Pipe audio to STT/LLM/TTS pipeline ──
            # 1. Send PCM to Whisper STT → text
            # 2. Text → LLM → response text
            # 3. Response text → TTS engine → PCM
            # For now: generate test sine wave response

            # Send TTS response (sine wave test tone)
            tts_audio = _generate_sine(523.0, 80, 16000)  # C5 note, 80ms
            await ws.send_bytes(tts_audio)

            # Print stats occasionally
            if rms > 0.02:
                print(f"[WS-STREAM] {client_id}: {sample_count} samples, RMS={rms:.3f}")

    except WebSocketDisconnect:
        print(f"[WS-STREAM] Client disconnected: {client_id}")
    except Exception as e:
        print(f"[WS-STREAM] Error: {e}")
    finally:
        active_streams.pop(client_id, None)


@router.get("/stream/status")
async def stream_status():
    """Get WebSocket stream status."""
    return {
        "active_connections": len(active_streams),
        "clients": list(active_streams.keys()),
    }
