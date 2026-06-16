"""ESP Development Router — unified ESP-IDF + ESP-NOW environment.

Endpoints:
  GET  /api/esp/serial-ports       — list COM ports with ESP detection
  GET  /api/esp/serial-ports/{dev} — port details
  WS   /api/esp/terminal/{dev}     — WebSocket serial terminal
  GET  /api/esp/idf/status         — ESP-IDF toolchain status
  GET  /api/esp/idf/projects       — list IDF projects
  POST /api/esp/idf/projects       — scaffold new IDF project
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Query

from services.esp_terminal_service import (
    HAS_PYSERIAL,
    close_connection,
    get_or_create_connection,
    list_serial_ports,
)
from services.espnow_service import (
    build_command,
    espnow_available,
    get_example_detail,
    get_firmware_binaries,
    idf_available,
    list_examples,
    list_modules,
)

logger = logging.getLogger("esp_router")

router = APIRouter(prefix="/api/esp", tags=["esp"])

REPO_ROOT = Path(__file__).resolve().parents[2]
IDF_PROJECTS_DIR = REPO_ROOT / "firmware" / "esp-idf-projects"

# ── Serial Ports ──────────────────────────────────────────────────────────

@router.get("/serial-ports")
def get_serial_ports():
    """List all serial ports with ESP device auto-detection."""
    return list_serial_ports()


@router.get("/serial-ports/{device:path}")
def get_port_detail(device: str):
    """Get details for a specific serial port."""
    from services.esp_terminal_service import get_port_info

    info = get_port_info(device)
    if info is None:
        raise HTTPException(404, f"Port {device} not found")
    return info


# ── WebSocket Serial Terminal ─────────────────────────────────────────────

@router.websocket("/terminal/{device:path}")
async def ws_serial_terminal(websocket: WebSocket, device: str, baud: int = Query(115200)):
    """WebSocket-based serial terminal for an ESP device."""
    if not HAS_PYSERIAL:
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": "pyserial not installed. Run: pip install pyserial"})
        await websocket.close()
        return

    await websocket.accept()
    logger.info(f"ESP terminal WS connected: {device} @ {baud}")

    conn = get_or_create_connection(device, baud)
    if not conn.is_open:
        await websocket.send_json({"type": "error", "message": f"Could not open {device}"})
        await websocket.close()
        return

    # Queue for forwarding serial data to WS
    rx_queue: asyncio.Queue = asyncio.Queue()

    async def on_serial_data(data: bytes):
        await rx_queue.put(data)

    conn.set_on_data(lambda data: asyncio.ensure_future(on_serial_data(data)))

    # Send connected confirmation
    await websocket.send_json({
        "type": "connected",
        "device": device,
        "baud": baud,
        "message": f"Connected to {device} at {baud} baud",
    })

    async def ws_to_serial():
        """Forward WebSocket text → serial port."""
        try:
            while True:
                msg = await websocket.receive_text()
                payload = json.loads(msg)
                text = payload.get("text", "")
                if text:
                    # Append newline if terminal-style input
                    data = text.encode("utf-8", errors="replace")
                    if not text.endswith("\n") and not text.endswith("\r"):
                        data += b"\r\n"
                    conn.write(data)
                if payload.get("action") == "close":
                    break
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.error(f"WS→serial error: {e}")

    async def serial_to_ws():
        """Forward serial data → WebSocket."""
        try:
            while True:
                data = await rx_queue.get()
                try:
                    text = data.decode("utf-8", errors="replace")
                except Exception:
                    text = data.hex()
                await websocket.send_json({"type": "data", "text": text})
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.error(f"Serial→WS error: {e}")

    # Run both directions concurrently
    try:
        await asyncio.gather(ws_to_serial(), serial_to_ws())
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"ESP terminal error: {e}")
    finally:
        close_connection(device)
        logger.info(f"ESP terminal WS disconnected: {device}")


# ── ESP-IDF Toolchain ─────────────────────────────────────────────────────

@router.get("/idf/status")
def get_idf_status():
    """ESP-IDF toolchain availability and version."""
    import os as _os

    idf_path = _os.getenv("IDF_PATH", "")
    idf_py = _os.getenv("IDF_PYTHON", "python")

    status = {
        "idf_available": idf_available(),
        "idf_path": idf_path or "not set",
        "idf_python": idf_py,
        "espnow_available": espnow_available(),
        "pyserial_available": HAS_PYSERIAL,
        "projects_dir": str(IDF_PROJECTS_DIR),
    }

    # Try to get IDF version
    if idf_available() and idf_path:
        import subprocess
        try:
            result = subprocess.run(
                [idf_py, str(Path(idf_path) / "tools" / "idf.py"), "--version"],
                capture_output=True, text=True, timeout=10,
                cwd=idf_path,
            )
            if result.returncode == 0:
                status["idf_version"] = result.stdout.strip()
        except Exception:
            pass

    return status


@router.get("/idf/projects")
def list_idf_projects():
    """List existing ESP-IDF projects in firmware/esp-idf-projects/."""
    if not IDF_PROJECTS_DIR.exists():
        return {"projects": [], "count": 0, "path": str(IDF_PROJECTS_DIR)}

    projects = []
    for d in sorted(IDF_PROJECTS_DIR.iterdir()):
        if d.is_dir() and not d.name.startswith("."):
            cmake = (d / "CMakeLists.txt").exists()
            main_c = (d / "main" / "main.c").exists() or any(
                f.suffix in (".c", ".cpp") for f in (d / "main").iterdir()
            ) if (d / "main").is_dir() else False
            sdkconfig = (d / "sdkconfig").exists()
            projects.append({
                "name": d.name,
                "has_cmake": cmake,
                "has_main": main_c,
                "has_sdkconfig": sdkconfig,
                "path": str(d.relative_to(REPO_ROOT)),
            })

    return {"projects": projects, "count": len(projects), "path": str(IDF_PROJECTS_DIR)}


@router.post("/idf/projects")
def create_idf_project(name: str, template: str = "blank"):
    """Scaffold a new ESP-IDF project from a template.

    Templates: blank, blink, wifi-station, espnow-node
    """
    IDF_PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    project_dir = IDF_PROJECTS_DIR / name

    if project_dir.exists():
        raise HTTPException(409, f"Project '{name}' already exists")

    project_dir.mkdir(parents=True)
    (project_dir / "main").mkdir()

    templates = {
        "blank": {
            "CMakeLists.txt": 'cmake_minimum_required(VERSION 3.16)\ninclude($ENV{IDF_PATH}/tools/cmake/project.cmake)\nproject({name})\n',
            "main/CMakeLists.txt": "idf_component_register(SRCS \"main.c\"\n                    INCLUDE_DIRS \".\")\n",
            "main/main.c": '#include <stdio.h>\n#include "freertos/FreeRTOS.h"\n#include "freertos/task.h"\n\nvoid app_main(void) {\n    printf("Hello from NPU-STACK ESP-IDF project: {name}\\n");\n    while (1) { vTaskDelay(pdMS_TO_TICKS(1000)); }\n}\n',
        },
        "blink": {
            "CMakeLists.txt": 'cmake_minimum_required(VERSION 3.16)\ninclude($ENV{IDF_PATH}/tools/cmake/project.cmake)\nproject({name})\n',
            "main/CMakeLists.txt": "idf_component_register(SRCS \"main.c\"\n                    INCLUDE_DIRS \".\")\n",
            "main/main.c": '#include <stdio.h>\n#include "freertos/FreeRTOS.h"\n#include "freertos/task.h"\n#include "driver/gpio.h"\n\n#define LED_GPIO 2\n\nvoid app_main(void) {\n    gpio_reset_pin(LED_GPIO);\n    gpio_set_direction(LED_GPIO, GPIO_MODE_OUTPUT);\n    printf("NPU-STACK Blink: {name}\\n");\n    while (1) {\n        gpio_set_level(LED_GPIO, 1);\n        vTaskDelay(pdMS_TO_TICKS(500));\n        gpio_set_level(LED_GPIO, 0);\n        vTaskDelay(pdMS_TO_TICKS(500));\n    }\n}\n',
        },
    }

    tmpl = templates.get(template, templates["blank"])
    for filepath, content in tmpl.items():
        target = project_dir / filepath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content.replace("{name}", name), encoding="utf-8")

    # Generate sdkconfig.defaults
    (project_dir / "sdkconfig.defaults").write_text(
        "CONFIG_FREERTOS_HZ=1000\nCONFIG_ESPTOOLPY_BAUD_OTHER=921600\n",
        encoding="utf-8",
    )

    return {
        "created": True,
        "project": name,
        "template": template,
        "path": str(project_dir.relative_to(REPO_ROOT)),
        "files": list(tmpl.keys()) + ["sdkconfig.defaults"],
    }


# ── ESP-NOW sub-router (backward-compatible under /api/esp/espnow) ────────

@router.get("/espnow/status")
def esp_status():
    """ESP-NOW library status."""
    return {
        "library_available": espnow_available(),
        "idf_available": idf_available(),
        "library_path": "libraries/esp-now-lib/",
    }


@router.get("/espnow/modules")
def esp_modules():
    """ESP-NOW source modules."""
    if not espnow_available():
        raise HTTPException(404, "ESP-NOW library not found")
    return list_modules()


@router.get("/espnow/examples")
def esp_examples():
    """ESP-NOW example projects."""
    if not espnow_available():
        raise HTTPException(404, "ESP-NOW library not found")
    return list_examples()


@router.get("/espnow/examples/{name}")
def esp_example(name: str):
    """ESP-NOW example detail."""
    detail = get_example_detail(name)
    if detail is None:
        raise HTTPException(404, f"Example not found: {name}")
    return detail


@router.get("/espnow/examples/{name}/build")
def esp_build_info(name: str, target: str = "esp32", port: str = ""):
    """Build commands for an ESP-NOW example."""
    result = build_command(name, target=target, port=port)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


@router.get("/espnow/examples/{name}/binaries")
def esp_binaries(name: str):
    """Built firmware binaries for an example."""
    return get_firmware_binaries(name)
