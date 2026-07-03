"""Flash Pipeline — detect device, select firmware, flash via platform method."""
from __future__ import annotations
import json, os, shutil, subprocess, time, zipfile
from pathlib import Path
from typing import Any, Dict, Optional

REPO = Path(__file__).resolve().parents[2]
FIRMWARE_DIR = REPO / "firmware"
DATA_DIR = REPO / "backend" / "data"
PREPARED_DIR = DATA_DIR / "firmware_prepared"

PLATFORM_PROFILES = {
    "circuitpython": {
        "name": "CircuitPython Control Bundle", "families": ["circuitpython","rp2040","rp2350","nrf","microchip"],
        "firmware_source": "circuitpython-agent", "main_file": "code.py",
        "flash_method": "usb-mass-storage", "flash_instructions": "Copy code.py to CIRCUITPY drive",
    },
    "micropython-esp32": {
        "name": "ESP32 MicroPython Agent", "families": ["esp32","esp32-s2","esp32-s3","esp32-c3","esp32-c6","esp32-h2","esp32-p4","esp8266"],
        "firmware_source": "esp32-agent", "main_file": "main.py",
        "flash_method": "serial", "flash_instructions": "mpremote connect {port} fs cp main.py :main.py",
    },
    "linux": {
        "name": "Linux Edge Agent", "families": ["rpi-sbc","rockchip","allwinner","nvidia","coral","movidius","qualcomm"],
        "firmware_source": "linux-agent", "main_file": "npu-agent.py",
        "flash_method": "scp", "flash_instructions": "scp npu-agent.py root@{host}:/usr/local/bin/",
    },
}

def detect_platform(device: Dict[str, Any]) -> Optional[str]:
    family = (device.get("family") or "").lower(); chip = (device.get("chip") or "").lower(); desc = (device.get("description") or "").lower()
    for pid, prof in PLATFORM_PROFILES.items():
        if family in [f.lower() for f in prof["families"]]: return pid
        if any(f in chip or f in desc for f in [f.lower() for f in prof["families"]]): return pid
    if "circuitpy" in desc or "bootsel" in desc: return "circuitpython"
    if any(c in chip for c in ["esp32","esp8266"]): return "micropython-esp32"
    if device.get("connection") == "network": return "linux"
    return None

def prepare_bundle(device_id: str, profile_id: Optional[str] = None, wifi_ssid: str = "", wifi_pass: str = "", mqtt_broker: str = "127.0.0.1") -> Dict[str, Any]:
    PREPARED_DIR.mkdir(parents=True, exist_ok=True)
    if not profile_id: profile_id = "circuitpython"
    if profile_id not in PLATFORM_PROFILES: return {"success": False, "error": f"Unknown profile: {profile_id}"}
    prof = PLATFORM_PROFILES[profile_id]; src = FIRMWARE_DIR / prof["firmware_source"]
    if not src.exists(): return {"success": False, "error": f"Firmware not found: {src}"}
    ts = time.strftime("%Y%m%d-%H%M%S"); name = f"{device_id}-{profile_id}-{ts}"
    bundle_dir = PREPARED_DIR / name; bundle_dir.mkdir(parents=True, exist_ok=True)
    files = []
    for f in src.iterdir():
        if f.is_file(): shutil.copy2(f, bundle_dir / f.name); files.append(f.name)
    cfg = {"device_id": device_id, "mqtt_broker": mqtt_broker, "mqtt_port": 1883}
    if wifi_ssid: cfg["wifi_ssid"] = wifi_ssid
    if wifi_pass: cfg["wifi_password"] = wifi_pass
    (bundle_dir / "npu_config.json").write_text(json.dumps(cfg, indent=2))
    (bundle_dir / "README.txt").write_text(f"NPU-STACK Bundle\nDevice: {device_id}\nPlatform: {prof['name']}\nFlash: {prof['flash_instructions'].format(main_file=prof['main_file'], port='COMx', host='ip')}\n")
    zip_path = PREPARED_DIR / f"{name}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, fls in os.walk(bundle_dir):
            for fl in fls: zf.write(Path(root)/fl, fl)
    return {"success": True, "bundle_id": name, "bundle_dir": str(bundle_dir), "zip_path": str(zip_path),
            "download_url": f"/api/flash/download/{name}.zip", "profile": prof["name"],
            "flash_method": prof["flash_method"], "files": files}

def flash_uf2(bundle_dir: Path, drive: str = "D:") -> Dict[str, Any]:
    try:
        tgt = Path(f"{drive}/")
        if not tgt.exists(): return {"success": False, "error": f"Drive {drive}: not found"}
        for f in ["code.py","npu_config.json"]:
            srcf = bundle_dir / f
            if srcf.exists(): shutil.copy2(srcf, tgt / f)
        return {"success": True, "output": f"Copied to {drive}:"}
    except Exception as e: return {"success": False, "error": str(e)}

def flash_esptool(bundle_dir: Path, port: str = "COM3") -> Dict[str, Any]:
    try:
        for f in ["main.py","npu_config.json"]:
            srcf = bundle_dir / f
            if srcf.exists():
                r = subprocess.run(["mpremote","connect",port,"fs","cp",str(srcf),f":{f}"], capture_output=True, text=True, timeout=30)
                if r.returncode != 0:
                    r2 = subprocess.run(["ampy","--port",port,"put",str(srcf),f], capture_output=True, text=True, timeout=30)
                    if r2.returncode != 0: return {"success": False, "error": r2.stderr or r.stderr}
        return {"success": True, "output": f"Flashed to {port}"}
    except Exception as e: return {"success": False, "error": str(e)}

def list_bundles() -> list:
    bundles = []
    for d in sorted(PREPARED_DIR.glob("*"), reverse=True):
        if d.is_dir():
            zf = PREPARED_DIR / f"{d.name}.zip"
            bundles.append({"id": d.name, "created": d.stat().st_mtime, "has_zip": zf.exists(),
                           "size_kb": round(sum(f.stat().st_size for f in d.rglob("*") if f.is_file())/1024, 1)})
    return bundles
