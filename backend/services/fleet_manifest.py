"""NPU Fleet Flash Manifest — per-platform flash/backup methods & firmware bundle prep.

Single source of truth for flashing every supported board in NPU-STACK.
Every flash operation is: backup → prepare → flash, with user confirmation.
"""
from __future__ import annotations

import json, os, shutil, subprocess, sys, time, zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parents[2]
FIRMWARE_DIR = REPO / "firmware"
DATA_DIR = REPO / "backend" / "data"
BUNDLES_DIR = DATA_DIR / "firmware_bundles"
BACKUPS_DIR = DATA_DIR / "firmware_backups"
BUNDLES_DIR.mkdir(parents=True, exist_ok=True)
BACKUPS_DIR.mkdir(parents=True, exist_ok=True)

# ── Platform Profiles (flash method + backup method + agent source) ─────

PLATFORMS = {
    "micropython-esp32": {
        "name": "ESP32 MicroPython",
        "families": ["esp32", "esp32-s2", "esp32-s3", "esp32-c3", "esp32-c6", "esp32-h2", "esp32-p4"],
        "agent_dir": "esp32-agent",
        "main_file": "main.py",
        "flash": {
            "tool": "esptool",
            "firmware_url": "https://micropython.org/resources/firmware/ESP32_GENERIC_S3-20240602-v1.23.0.bin",
            "firmware_file": "ESP32_GENERIC_S3.bin",
            "offset": "0x0",
        },
        "backup": {
            "tool": "esptool",
            "method": "read_flash",
            "args": ["0", "4MB"],
        },
        "deploy": {
            "tool": "mpremote",
            "method": "fs_cp",
            "args_template": "cp {src} :{target}",
        },
    },
    "circuitpython": {
        "name": "CircuitPython",
        "families": ["circuitpython", "rp2040", "rp2350", "nrf", "microchip", "seeed-xiao", "teensy"],
        "agent_dir": "circuitpython-agent",
        "main_file": "code.py",
        "flash": {
            "tool": "usb-mass-storage",
            "method": "copy_to_circuitpy",
        },
        "backup": {
            "tool": "usb-mass-storage",
            "method": "copy_from_circuitpy",
        },
        "deploy": {
            "tool": "usb-mass-storage",
            "method": "copy_files",
        },
    },
    "linux-sbc": {
        "name": "Linux Edge Agent",
        "families": ["rpi-sbc", "rockchip", "allwinner", "nvidia", "coral", "movidius", "qualcomm", "luckfox"],
        "agent_dir": "linux-agent",
        "main_file": "npu-agent.py",
        "flash": {
            "tool": "scp",
            "method": "scp_install",
        },
        "backup": {
            "tool": "scp",
            "method": "scp_pull",
        },
        "deploy": {
            "tool": "scp",
            "method": "scp_push",
        },
    },
}

# ── Bundle Preparation ────────────────────────────────────────────────────

def prepare_device_bundle(
    device_id: str,
    platform: str,
    wifi_ssid: str = "",
    wifi_pass: str = "",
    mqtt_broker: str = "127.0.0.1",
    mqtt_port: int = 1883,
) -> Dict[str, Any]:
    """Generate a ready-to-flash firmware bundle for a specific device.

    Creates a ZIP containing:
    - Agent code (main.py/code.py/npu-agent.py)
    - npu_config.json (WiFi, MQTT, device ID baked in)
    - README.txt (flash instructions)
    - Optional: firmware binary for platforms needing base OS

    The ZIP can be downloaded and flashed via the UI with backup enforcement.
    """
    if platform not in PLATFORMS:
        return {"success": False, "error": f"Unknown platform: {platform}"}

    prof = PLATFORMS[platform]
    src = FIRMWARE_DIR / prof["agent_dir"]
    if not src.exists():
        return {"success": False, "error": f"Agent source not found: {src}"}

    ts = time.strftime("%Y%m%d-%H%M%S")
    safe_name = device_id.replace("/", "_").replace("\\", "_").replace(":", "_").replace(".", "_")
    bundle_name = f"{safe_name}-{platform}-{ts}"
    bundle_dir = BUNDLES_DIR / bundle_name
    bundle_dir.mkdir(parents=True, exist_ok=True)

    files = []

    # Copy agent files
    for f in src.iterdir():
        if f.is_file() and f.name != "setup_agent.py":
            shutil.copy2(f, bundle_dir / f.name)
            files.append(f.name)

    # Generate baked-in config
    cfg = {
        "device_id": device_id,
        "mqtt_broker": mqtt_broker,
        "mqtt_port": mqtt_port,
        "wifi_ssid": wifi_ssid,
        "wifi_password": wifi_pass,
        "telemetry_interval": 5,
        "npu_stack_version": "1.0.0",
    }
    (bundle_dir / "npu_config.json").write_text(json.dumps(cfg, indent=2))
    files.append("npu_config.json")

    # Flash instructions
    inst = _flash_instructions(platform, prof, device_id)
    (bundle_dir / "README.txt").write_text(inst, encoding="utf-8")
    files.append("README.txt")

    # ZIP
    zip_path = BUNDLES_DIR / f"{bundle_name}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in bundle_dir.iterdir():
            zf.write(f, f.name)

    # Estimate flash size
    total_bytes = sum(f.stat().st_size for f in bundle_dir.iterdir() if f.is_file())

    return {
        "success": True,
        "bundle_id": bundle_name,
        "bundle_dir": str(bundle_dir),
        "zip_path": str(zip_path),
        "download_url": f"/api/fleet/bundles/{bundle_name}.zip",
        "platform": platform,
        "platform_name": prof["name"],
        "flash_method": prof["flash"]["tool"],
        "backup_method": prof["backup"]["tool"],
        "files": files,
        "size_kb": round(total_bytes / 1024, 1),
        "device_id": device_id,
    }


