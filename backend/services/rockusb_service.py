"""Rockchip USB (rockusb) Service — direct libusb communication with LuckFox/Rockchip devices.

Rockchip devices expose a vendor-specific USB class (0xFF) with bulk endpoints using
the "rockusb" protocol (same as rkdeveloptool). This service provides:
- Device detection (no Maskrom mode needed if rockusb.sys is loaded)
- Firmware read (backup)
- Firmware write (flash)
- Device reset

Protocol reference: https://github.com/rockchip-linux/rkdeveloptool
Rockusb uses 512-byte command blocks + bulk transfers.
"""

from __future__ import annotations

import ctypes
import json
import os
import struct
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parents[2]
BACKUPS_DIR = REPO / "backend" / "data" / "firmware_backups"
BACKUPS_DIR.mkdir(parents=True, exist_ok=True)

# Rockchip USB VID
ROCKCHIP_VID = 0x2207

# Rockusb command codes
CMD_READ_LBA = 0x05
CMD_WRITE_LBA = 0x06
CMD_RESET = 0x0B
CMD_READ_CHIP_ID = 0x0E
CMD_GET_FLASH_INFO = 0x10

# ── libusb backend (lazy init) ────────────────────────────────────────────

_backend = None

def _get_backend():
    global _backend
    if _backend is not None:
        return _backend
    import usb.backend.libusb1
    # Try common DLL paths
    for path in [
        r"C:\Windows\System32\libusb-1.0.dll",
        r"C:\Users\iAMBLACK\AppData\Local\Temp\libusb_dll\libusb-1.0.dll",
    ]:
        if os.path.exists(path):
            _backend = usb.backend.libusb1.get_backend(find_library=lambda x: path)
            if _backend:
                return _backend
    _backend = usb.backend.libusb1.get_backend()
    return _backend


# ── Device Detection ──────────────────────────────────────────────────────

def detect_rockchip_devices() -> List[Dict[str, Any]]:
    """Find all connected Rockchip devices via libusb. No Maskrom required."""
    be = _get_backend()
    if not be:
        return []

    import usb.core
    devices = []
    for d in usb.core.find(find_all=True, backend=be, idVendor=ROCKCHIP_VID):
        info = {
            "vid": f"0x{d.idVendor:04X}",
            "pid": f"0x{d.idProduct:04X}",
            "bus": d.bus,
            "address": d.address,
            "port": str(d.port_numbers) if d.port_numbers else "?",
            "chip": _pid_to_chip_name(d.idProduct),
            "family": "rockchip",
            "npu": d.idProduct in [0x110B, 0x110C, 0x350A, 0x350B, 0x350D],
        }

        # Try to read manufacturer/product strings
        import usb.util
        try:
            if d.iManufacturer:
                info["manufacturer"] = usb.util.get_string(d, d.iManufacturer)
        except:
            info["manufacturer"] = "Fuzhou Rockchip"
        try:
            if d.iProduct:
                info["product"] = usb.util.get_string(d, d.iProduct)
        except:
            info["product"] = info["chip"]

        # Interface info
        try:
            for cfg in d:
                for intf in cfg:
                    info["interface_class"] = f"0x{intf.bInterfaceClass:02X}"
                    if intf.bInterfaceClass == 0xFF:
                        info["rockusb_mode"] = True
        except:
            pass

        devices.append(info)
    return devices


def _pid_to_chip_name(pid: int) -> str:
    """Map Rockchip PID to chip name."""
    names = {
        0x0011: "RK28xx Maskrom",
        0x110A: "RV1103 (LuckFox Pico)",
        0x110B: "RV1103 (LuckFox Pico Ultra)",
        0x110C: "RV1106 (LuckFox Pico Pro/Ultra)",
        0x330C: "RK3308 (LuckFox Pico Mini)",
        0x350A: "RK3588",
        0x350B: "RK3588S",
        0x350D: "RK3562",
    }
    return names.get(pid, f"RK{pid:04X}")


# ── Firmware Backup ──────────────────────────────────────────────────────

