"""Nirvana OS MicroPython emulator — WebSocket + example listing.

The browser playground streams a virtual 240x240 RGB565 framebuffer and sends
touch points back; the app code runs on the host through the MicroPython shim
in ``backend/emulator``. No device needed — same code, same pixels.
"""
import asyncio
import json
import os
import shutil
import tempfile
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/emulator", tags=["emulator"])

MARKETPLACE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "marketplace")
BACKEND_DIR = os.path.dirname(os.path.dirname(__file__))
SD_ROOT = os.environ.get("NIRVANA_EMULATOR_SD") or os.path.join(BACKEND_DIR, "data", "emulator_sd")
VENV_PY = None


def _sd_path(path: str) -> str:
    """Resolve a /sd-relative path safely inside SD_ROOT."""
    rel = path.replace("\\", "/").strip("/")
    full = os.path.realpath(os.path.join(SD_ROOT, rel))
    if full != os.path.realpath(SD_ROOT) and not full.startswith(os.path.realpath(SD_ROOT) + os.sep):
        raise ValueError("path escapes SD root")
    return full


def _sd_tree(root: str):
    """Recursive tree of the virtual SD card for the playground UI."""
    entries = []
    try:
        names = sorted(os.listdir(root))
    except Exception:
        return entries
    for name in names:
        full = os.path.join(root, name)
        rel = os.path.relpath(full, SD_ROOT).replace(os.sep, "/")
        if os.path.isdir(full):
            entries.append({"name": name, "path": "/" + rel, "type": "dir",
                            "children": _sd_tree(full)})
        else:
            entries.append({"name": name, "path": "/" + rel, "type": "file",
                            "size": os.path.getsize(full)})
    return entries


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


@router.get("/sd")
def sd_tree():
    """List the virtual SD card contents (what /sd looks like to apps)."""
    os.makedirs(SD_ROOT, exist_ok=True)
    return {"root": SD_ROOT, "tree": _sd_tree(SD_ROOT)}


@router.get("/sd/file")
def sd_read(path: str):
    """Read a single file from the virtual SD card (for the playground editor)."""
    try:
        full = _sd_path(path)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    if not os.path.isfile(full):
        return JSONResponse({"error": "not a file"}, status_code=404)
    try:
        with open(full, "r", encoding="utf-8") as f:
            return {"path": path, "content": f.read()}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/sensors")
def sensor_schema():
    """Sensor schema + current values for the playground's sensor panel."""
    from backend.emulator import shim
    return {"sensors": shim.get_sensor_schema(), "values": shim.get_sensors()}


@router.post("/sd")
def sd_write(payload: dict):
    """Mutate the virtual SD card: {action, path, content?}."""
    action = payload.get("action", "")
    path = payload.get("path", "")
    if not path:
        return JSONResponse({"error": "path required"}, status_code=400)
    try:
        full = _sd_path(path)
        if action == "write":
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8") as f:
                f.write(payload.get("content", ""))
        elif action == "mkdir":
            os.makedirs(full, exist_ok=True)
        elif action == "delete":
            if os.path.isdir(full):
                shutil.rmtree(full)
            else:
                os.remove(full)
        else:
            return JSONResponse({"error": "unknown action"}, status_code=400)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    return {"ok": True, "tree": _sd_tree(SD_ROOT)}


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
            env={**os.environ, "NIRVANA_EMULATOR_SD": SD_ROOT},
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
            elif mtype == "sensor":
                if proc and proc.stdin and proc.returncode is None:
                    try:
                        proc.stdin.write(("SENSOR:%s\n" % json.dumps(msg.get("values", {}))).encode())
                        await proc.stdin.drain()
                    except Exception:
                        pass
            elif mtype == "stop":
                await _stop()
    except WebSocketDisconnect:
        pass
    finally:
        await _stop()
