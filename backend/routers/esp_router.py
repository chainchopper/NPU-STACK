"""ESP Development Router — unified ESP-IDF + ESP-NOW environment.

Endpoints:
  GET  /api/esp/serial-ports       — list COM ports with ESP detection
  GET  /api/esp/serial-ports/{dev} — port details
  WS   /api/esp/terminal/{dev}     — WebSocket serial terminal
  GET  /api/esp/idf/status         — ESP-IDF toolchain status (full detection)
  GET  /api/esp/idf/projects       — list IDF projects
  POST /api/esp/idf/projects       — scaffold new IDF project
  POST /api/esp/idf/build          — idf.py build
  POST /api/esp/idf/flash          — idf.py flash
  GET  /api/esp/idf/monitor        — idf.py monitor command
  GET  /api/esp/flash/detect/{dev} — esptool chip-id
  POST /api/esp/flash/backup/{dev} — esptool read_flash
  POST /api/esp/flash/write/{dev}  — esptool write_flash
  POST /api/esp/flash/micropython/{dev} — mpremote/ampy file push
  GET  /api/esp/flash/backups      — list backups
  DELETE /api/esp/flash/backups/{n} — delete backup
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Query
from pydantic import BaseModel

from services.idf_service import (
    detect_idf_installation,
    get_esptool_cmd,
    get_idf_env,
    get_idf_esptool_cmd,
    get_idf_python,
    idf_build,
    idf_flash,
    idf_monitor,
    idf_ready,
)
from services.esp_terminal_service import (
    HAS_PYSERIAL,
    BUILD_COMMAND_TEMPLATES,
    close_connection,
    get_or_create_connection,
    list_serial_ports,
    resolve_flash_method,
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
    """List all serial ports with ESP device auto-detection and flash method."""
    return list_serial_ports()


@router.get("/serial-ports/{device:path}")
def get_port_detail(device: str):
    """Get details for a specific serial port."""
    from services.esp_terminal_service import get_port_info

    info = get_port_info(device)
    if info is None:
        raise HTTPException(404, f"Port {device} not found")
    return info


# ── Multi-family Build Commands ──────────────────────────────────────────

@router.get("/build-commands")
def get_build_commands(family: str = "esp32", port: str = "", target: str = ""):
    """Get build/flash/monitor commands for a device family.

    Supported families: esp32, rp2040, rp2350, rockchip, circuitpython, luckfox, rpi-sbc
    """
    flash_method, toolchain = resolve_flash_method(family, None)
    if flash_method == "unknown":
        return {
            "family": family,
            "flash_method": "unknown",
            "available": False,
            "message": f"No build template for family '{family}'.",
            "commands": {},
        }

    templates = BUILD_COMMAND_TEMPLATES.get(flash_method, {})
    port_or_ip = port or "auto-detect"
    resolved_target = target or ("esp32" if flash_method == "esptool" else family)

    # Render commands with placeholders replaced
    commands = {}
    for step, template in templates.items():
        cmd = template.format(
            target=resolved_target,
            port=port_or_ip,
            firmware=family,
            ip=port_or_ip,
        )
        commands[step] = cmd

    return {
        "family": family,
        "flash_method": flash_method,
        "toolchain": toolchain,
        "available": True,
        "target": resolved_target,
        "port": port or "auto-detect",
        "commands": commands,
    }


# ── Fleet Devices (for quick-select in Dev Console) ──────────────────────

@router.get("/fleet-devices")
def get_fleet_devices():
    """Return fleet devices tagged with flash method for the ESP Dev Console quick-select."""
    from services.edge_discovery import list_registry_devices

    registry = list_registry_devices(include_low_confidence=False)
    devices = registry.get("devices", [])

    result = []
    for d in devices:
        family = d.get("family", "unknown")
        flash_method, toolchain = resolve_flash_method(family, d.get("chip"))
        result.append({
            "id": d.get("id"),
            "nickname": d.get("nickname") or d.get("id"),
            "chip": d.get("chip"),
            "family": family,
            "flash_method": flash_method,
            "toolchain": toolchain,
            "paired": d.get("paired", False),
            "ip": d.get("ip"),
            "port": d.get("port"),
            "drive": d.get("drive"),
            "status": d.get("status", "unknown"),
            "connection": d.get("connection"),
        })

    return {
        "devices": result,
        "count": len(result),
        "flashable_count": len([d for d in result if d["flash_method"] != "unknown"]),
    }


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
    """Full ESP-IDF toolchain status — auto-detects installed IDF from ~/.espressif/esp_idf.json.

    Returns: installed versions, active path, IDF Python, all toolchains (xtensa/riscv),
    esptool version, cmake, ninja, openocd.
    """
    return detect_idf_installation()


# ── idf.py Build / Flash / Monitor ────────────────────────────────────────

class BuildRequest(BaseModel):
    project_path: str
    target: str = "esp32"
    extra_args: Optional[List[str]] = None

class FlashRequest(BaseModel):
    project_path: str
    port: str
    target: str = "esp32"
    baud: str = "921600"

@router.post("/idf/build")
def idf_project_build(req: BuildRequest):
    """Build an ESP-IDF project using idf.py."""
    return idf_build(req.project_path, target=req.target, extra_args=req.extra_args)

@router.post("/idf/flash")
def idf_project_flash(req: FlashRequest):
    """Flash a built ESP-IDF project to device using idf.py flash."""
    return idf_flash(req.project_path, port=req.port, target=req.target, baud=req.baud)

@router.get("/idf/monitor")
def idf_project_monitor(project_path: str, port: str, target: str = "esp32"):
    """Get the idf.py monitor command for interactive serial monitoring."""
    return idf_monitor(project_path, port=port, target=target)


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
        "idf_available": idf_ready(),
        "library_path": "libraries/esp-now-lib/",
    }


# ── Firmware Templates ──────────────────────────────────────────────────

@router.get("/firmware-templates")
def list_firmware_templates():
    """List all available firmware templates — ESP-NOW examples + Bit Pirate + baked firmwares."""
    templates = []

    # ESP-NOW examples
    if espnow_available():
        for ex in list_examples().get("examples", []):
            templates.append({
                "id": f"espnow/{ex['name']}",
                "name": ex['name'].replace("_", " ").title(),
                "category": "espnow",
                "category_label": "ESP-NOW",
                "description": f"ESP-NOW mesh example: {ex['name']}",
                "path": ex.get("path", ""),
                "icon": "radio",
                "actions": ["build", "flash"],
            })

    # ESP32-Bit-Pirate firmware template (submodule)
    bit_pirate_dir = REPO_ROOT / "libraries" / "esp-bit-pirate"
    if bit_pirate_dir.exists():
        bp_src = bit_pirate_dir / "src"
        bp_webflasher = bit_pirate_dir / "webflasher"
        templates.append({
            "id": "bit-pirate/esp32-bit-pirate",
            "name": "ESP32 Bit Pirate",
            "category": "firmware",
            "category_label": "Firmware",
            "description": "Multi-protocol hardware hacking tool — 23 modes: I2C, SPI, UART, JTAG, CAN, RFID, SubGHz, Bluetooth, Wi-Fi, IR, FM, CELL. Web flasher + web serial terminal.",
            "path": str(bit_pirate_dir.relative_to(REPO_ROOT)),
            "icon": "cpu",
            "platformio_config": "platformio.ini" if (bit_pirate_dir / "platformio.ini").exists() else None,
            "web_flasher": str(bp_webflasher.relative_to(REPO_ROOT)) if bp_webflasher.exists() else None,
            "modes": 23,
            "boards": [
                "ESP32-S3 Dev Kit", "LILYGO T-Display", "LILYGO T-Embed", "LILYGO T-Embed CC1101",
                "M5 AtomS3 Lite", "M5 Cardputer", "M5 StampS3", "M5 Stick S3", "Seeed Xiao S3",
            ],
            "actions": ["build", "flash", "web-flash"],
            "license": "MIT",
            "wiki": "https://github.com/geo-tp/ESP32-Bit-Pirate/wiki",
        })

    # ESP-NOW library baked templates
    espnow_lib = REPO_ROOT / "libraries" / "esp-now-lib"
    if espnow_lib.exists():
        templates.append({
            "id": "template/espnow-mesh-node",
            "name": "ESP-NOW Mesh Node",
            "category": "template",
            "category_label": "Template",
            "description": "Bare ESP-NOW mesh node firmware template — build on top of ESP-NOW control, OTA, and security modules.",
            "path": "libraries/esp-now-lib/src",
            "icon": "zap",
            "actions": ["build"],
        })

    # CircuitPython template (for RP2040 / Adafruit boards)
    circuitpython_dir = REPO_ROOT / "firmware" / "circuitpython-agent"
    if circuitpython_dir.exists():
        templates.append({
            "id": "template/circuitpython-agent",
            "name": "CircuitPython Agent",
            "category": "template",
            "category_label": "Template",
            "description": "CircuitPython edge agent for RP2040/RP2350/Adafruit boards — USB mass-storage flash.",
            "path": str(circuitpython_dir.relative_to(REPO_ROOT)),
            "icon": "cpu",
            "flash_method": "uf2",
            "actions": ["flash"],
        })

    return {
        "templates": templates,
        "count": len(templates),
        "categories": list(set(t["category_label"] for t in templates)),
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


# ── Real Device Flash / Backup / Detect ────────────────────────────────────
# These use actual esptool + pyserial (NOT stubs) to interact with hardware.

import hashlib
import tempfile
from datetime import datetime, timezone

from services.esp_terminal_service import HAS_PYSERIAL, list_serial_ports


@router.get("/flash/detect/{device:path}")
def detect_chip(device: str):
    """Detect ESP chip info via esptool chip-id (REAL hardware call)."""
    if not HAS_PYSERIAL:
        raise HTTPException(500, "pyserial not installed — cannot detect chip")

    esptool = get_esptool_cmd()
    try:
        result = subprocess.run(
            esptool + ["--port", device, "chip-id"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            # chip-id succeeded; if it didn't, try flash_id (underscore deprecation) as fallback
            result = subprocess.run(
                esptool + ["--port", device, "flash_id"],
                capture_output=True, text=True, timeout=15,
            )
        return {
            "success": result.returncode == 0,
            "device": device,
            "output": result.stdout.strip(),
            "error": result.stderr.strip() if result.returncode != 0 else None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except FileNotFoundError:
        raise HTTPException(500, "esptool.py not found — run: pip install esptool")
    except subprocess.TimeoutExpired:
        raise HTTPException(500, f"Timed out probing {device}")


@router.post("/flash/backup/{device:path}")
def backup_firmware(device: str, size: str = "4MB"):
    """Backup current firmware from device via esptool read_flash (REAL)."""
    if not HAS_PYSERIAL:
        raise HTTPException(500, "pyserial not installed")

    backup_dir = Path(__file__).resolve().parents[1] / "data" / "firmware_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    safe_name = device.replace("/", "_").replace("\\", "_").replace(":", "_")
    backup_path = backup_dir / f"{safe_name}-{ts}-backup.bin"

    esptool = get_esptool_cmd()
    try:
        result = subprocess.run(
            esptool + ["--port", device, "read_flash", "0", size, str(backup_path)],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            return {
                "success": False,
                "device": device,
                "error": result.stderr.strip(),
                "backup_path": None,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        backup_size = backup_path.stat().st_size if backup_path.exists() else 0
        return {
            "success": True,
            "device": device,
            "backup_path": str(backup_path),
            "backup_size": backup_size,
            "backup_size_mb": round(backup_size / (1024 * 1024), 2),
            "output": result.stdout.strip(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except FileNotFoundError:
        raise HTTPException(500, "esptool.py not found")
    except subprocess.TimeoutExpired:
        raise HTTPException(500, f"Backup timed out for {device}")


@router.post("/flash/write/{device:path}")
def flash_firmware(
    device: str,
    firmware_path: str,
    offset: str = "0x0",
    baud: str = "921600",
    backup_first: bool = True,
):
    """Flash firmware to device (REAL esptool write_flash).

    Set backup_first=true to auto-backup before flashing.
    """
    if not HAS_PYSERIAL:
        raise HTTPException(500, "pyserial not installed")

    fw = Path(firmware_path)
    if not fw.exists():
        raise HTTPException(404, f"Firmware file not found: {firmware_path}")

    result = {"device": device, "firmware": str(fw), "offset": offset, "backup": None}

    # Auto-backup before flash
    if backup_first:
        try:
            backup_result = backup_firmware(device)
            result["backup"] = backup_result
        except Exception as e:
            result["backup_warning"] = str(e)

    esptool = get_esptool_cmd()
    try:
        flash_result = subprocess.run(
            esptool + ["--port", device, "--baud", baud,
             "write_flash", offset, str(fw)],
            capture_output=True, text=True, timeout=300,
        )
        result["success"] = flash_result.returncode == 0
        result["output"] = flash_result.stdout.strip()
        result["error"] = flash_result.stderr.strip() if flash_result.returncode != 0 else None
        result["timestamp"] = datetime.now(timezone.utc).isoformat()
        return result
    except FileNotFoundError:
        raise HTTPException(500, "esptool.py not found")
    except subprocess.TimeoutExpired:
        raise HTTPException(500, f"Flash timed out for {device}")


@router.post("/flash/micropython/{device:path}")
def flash_micropython_files(device: str, source_dir: str):
    """Push MicroPython files to device via mpremote/ampy (REAL).

    Copies all .py files from source_dir to the device root.
    """
    if not HAS_PYSERIAL:
        raise HTTPException(500, "pyserial not installed")

    src = Path(source_dir)
    if not src.exists() or not src.is_dir():
        raise HTTPException(404, f"Source directory not found: {source_dir}")

    py_files = list(src.glob("*.py")) + list(src.glob("*.json"))
    results = []

    for f in py_files:
        target = f":{f.name}"
        try:
            r = subprocess.run(
                [sys.executable, "-m", "mpremote", "connect", device, "fs", "cp", str(f), target],
                capture_output=True, text=True, timeout=30,
            )
            if r.returncode != 0:
                # Fallback to ampy
                r2 = subprocess.run(
                    [sys.executable, "-m", "ampy.cli", "--port", device, "put", str(f), f.name],
                    capture_output=True, text=True, timeout=30,
                )
                results.append({
                    "file": f.name,
                    "success": r2.returncode == 0,
                    "tool": "ampy",
                    "error": r2.stderr.strip() if r2.returncode != 0 else None,
                })
            else:
                results.append({
                    "file": f.name,
                    "success": True,
                    "tool": "mpremote",
                    "error": None,
                })
        except Exception as e:
            results.append({"file": f.name, "success": False, "error": str(e)})

    return {
        "success": all(r["success"] for r in results),
        "device": device,
        "files_transferred": len(results),
        "results": results,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/flash/backups")
def list_backups():
    """List all firmware backups on disk."""
    backup_dir = Path(__file__).resolve().parents[1] / "data" / "firmware_backups"
    if not backup_dir.exists():
        return {"backups": [], "count": 0}

    backups = []
    for f in sorted(backup_dir.glob("*-backup.bin"), key=lambda x: x.stat().st_mtime, reverse=True):
        backups.append({
            "name": f.name,
            "path": str(f),
            "size_bytes": f.stat().st_size,
            "size_mb": round(f.stat().st_size / (1024 * 1024), 2),
            "created": datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).isoformat(),
        })
    return {"backups": backups, "count": len(backups), "directory": str(backup_dir)}


@router.delete("/flash/backups/{name}")
def delete_backup(name: str):
    """Delete a firmware backup."""
    backup_dir = Path(__file__).resolve().parents[1] / "data" / "firmware_backups"
    f = backup_dir / name
    if not f.exists():
        raise HTTPException(404, f"Backup not found: {name}")
    f.unlink()
    return {"deleted": True, "name": name}
