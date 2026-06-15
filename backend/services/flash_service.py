"""Flash Service — USB flashing for Rockchip and other edge devices via native tools.

Wraps rkdeveloptool (Rockchip), esptool (ESP32), and future tool backends.
"""

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

BACKEND_ROOT = Path(os.path.dirname(os.path.dirname(__file__)))
TOOLS_DIR = BACKEND_ROOT / "data" / "flash_tools"
TOOLS_DIR.mkdir(parents=True, exist_ok=True)

# ── Tool detection ──

def _which(name: str) -> Optional[Path]:
    """Find binary on PATH or in bundled tools dir."""
    bundled = TOOLS_DIR / name / f"{name}.exe" if os.name == "nt" else TOOLS_DIR / name / name
    if bundled.exists():
        return bundled
    found = shutil.which(name)
    return Path(found) if found else None

def detect_rkdeveloptool() -> Optional[Path]:
    """Return path to rkdeveloptool if available."""
    return _which("rkdeveloptool")

def detect_upgrade_tool() -> Optional[Path]:
    """Return path to upgrade_tool (Rockchip proprietary) if available."""
    return _which("upgrade_tool")

def flash_tools_available() -> dict:
    """Return available flash tool backends."""
    return {
        "rkdeveloptool": detect_rkdeveloptool() is not None,
        "upgrade_tool": detect_upgrade_tool() is not None,
        "esptool": shutil.which("esptool") is not None or shutil.which("esptool.py") is not None,
    }

# ── Rockchip operations ──

def rk_read_flash_id() -> dict:
    """Read flash ID from Rockchip device in Loader mode."""
    tool = detect_rkdeveloptool()
    if not tool:
        return {"ok": False, "error": "rkdeveloptool not found"}
    try:
        result = subprocess.run(
            [str(tool), "rfi"],
            capture_output=True, text=True, timeout=10
        )
        return {"ok": result.returncode == 0, "output": result.stdout.strip(), "stderr": result.stderr.strip()}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def rk_read_flash(offset_sectors: int = 0, sector_count: int = 1, output_file: Optional[str] = None) -> dict:
    """Read raw flash sectors from Rockchip device in Loader mode."""
    tool = detect_rkdeveloptool()
    if not tool:
        return {"ok": False, "error": "rkdeveloptool not found"}
    out = output_file or str(BACKEND_ROOT / "data" / "flash_dump.bin")
    try:
        result = subprocess.run(
            [str(tool), "rl", str(offset_sectors), str(sector_count), out],
            capture_output=True, text=True, timeout=300
        )
        return {
            "ok": result.returncode == 0,
            "offset_sectors": offset_sectors,
            "sector_count": sector_count,
            "output_file": out,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}

def rk_write_flash(offset_sectors: int, input_file: str) -> dict:
    """Write firmware to Rockchip device flash."""
    tool = detect_rkdeveloptool()
    if not tool:
        return {"ok": False, "error": "rkdeveloptool not found"}
    try:
        result = subprocess.run(
            [str(tool), "wl", str(offset_sectors), input_file],
            capture_output=True, text=True, timeout=600
        )
        return {
            "ok": result.returncode == 0,
            "offset_sectors": offset_sectors,
            "input_file": input_file,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}

def rk_detect_device() -> dict:
    """Detect connected Rockchip device in Loader mode. Returns chip info if found."""
    tool = detect_rkdeveloptool()
    if not tool:
        return {"ok": False, "error": "rkdeveloptool not found"}
    try:
        result = subprocess.run(
            [str(tool), "ld"],
            capture_output=True, text=True, timeout=10
        )
        return {"ok": result.returncode == 0, "output": result.stdout.strip(), "stderr": result.stderr.strip()}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def rk_reset_device() -> dict:
    """Reset Rockchip device (reboots it out of Loader mode)."""
    tool = detect_rkdeveloptool()
    if not tool:
        return {"ok": False, "error": "rkdeveloptool not found"}
    try:
        result = subprocess.run(
            [str(tool), "rd"],
            capture_output=True, text=True, timeout=10
        )
        return {"ok": result.returncode == 0, "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}
    except Exception as e:
        return {"ok": False, "error": str(e)}
