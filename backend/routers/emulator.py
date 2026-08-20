"""Nirvana OS MicroPython emulator — WebSocket + example listing.

The browser playground streams a virtual 240x240 RGB565 framebuffer and sends
touch points back; the app code runs on the host through the MicroPython shim
in ``backend/emulator``. No device needed — same code, same pixels.
"""
import asyncio
import json
import os
import tempfile
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/emulator", tags=["emulator"])

MARKETPLACE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "marketplace")
VENV_PY = None


def _python():
    global VENV_PY
    if VENV_PY:
        return VENV_PY
    backend_dir = os.path.dirname(os.path.dirname(__file__))
    candidate = os.path.join(os.path.dirname(backend_dir), ".venv", "Scripts", "python.exe")
    if not os.path.exists(candidate):
        candidate = "python"
    VENV_PY = candidate
    return VENV_PY


@router.get("/examples")
def examples():
    """List marketplace apps with their source, ready to run in the playground."""
    catalog_path = os.path.join(MARKETPLACE_DIR, "catalog.json")
    apps = []
    try:
        with open(catalog_path, encoding="utf-8") as f:
            catalog = json.load(f).get("apps", [])
    except Exception:
        catalog = []

    for app in catalog:
        main_path = os.path.join(MARKETPLACE_DIR, "apps", app["id"], "main.py")
        try:
            with open(main_path, encoding="utf-8") as f:
                code = f.read()
        except Exception:
            code = ""
        apps.append({
            "id": app["id"],
            "name": app.get("name", app["id"]),
            "description": app.get("description", ""),
            "code": code,
        })
    return {"apps": apps}


@router.websocket("/ws")
async def emulator_ws(ws: WebSocket):
    await ws.accept()
    proc: Optional[asyncio.subprocess.Process] = None
    tmp: Optional[str] = None

    async def spawn(code: str):
        nonlocal proc, tmp
        await _stop()
        fd, tmp = tempfile.mkstemp(suffix=".py", prefix="nirvana_app_")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(code)
        proc = await asyncio.create_subprocess_exec(
            _python(),
            "-m", "backend.emulator.runner", tmp,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        asyncio.create_task(_pump(proc, ws))

    async def _pump(p, wsock):
        try:
            while True:
                line = await p.stdout.readline()
                if not line:
                    break
                text = line.decode("utf-8", "replace").rstrip("\n")
                if text.startswith("FRAME:"):
                    try:
                        length = int(text[6:])
                    except Exception:
                        continue
                    try:
                        data = await p.stdout.readexactly(length)
                    except Exception:
                        break
                    try:
                        await wsock.send_bytes(data)
                    except Exception:
                        pass
                elif text.startswith("LOG:"):
                    try:
                        await wsock.send_text(json.dumps({"type": "log", "text": text[4:]}))
                    except Exception:
                        pass
        except Exception:
            pass

    async def _stop():
        nonlocal proc, tmp
        if proc and proc.returncode is None:
            try:
                if proc.stdin:
                    proc.stdin.write(b"STOP\n")
                    await proc.stdin.drain()
            except Exception:
                pass
            try:
                proc.terminate()
            except Exception:
                pass
            try:
                await asyncio.wait_for(proc.wait(), timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        proc = None
        if tmp and os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass
        tmp = None

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            mtype = msg.get("type")
            if mtype == "run":
                await spawn(msg.get("code", ""))
            elif mtype == "touch":
                if proc and proc.stdin and proc.returncode is None:
                    try:
                        proc.stdin.write(("TOUCH:%s,%s\n" % (msg.get("x", 0), msg.get("y", 0))).encode())
                        await proc.stdin.drain()
                    except Exception:
                        pass
            elif mtype == "stop":
                await _stop()
    except WebSocketDisconnect:
        pass
    finally:
        await _stop()
