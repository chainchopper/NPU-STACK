"""
XiaoZhi WebSocket protocol probe — simulates a xiaozhi device against our server.

Runs the xiaozhi_websocket router standalone on 127.0.0.1:8099 and drives a real
WebSocket client through the full protocol:
    hello → listen start → Opus binary (v3) → listen detect (LLM) → goodbye

This verifies the server side of the xiaozhi wire protocol end-to-end without
needing physical hardware. For real-device verification, flash a stock xiaozhi
board and point its WebSocket URL at the NPU-STACK endpoint.

Usage: python scripts/xiaozhi_ws_probe.py
"""
from __future__ import annotations

import asyncio
import json
import struct
import sys
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "backend"))

import uvicorn
from fastapi import FastAPI

from backend.routers.xiaozhi_websocket import router as xz_router

HOST = "127.0.0.1"
PORT = 8099
PATH = "/api/fleet/voice/ws"


_server: "uvicorn.Server | None" = None


def _start_server() -> None:
    global _server
    app = FastAPI()
    app.include_router(xz_router)
    config = uvicorn.Config(app, host=HOST, port=PORT, log_level="warning")
    _server = uvicorn.Server(config)
    _server.run()


def _opus_v3(payload: bytes) -> bytes:
    """Wrap Opus payload in a BinaryProtocol3 frame."""
    return struct.pack("<BBH", 1, 0, len(payload)) + payload


async def _probe() -> None:
    from websockets.asyncio.client import connect

    headers = {
        "Authorization": "Bearer probe-token",
        "Protocol-Version": "3",
        "Device-Id": "probe-device-001",
        "Client-Id": "probe-client-001",
    }
    uri = f"ws://{HOST}:{PORT}{PATH}"

    async with connect(uri, additional_headers=headers) as ws:
        # 1. hello handshake
        await ws.send(json.dumps({
            "type": "hello",
            "version": 3,
            "features": {"mcp": True},
            "transport": "websocket",
            "audio_params": {"format": "opus", "sample_rate": 16000,
                              "channels": 1, "frame_duration": 60},
        }))
        hello = json.loads(await ws.recv())
        assert hello["type"] == "hello" and hello["transport"] == "websocket", hello
        session_id = hello.get("session_id", "")
        assert session_id, "no session_id in hello reply"
        print(f"  [1] hello        -> session={session_id[:8]}...  transport=websocket")

        # 2. listen start → expect tts start ack
        await ws.send(json.dumps({
            "session_id": session_id, "type": "listen",
            "state": "start", "mode": "manual",
        }))
        ack = json.loads(await ws.recv())
        assert ack["type"] == "tts" and ack["state"] == "start", ack
        print("  [2] listen start -> tts start ack")

        # 3. upstream Opus audio (BinaryProtocol3)
        await ws.send(_opus_v3(b"\x00" * 64))
        print("  [3] sent Opus v3 frame (64 B payload)")

        # 4. wake-word detect → triggers STT→LLM→TTS pipeline
        await ws.send(json.dumps({
            "session_id": session_id, "type": "listen",
            "state": "detect", "text": "Hello Nirvana!",
        }))
        msg = json.loads(await ws.recv())
        print(f"  [4] listen detect -> {msg.get('type')} / {msg.get('emotion', '')}")

        # 5. goodbye
        await ws.send(json.dumps({"session_id": session_id, "type": "goodbye"}))
        print("  [5] goodbye      -> sent")

    print("PROBE OK — full xiaozhi WebSocket flow passed")


def main() -> None:
    print(f"Starting xiaozhi WebSocket router on {HOST}:{PORT} ...")
    thread = threading.Thread(target=_start_server, daemon=True)
    thread.start()
    time.sleep(2)
    try:
        asyncio.run(_probe())
    finally:
        if _server is not None:
            _server.should_exit = True
        thread.join(timeout=3)


if __name__ == "__main__":
    main()