def backup_rockchip_firmware(device_addr: str = "auto", size_mb: int = 256) -> Dict[str, Any]:
    """Read full firmware from a Rockchip device via rockusb protocol.

    Uses raw USB bulk transfers to read flash sectors.
    Falls back to rkdeveloptool if available.
    """
    # Check if rkdeveloptool is available (preferred)
    if _has_rkdeveloptool():
        return _backup_via_rkdeveloptool(size_mb)

    # Fallback: try libusb raw read
    be = _get_backend()
    if not be:
        return {"success": False, "error": "No libusb backend available. Install libusb-1.0.dll"}

    import usb.core
    try:
        dev = usb.core.find(backend=be, idVendor=ROCKCHIP_VID)
        if not dev:
            return {"success": False, "error": "No Rockchip device found"}

        # Claim device
        dev.set_configuration()
        import usb.util
        usb.util.claim_interface(dev, 0)

        ts = time.strftime("%Y%m%d-%H%M%S")
        chip = _pid_to_chip_name(dev.idProduct).replace(" ", "_")
        backup_path = BACKUPS_DIR / f"rockchip-{chip}-{ts}.bin"

        # Read in 512-byte sectors via bulk endpoint
        endpoint = dev[0][(0, 0)][0]  # First bulk endpoint
        total_bytes = size_mb * 1024 * 1024
        sector_size = 512
        sectors = total_bytes // sector_size

        with open(backup_path, "wb") as f:
            for sector in range(0, sectors, 8):
                # Build read command
                cmd = struct.pack("<II", CMD_READ_LBA, sector // 8)
                dev.write(endpoint.bEndpointAddress, cmd, timeout=5000)
                data = dev.read(endpoint.bEndpointAddress | 0x80, sector_size * 8, timeout=10000)
                f.write(data)

        usb.util.release_interface(dev, 0)
        file_size = backup_path.stat().st_size
        return {
            "success": True,
            "backup_path": str(backup_path),
            "size_mb": round(file_size / (1024 * 1024), 2),
            "method": "libusb-raw",
            "device": chip,
        }
    except Exception as e:
        return {"success": False, "error": str(e), "hint": "Try installing rkdeveloptool for reliable backup"}


def _has_rkdeveloptool() -> bool:
    """Check if rkdeveloptool is installed."""
    import shutil
    return shutil.which("rkdeveloptool") is not None


def _backup_via_rkdeveloptool(size_mb: int = 256) -> Dict[str, Any]:
    """Backup using rkdeveloptool CLI (most reliable)."""
    import subprocess
    try:
        # Read first 256MB of flash
        ts = time.strftime("%Y%m%d-%H%M%S")
        backup_path = BACKUPS_DIR / f"rockchip-rkdeveloptool-{ts}.bin"

        # rkdeveloptool requires: rl <sector> <count> <file>
        # 1 sector = 512 bytes, 256MB = 524288 sectors
        sectors = size_mb * 2048  # MB to 512-byte sectors
        r = subprocess.run(
            ["rkdeveloptool", "rl", "0", str(sectors), str(backup_path)],
            capture_output=True, text=True, timeout=600,
        )
        if r.returncode == 0:
            return {
                "success": True,
                "backup_path": str(backup_path),
                "size_mb": round(backup_path.stat().st_size / (1024 * 1024), 2),
                "method": "rkdeveloptool",
            }
        return {"success": False, "error": r.stderr.strip()[-500:]}
    except FileNotFoundError:
        return {"success": False, "error": "rkdeveloptool not installed"}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Backup timed out"}


# ── Firmware Flash ────────────────────────────────────────────────────────

def flash_rockchip_firmware(firmware_path: str) -> Dict[str, Any]:
    """Flash firmware to Rockchip device. Requires rkdeveloptool or upgrade_tool."""
    fw = Path(firmware_path)
    if not fw.exists():
        return {"success": False, "error": f"Firmware not found: {firmware_path}"}

    if _has_rkdeveloptool():
        return _flash_via_rkdeveloptool(fw)

    return {"success": False, "error": "rkdeveloptool not installed. Install for Rockchip flashing."}


def _flash_via_rkdeveloptool(fw_path: Path) -> Dict[str, Any]:
    """Flash using rkdeveloptool."""
    import subprocess
    try:
        r = subprocess.run(
            ["rkdeveloptool", "wl", "0", str(fw_path)],
            capture_output=True, text=True, timeout=600,
        )
        if r.returncode == 0:
            # Reset device
            subprocess.run(["rkdeveloptool", "rd"], capture_output=True, timeout=10)
            return {"success": True, "output": r.stdout.strip()[-500:]}
        return {"success": False, "error": r.stderr.strip()[-500:]}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Flash timed out"}
    except Exception as e:
        return {"success": False, "error": str(e)}