def _flash_instructions(platform: str, prof: dict, device_id: str) -> str:
    """Generate human-readable flash instructions per platform."""
    if platform == "micropython-esp32":
        return (
            f"NPU-STACK Bundle — {prof['name']}\n"
            f"Device: {device_id}\n"
            f"========================================\n\n"
            f"1. Flash MicroPython firmware (one-time):\n"
            f"   esptool.py --port COMx write_flash 0x0 ESP32_GENERIC_S3.bin\n\n"
            f"2. Push NPU agent files:\n"
            f"   mpremote connect COMx fs cp main.py :main.py\n"
            f"   mpremote connect COMx fs cp npu_config.json :npu_config.json\n\n"
            f"3. Reset device — agent auto-starts on boot\n"
            f"   mpremote connect COMx reset\n\n"
            f"After boot, device will auto-register with MQTT at {cfg['mqtt_broker']}:{cfg['mqtt_port']}\n"
        )
    elif platform == "circuitpython":
        return (
            f"NPU-STACK Bundle — {prof['name']}\n"
            f"Device: {device_id}\n"
            f"========================================\n\n"
            f"1. Double-tap reset to enter bootloader mode\n"
            f"2. Copy ALL files to the CIRCUITPY drive\n"
            f"3. Press reset — agent auto-starts on boot\n\n"
            f"After boot, device auto-registers with MQTT.\n"
            f"If WiFi is configured, it connects automatically.\n"
        )
    elif platform == "linux-sbc":
        return (
            f"NPU-STACK Bundle — {prof['name']}\n"
            f"Device: {device_id}\n"
            f"========================================\n\n"
            f"1. SCP files to device:\n"
            f"   scp npu-agent.py root@<ip>:/usr/local/bin/\n"
            f"   scp npu_config.json root@<ip>:/etc/npu-agent/config.json\n\n"
            f"2. Install as systemd service:\n"
            f"   scp npu-agent.service root@<ip>:/etc/systemd/system/\n"
            f"   ssh root@<ip> systemctl enable --now npu-agent\n\n"
            f"After boot, device auto-registers with MQTT at {cfg['mqtt_broker']}:{cfg['mqtt_port']}\n"
        )
    return "See README in bundle for instructions."

cfg = {"mqtt_broker": "YOUR_MQTT_BROKER", "mqtt_port": 1883}  # placeholder for instructions


# ── Backup (enforced before every flash) ──────────────────────────────────

