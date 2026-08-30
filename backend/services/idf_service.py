"""ESP-IDF Toolchain Service — detection, version management, build/flash commands.

Single source of truth for all ESP-IDF interactions in NPU-STACK.
Preferentially uses workspace-bundled IDF (libraries/esp-idf), then falls back
to ~/.espressif/ system installs.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ── Constants ────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parents[2]
BUNDLED_IDF_DIR = REPO_ROOT / "libraries" / "esp-idf"
ESPRESSIF_DIR = Path.home() / ".espressif"
ESP_IDF_JSON = ESPRESSIF_DIR / "esp_idf.json"
IDF_PROJECTS_DIR = REPO_ROOT / "firmware" / "esp-idf-projects"
ESP_FULL_FLASH_BYTES = 8 * 1024 * 1024
SUPPORTED_IDF_FLASH_SIZE_MB = frozenset({2, 4, 8, 16, 32})


# ── Detection ─────────────────────────────────────────────────────────────

def _idf_version_from_path(idf_path: Path) -> Optional[str]:
    """Read IDF version from version.txt or git describe."""
    vf = idf_path / "version.txt"
    if vf.exists():
        return vf.read_text(encoding="utf-8").strip()
    # Try git describe
    try:
        r = subprocess.run(
            ["git", "describe", "--tags", "--always"],
            capture_output=True, text=True, timeout=10, cwd=str(idf_path),
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return None


def _detect_bundled_idf() -> Optional[Dict[str, Any]]:
    """Detect workspace-bundled ESP-IDF at libraries/esp-idf."""
    if not BUNDLED_IDF_DIR.exists():
        return None
    idf_py = BUNDLED_IDF_DIR / "tools" / "idf.py"
    if not idf_py.exists():
        return None

    version = _idf_version_from_path(BUNDLED_IDF_DIR) or "v6.x (bundled)"
    # Use our venv Python for the bundled IDF (not a separate IDF Python env)
    python_exe = sys.executable

    return {
        "id": "npustack-bundled",
        "version": version,
        "path": str(BUNDLED_IDF_DIR),
        "python": python_exe,
        "source": "workspace-bundled",
    }


def detect_idf_installation() -> Dict[str, Any]:
    """Detect all installed ESP-IDF versions and toolchains.

    Priority: workspace-bundled (libraries/esp-idf) → ~/.espressif/system installs.

    Returns comprehensive status: path, version, Python env, available tools,
    xtensa/riscv compilers, esptool path, openocd, cmake, ninja.
    """
    result: Dict[str, Any] = {
        "installed": False,
        "versions": [],
        "active_version": None,
        "active_path": None,
        "idf_python": None,
        "esptool_path": None,
        "toolchains": {},
        "tools": {},
        "source": None,
    }

    # ── Priority 1: Workspace-bundled IDF (libraries/esp-idf) ──
    bundled = _detect_bundled_idf()
    if bundled:
        result["installed"] = True
        result["versions"].append(bundled)
        result["active_version"] = bundled["version"]
        result["active_path"] = bundled["path"]
        result["idf_python"] = bundled["python"]
        result["source"] = "bundled"
        _probe_bundled_tools(result, BUNDLED_IDF_DIR)
        return result

    # ── Priority 2: ~/.espressif system installs ──
    cfg = _parse_esp_idf_json()
    if cfg:
        result["installed"] = True
        result["source"] = "espressif"
        installed = cfg.get("idfInstalled", {})
        for idf_id, info in installed.items():
            result["versions"].append({
                "id": idf_id,
                "version": info.get("version", "unknown"),
                "path": info.get("path", ""),
                "python": info.get("python", ""),
                "source": "espressif-installer",
            })
        active_id = cfg.get("idfSelectedId", "")
        if active_id in installed:
            active = installed[active_id]
            result["active_version"] = active.get("version")
            result["active_path"] = active.get("path")
            result["idf_python"] = active.get("python", sys.executable)
        _probe_espressif_tools(result, Path(cfg.get("idfToolsPath", str(ESPRESSIF_DIR))))

    return result


def _parse_esp_idf_json() -> Optional[Dict[str, Any]]:
    """Parse ~/.espressif/esp_idf.json for installed IDF info."""
    if not ESP_IDF_JSON.exists():
        return None
    try:
        return json.loads(ESP_IDF_JSON.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _probe_bundled_tools(result: Dict[str, Any], idf_dir: Path) -> None:
    """Probe toolchains inside a workspace-bundled IDF."""
    tools_json = idf_dir / "tools" / "tools.json"
    if tools_json.exists():
        try:
            tools_cfg = json.loads(tools_json.read_text(encoding="utf-8"))
            for t in tools_cfg.get("tools", []):
                name = t.get("name", "")
                for v in t.get("versions", []):
                    if v.get("status") == "recommended":
                        result["toolchains"][name] = {
                            "available": True,
                            "version": v.get("name", "unknown"),
                            "path": "",
                        }
        except (json.JSONDecodeError, KeyError):
            pass
    result["toolchains"]["bundled_idf"] = {"available": True, "path": str(idf_dir)}


def _probe_espressif_tools(result: Dict[str, Any], tools_dir: Path) -> None:
    """Probe toolchains from an Espressif installer layout."""
    tools_path = tools_dir / "tools"
    _tool_checks = {
        "xtensa_esp32": "xtensa-esp32-elf", "xtensa_esp32s2": "xtensa-esp32s2-elf",
        "xtensa_esp32s3": "xtensa-esp32s3-elf", "riscv32_esp": "riscv32-esp-elf",
        "openocd": "openocd-esp32", "cmake": "cmake", "ninja": "ninja",
        "dfu_util": "dfu-util", "ccache": "ccache", "idf_python": "idf-python",
    }
    for key, td_name in _tool_checks.items():
        td = tools_path / td_name
        if td.exists():
            versions = sorted(
                [d for d in td.iterdir() if d.is_dir() and not d.name.startswith(".")],
                reverse=True,
            )
            if versions:
                result["toolchains"][key] = {
                    "available": True, "path": str(versions[0]), "version": versions[0].name,
                }
                continue
        result["toolchains"][key] = {"available": False}


def get_idf_env(project_dir: Optional[str] = None) -> Dict[str, str]:
    """Return environment dict for running idf.py / esptool with the detected IDF.

    On Windows, runs export.bat and captures env. On Linux/macOS, sources export.sh.
    """
    info = detect_idf_installation()
    env = os.environ.copy()

    if not info["installed"] or not info["active_path"]:
        return env

    idf_path = info["active_path"]
    idf_python = info.get("idf_python", sys.executable)

    env["IDF_PATH"] = idf_path
    env["IDF_PYTHON"] = idf_python
    env["PYTHON"] = idf_python

    # Add toolchain bins to PATH
    for tc_name, tc_info in info.get("toolchains", {}).items():
        if tc_info.get("available") and tc_info.get("path"):
            tc_bin = Path(tc_info["path"]) / "bin"
            if tc_bin.exists():
                env["PATH"] = str(tc_bin) + os.pathsep + env.get("PATH", "")

    return env


# ── Build / Flash / Monitor (idf.py) ──────────────────────────────────────

def idf_build(
    project_path: str,
    target: str = "esp32",
    extra_args: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Build an IDF project using idf.py."""
    info = detect_idf_installation()
    if not info["installed"]:
        return {"success": False, "error": "ESP-IDF not installed. Run: https://docs.espressif.com/projects/esp-idf/"}

    proj = Path(project_path)
    if not proj.exists():
        return {"success": False, "error": f"Project not found: {project_path}"}

    env = get_idf_env()
    idf_py_path = Path(info["active_path"]) / "tools" / "idf.py"

    cmd = [info["idf_python"], str(idf_py_path), "-C", str(proj), "build"]
    if extra_args:
        cmd.extend(extra_args)

    # Set target via env
    env["IDF_TARGET"] = target

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600, env=env, cwd=str(proj))
        return {
            "success": r.returncode == 0,
            "project": str(proj),
            "target": target,
            "output": r.stdout.strip()[-3000:] if r.stdout else "",
            "error": r.stderr.strip()[-1000:] if r.stderr else None,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Build timed out (10 minutes)"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def backup_before_idf_flash(port: str, flash_size_mb: int = 8) -> Dict[str, Any]:
    """Create and validate the mandatory full-flash backup for IDF writes."""
    if not str(port or "").strip():
        return {"success": False, "error": "ESP32 firmware writes require a serial port for the mandatory full-flash backup"}
    if flash_size_mb not in SUPPORTED_IDF_FLASH_SIZE_MB:
        supported = ", ".join(str(size) for size in sorted(SUPPORTED_IDF_FLASH_SIZE_MB))
        return {"success": False, "error": f"Unsupported ESP flash size {flash_size_mb} MB; choose one of: {supported}"}

    expected_size = flash_size_mb * 1024 * 1024

    backup_dir = REPO_ROOT / "backend" / "data" / "firmware_backups" / "idf"
    backup_dir.mkdir(parents=True, exist_ok=True)
    safe_port = re.sub(r"[^A-Za-z0-9_.-]+", "_", port)
    backup_path = backup_dir / f"{safe_port}-{flash_size_mb}MB-{time.strftime('%Y%m%d-%H%M%S')}-backup.bin"

    try:
        if backup_path.exists():
            backup_path.unlink()
        result = subprocess.run(
            get_esptool_cmd() + [
                "--port", port, "--baud", "460800", "read_flash", "0",
                hex(expected_size), str(backup_path),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        backup_size = backup_path.stat().st_size if backup_path.exists() else 0
        if result.returncode != 0:
            return {
                "success": False,
                "error": (result.stderr or "Backup command failed").strip(),
                "expected_size": expected_size,
                "backup_path": None,
            }
        if backup_size != expected_size:
            return {
                "success": False,
                "error": f"Incomplete backup: expected {expected_size} bytes, got {backup_size}",
                "expected_size": expected_size,
                "backup_size": backup_size,
                "backup_path": None,
            }
        return {
            "success": True,
            "backup_path": str(backup_path),
            "backup_size": backup_size,
            "expected_size": expected_size,
            "output": (result.stdout or "").strip(),
        }
    except FileNotFoundError:
        return {"success": False, "error": "esptool not found", "backup_path": None}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Backup timed out for {port}", "backup_path": None}
    except Exception as exc:
        return {"success": False, "error": str(exc), "backup_path": None}


def idf_flash(
    project_path: str,
    port: str,
    target: str = "esp32",
    baud: str = "921600",
    flash_size_mb: int = 8,
) -> Dict[str, Any]:
    """Flash a built IDF project to device."""
    info = detect_idf_installation()
    if not info["installed"]:
        return {"success": False, "error": "ESP-IDF not installed"}

    proj = Path(project_path)
    if not proj.exists():
        return {"success": False, "error": f"Project not found: {project_path}"}

    try:
        backup = backup_before_idf_flash(port, flash_size_mb=flash_size_mb)
    except Exception as exc:
        backup = {"success": False, "error": str(exc), "backup_path": None}
    if not backup.get("success"):
        return {
            "success": False,
            "phase": "backup",
            "project": str(proj),
            "port": port,
            "target": target,
            "backup": backup,
            "error": f"Flash blocked: {backup.get('error', 'complete full-flash backup was not validated')}",
        }

    env = get_idf_env()
    idf_py_path = Path(info["active_path"]) / "tools" / "idf.py"

    cmd = [
        info["idf_python"], str(idf_py_path),
        "-C", str(proj), "flash",
        "-p", port, "-b", baud,
    ]
    env["IDF_TARGET"] = target
    env["ESPPORT"] = port

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300, env=env, cwd=str(proj))
        return {
            "success": r.returncode == 0,
            "project": str(proj),
            "port": port,
            "target": target,
            "backup": backup,
            "output": r.stdout.strip()[-3000:] if r.stdout else "",
            "error": r.stderr.strip()[-1000:] if r.stderr else None,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Flash timed out (5 minutes)"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def idf_monitor(
    project_path: str,
    port: str,
    target: str = "esp32",
) -> Dict[str, Any]:
    """Get the idf.py monitor command (returns command, doesn't run interactive)."""
    info = detect_idf_installation()
    if not info["installed"]:
        return {"success": False, "error": "ESP-IDF not installed"}

    idf_py_path = Path(info["active_path"]) / "tools" / "idf.py"

    return {
        "success": True,
        "command": f"{info['idf_python']} {idf_py_path} -C {project_path} monitor -p {port}",
        "idf_python": info["idf_python"],
        "idf_path": info["active_path"],
        "port": port,
        "target": target,
        "note": "Run this command in a terminal for interactive serial monitor",
    }


# ── Quick helpers ──────────────────────────────────────────────────────────

def idf_ready() -> bool:
    """Quick check: is ESP-IDF installed and usable?"""
    return detect_idf_installation()["installed"]


def get_esptool_cmd() -> List[str]:
    """Return the best esptool command for standalone flash operations.

    Prefers standalone esptool (newer) over IDF-bundled for chip-id/read_flash/write_flash.
    Falls back to IDF Python's esptool if standalone not available.
    """
    # Always prefer the venv's esptool (latest, 5.3.1+) for standalone operations
    return [sys.executable, "-m", "esptool"]


def get_idf_esptool_cmd() -> List[str]:
    """Return the IDF-bundled esptool command for IDF project operations (build/flash/monitor)."""
    info = detect_idf_installation()
    if info["installed"] and info.get("idf_python"):
        return [info["idf_python"], "-m", "esptool"]
    return [sys.executable, "-m", "esptool"]


def get_idf_python() -> str:
    """Return path to IDF Python executable, or system Python."""
    info = detect_idf_installation()
    return info.get("idf_python") or sys.executable