def backup_device(device_id: str, platform: str, port: str = "", ip: str = "", drive: str = "") -> Dict[str, Any]:
    """Backup current firmware from a device before flashing. ALWAYS called first.

    Platform-specific backup:
    - ESP32: esptool read_flash → .bin
    - CircuitPython: copy all files from CIRCUITPY drive
    - Linux: scp pull key files
    """
    ts = time.strftime("%Y%m%d-%H%M%S")
    safe = device_id.replace("/", "_").replace("\\", "_").replace(":", "_")
    backup_dir = BACKUPS_DIR / f"{safe}-{ts}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    if platform == "micropython-esp32":
        if not port:
            return {"success": False, "error": "ESP32 requires port (e.g., COM10)"}
        backup_file = backup_dir / "firmware_backup.bin"
        try:
            r = subprocess.run(
                [sys.executable, "-m", "esptool", "--port", port, "read-flash", "0", "4MB", str(backup_file)],
                capture_output=True, text=True, timeout=120,
            )
            if r.returncode == 0 and backup_file.exists():
                # Also try to pull files if MicroPython is running
                _try_mpremote_pull(port, backup_dir)
                return {
                    "success": True,
                    "backup_path": str(backup_dir),
                    "backup_size_kb": round(backup_file.stat().st_size / 1024, 1),
                    "files": [f.name for f in backup_dir.iterdir()],
                }
            return {"success": False, "error": r.stderr.strip()[-200:]}
        except FileNotFoundError:
            return {"success": False, "error": "esptool not installed"}
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Backup timed out"}

    elif platform == "circuitpython":
        if not drive:
            # Try to find CIRCUITPY drive
            drive = _find_circuitpy_drive()
            if not drive:
                return {"success": False, "error": "CIRCUITPY drive not found. Double-tap reset to enter bootloader."}
        try:
            src = Path(drive + "/")
            if not src.exists():
                return {"success": False, "error": f"Drive {drive} not accessible"}
            for f in src.iterdir():
                if f.is_file():
                    shutil.copy2(f, backup_dir / f.name)
            return {
                "success": True,
                "backup_path": str(backup_dir),
                "files": [f.name for f in backup_dir.iterdir()],
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    elif platform == "linux-sbc":
        if not ip:
            return {"success": False, "error": "Linux SBC requires IP address"}
        try:
            # Pull agent config and key files via scp
            for f in ["/etc/npu-agent/config.json", "/usr/local/bin/npu-agent.py"]:
                r = subprocess.run(
                    ["scp", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=5",
                     f"root@{ip}:{f}", str(backup_dir)],
                    capture_output=True, text=True, timeout=30,
                )
            return {
                "success": True,
                "backup_path": str(backup_dir),
                "files": [f.name for f in backup_dir.iterdir()],
            }
        except Exception as e:
            return {"success": False, "error": f"SCP backup failed: {e}"}

    return {"success": False, "error": f"Unknown platform: {platform}"}


def _try_mpremote_pull(port: str, dest: Path) -> None:
    """Try to pull files from MicroPython device via mpremote."""
    try:
        r = subprocess.run(
            [sys.executable, "-m", "mpremote", "connect", port, "fs", "ls"],
            capture_output=True, text=True, timeout=10,
        )
        if "main.py" in r.stdout or "npu_config" in r.stdout:
            for fn in ["main.py", "npu_config.json", "boot.py"]:
                subprocess.run(
                    [sys.executable, "-m", "mpremote", "connect", port, "fs", "cp", f":{fn}", str(dest / fn)],
                    capture_output=True, timeout=10,
                )
    except Exception:
        pass


def _find_circuitpy_drive() -> Optional[str]:
    """Find the CIRCUITPY drive letter on Windows."""
    import string
    for letter in string.ascii_uppercase:
        try:
            import ctypes
            drive_type = ctypes.windll.kernel32.GetDriveTypeW(f"{letter}:\\")
            if drive_type == 2:  # DRIVE_REMOVABLE
                vol = Path(f"{letter}:\\")
                if vol.exists():
                    # Check for boot_out.txt (CircuitPython marker)
                    if (vol / "boot_out.txt").exists() or (vol / "code.py").exists():
                        return f"{letter}:"
        except Exception:
            pass
    return None


# ── List Backups & Bundles ────────────────────────────────────────────────

def list_backups() -> List[Dict]:
    backups = []
    if BACKUPS_DIR.exists():
        for d in sorted(BACKUPS_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if d.is_dir():
                backups.append({
                    "name": d.name,
                    "path": str(d),
                    "size_kb": round(sum(f.stat().st_size for f in d.rglob("*") if f.is_file()) / 1024, 1),
                    "created": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(d.stat().st_mtime)),
                })
    return backups

def list_bundles() -> List[Dict]:
    bundles = []
    if BUNDLES_DIR.exists():
        for d in sorted(BUNDLES_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if d.is_dir():
                zf = BUNDLES_DIR / f"{d.name}.zip"
                bundles.append({
                    "id": d.name,
                    "platform": d.name.split("-")[-2] if "-" in d.name else "unknown",
                    "size_kb": round(sum(f.stat().st_size for f in d.rglob("*") if f.is_file()) / 1024, 1),
                    "has_zip": zf.exists(),
                    "created": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(d.stat().st_mtime)),
                })
    return sorted(bundles, key=lambda b: b["created"], reverse=True)
