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


# ── Baked-in Arduino toolchain (self-contained, no internet) ──────────────

ARDUINO_CLI = REPO / "tools" / "arduino" / "arduino-cli.exe"
ARDUINO_CONFIG = REPO / "tools" / "arduino" / "config.yaml"
ARDUINO_ENV = {**os.environ, "LC_ALL": "C", "LANG": "C"}  # avoid std::locale crash on Windows


def _arduino_cli_prefix() -> Optional[list]:
    """Resolve arduino-cli: the repo-vendored binary first, then system PATH."""
    if ARDUINO_CLI.exists():
        return [str(ARDUINO_CLI), "--config-file", str(ARDUINO_CONFIG)]
    cli = shutil.which("arduino-cli")
    return [cli] if cli else None


def flash_arduino_cli(sketch_dir: str, port: str = "", fqbn: str = "") -> Dict[str, Any]:
    """Compile + upload an Arduino sketch (e.g. AMB82-Mini) via arduino-cli.

    Prefers the repo-vendored arduino-cli + Realtek AmebaPro2 core/toolchain
    (tools/arduino/) so flashing works fully offline. Falls back to system
    arduino-cli, then to step-by-step instructions when neither is available.
    """
    cli_prefix = _arduino_cli_prefix()
    fqbn = fqbn or os.getenv("AMB82_FQBN", "realtek:AmebaPro2:Ameba_AMB82-MINI")
    sketch = Path(sketch_dir)

    if not cli_prefix:
        return {
            "success": False,
            "tool": "arduino-cli",
            "fqbn": fqbn,
            "error": "arduino-cli not found (vendored tools/arduino/arduino-cli.exe missing and not on PATH).",
            "instructions": [
                f"arduino-cli core install realtek:AmebaPro2",
                f"arduino-cli compile --fqbn {fqbn} {sketch_dir}",
                f"arduino-cli upload -p <port> --fqbn {fqbn} {sketch_dir}",
            ],
        }
    if not sketch.exists():
        return {"success": False, "tool": "arduino-cli", "error": f"Sketch not found: {sketch_dir}"}

    results = []
    try:
        compile_cmd = cli_prefix + ["compile", "--fqbn", fqbn, str(sketch)]
        r = subprocess.run(compile_cmd, capture_output=True, text=True, timeout=900, env=ARDUINO_ENV)
        results.append({
            "stage": "compile", "returncode": r.returncode,
            "stdout": (r.stdout or "")[-4000:], "stderr": (r.stderr or "")[-4000:],
        })
        if r.returncode != 0:
            return {"success": False, "tool": "arduino-cli", "fqbn": fqbn,
                    "results": results, "error": "compile failed"}

        upload_cmd = cli_prefix + ["upload", "--fqbn", fqbn]
        if port:
            upload_cmd += ["-p", port]
        upload_cmd.append(str(sketch))
        r2 = subprocess.run(upload_cmd, capture_output=True, text=True, timeout=900, env=ARDUINO_ENV)
        results.append({
            "stage": "upload", "returncode": r2.returncode,
            "stdout": (r2.stdout or "")[-4000:], "stderr": (r2.stderr or "")[-4000:],
        })
        if r2.returncode != 0:
            return {"success": False, "tool": "arduino-cli", "fqbn": fqbn,
                    "results": results, "error": "upload failed"}
        return {"success": True, "tool": "arduino-cli", "fqbn": fqbn,
                "port": port or "auto", "results": results}
    except Exception as e:
        return {"success": False, "tool": "arduino-cli", "fqbn": fqbn,
                "results": results, "error": str(e)}

def list_bundles() -> list:
    bundles = []
    for d in sorted(PREPARED_DIR.glob("*"), reverse=True):
        if d.is_dir():
            zf = PREPARED_DIR / f"{d.name}.zip"
            bundles.append({"id": d.name, "created": d.stat().st_mtime, "has_zip": zf.exists(),
                           "size_kb": round(sum(f.stat().st_size for f in d.rglob("*") if f.is_file())/1024, 1)})
    return bundles

# ── Firmware Detection & Backup ────────────────────────────────────────────

def detect_current_firmware(device_id: str, port: str = "") -> Dict[str, Any]:
    """Detect what firmware is currently on a device before flashing.

    For ESP32: reads chip info via esptool.
    For CircuitPython: reads boot_out.txt from drive.
    For Linux: returns current agent status.
    """
    info = {"device_id": device_id, "detected": False, "type": "unknown"}

    # Try ESP32 detection
    try:
        import serial.tools.list_ports
        ports = [p.device for p in serial.tools.list_ports.comports()]
        target = port or next((p for p in ports if "usb" in p.lower() or "com" in p.lower()), "")
        if target:
            result = subprocess.run(
                ["esptool.py", "--port", target, "chip_id"],
                capture_output=True, text=True, timeout=15
            )
            if result.returncode == 0:
                info["type"] = "esp32"
                info["port"] = target
                info["firmware_size_mb"] = 4  # default
                info["detected"] = True
                # Extract chip info
                for line in result.stdout.split("\n"):
                    if "Chip is" in line:
                        info["chip"] = line.split("Chip is")[-1].strip()
                    if "Features" in line:
                        info["features"] = line.strip()
                    if "MAC" in line:
                        info["mac"] = line.split("MAC:")[-1].strip()
                return info
    except Exception:
        pass

    # Try CircuitPython detection (check CIRCUITPY drive)
    for drive in ["D:", "E:", "F:", "G:", "H:"]:
        p = Path(f"{drive}/")
        boot_out = p / "boot_out.txt"
        if boot_out.exists():
            try:
                boot_text = boot_out.read_text()[:200]
                info["type"] = "circuitpython"
                info["drive"] = drive
                info["boot_out"] = boot_text
                info["detected"] = True
                # Check for existing code.py
                code_py = p / "code.py"
                if code_py.exists():
                    info["has_code_py"] = True
                    info["code_py_size"] = code_py.stat().st_size
                return info
            except:
                pass

    # Try Linux detection (check agent status)
    try:
        r = subprocess.run(
            ["ssh", f"root@{device_id}", "systemctl", "status", "npu-agent", "--no-pager"],
            capture_output=True, text=True, timeout=10
        )
        if r.returncode == 0 or "active" in r.stdout:
            info["type"] = "linux"
            info["detected"] = True
            info["agent_status"] = "active" if "active" in r.stdout else "unknown"
            return info
    except:
        pass

    return info


def backup_before_flash(device_id: str, port: str = "", flash_size_mb: int = 4) -> Dict[str, Any]:
    """Backup current firmware before flashing the NPU-STACK agent.

    Returns the backup path and metadata. Must be called BEFORE writing new firmware.
    """
    backup_dir = DATA_DIR / "firmware_backups" / device_id
    backup_dir.mkdir(parents=True, exist_ok=True)

    ts = time.strftime("%Y%m%d_%H%M%S")
    results = []

    # ── ESP32 backup via esptool ──
    if port:
        try:
            out = backup_dir / f"{device_id}_backup_{ts}.bin"
            size_hex = hex(flash_size_mb * 1024 * 1024)
            r = subprocess.run(
                ["esptool.py", "--port", port, "--baud", "460800", "read_flash", "0", size_hex, str(out)],
                capture_output=True, text=True, timeout=120
            )
            if r.returncode == 0 and out.exists():
                results.append({
                    "type": "esp32_flash_dump",
                    "file": str(out),
                    "size_mb": round(out.stat().st_size / (1024 * 1024), 2),
                })
        except Exception as e:
            results.append({"type": "esp32_flash_dump", "error": str(e)})

    # ── CircuitPython backup (copy existing code.py + boot_out.txt) ──
    for drive in ["D:", "E:", "F:", "G:", "H:"]:
        drive_path = Path(f"{drive}/")
        boot_out = drive_path / "boot_out.txt"
        if boot_out.exists():
            cp_dir = backup_dir / f"circuitpython_{ts}"
            cp_dir.mkdir(parents=True, exist_ok=True)
            files_backed = []
            for fname in ["code.py", "boot_out.txt", "boot.py", "npu_config.json"]:
                src = drive_path / fname
                if src.exists():
                    shutil.copy2(src, cp_dir / fname)
                    files_backed.append(fname)
            if files_backed:
                results.append({
                    "type": "circuitpython_files",
                    "dir": str(cp_dir),
                    "files": files_backed,
                    "drive": drive,
                })
            break

    if results:
        manifest = {"device_id": device_id, "backed_up_at": ts, "results": results}
        (backup_dir / f"manifest_{ts}.json").write_text(json.dumps(manifest, indent=2))
        return {"success": True, "backups": results, "backup_dir": str(backup_dir)}
    else:
        return {"success": False, "note": "No firmware to backup (empty/new device?)", "backup_dir": str(backup_dir)}


def firmware_flash_workflow(device_id: str, port: str = "", profile_id: str = "circuitpython",
                             wifi_ssid: str = "", wifi_pass: str = "",
                             backup_first: bool = True) -> Dict[str, Any]:
    """Complete flash workflow: detect → backup → prepare → flash.

    This is the single endpoint the frontend calls for the full user experience.
    """
    steps = []

    # Step 0: Detect current firmware
    detect = detect_current_firmware(device_id, port)
    steps.append({"step": "detect", "result": detect})

    # Step 1: Backup if requested and firmware exists
    if backup_first and detect.get("detected"):
        backup = backup_before_flash(device_id, port)
        steps.append({"step": "backup", "result": backup})
    else:
        steps.append({"step": "backup", "result": {"skipped": True, "reason": "Not detected or backup disabled"}})

    # Step 2: Prepare bundle
    bundle = prepare_bundle(device_id, profile_id, wifi_ssid, wifi_pass)
    steps.append({"step": "prepare", "result": bundle})

    # Step 3: Flash
    flash_result = None
    if bundle.get("success"):
        flash_method = bundle.get("flash_method", "")
        bundle_dir = Path(bundle["bundle_dir"])
        if flash_method == "usb-mass-storage":
            drive = detect.get("drive", "D:")
            flash_result = flash_uf2(bundle_dir, drive)
        elif flash_method == "serial":
            flash_result = flash_esptool(bundle_dir, port or "COM3")
        else:
            flash_result = {"success": False, "error": f"Unsupported flash method: {flash_method}"}
        steps.append({"step": "flash", "result": flash_result})
    else:
        steps.append({"step": "flash", "result": {"error": "Bundle preparation failed"}})

    success = flash_result.get("success", False) if flash_result else False
    return {
        "device_id": device_id,
        "success": success,
        "steps": steps,
        "next": "Device will reboot with NPU-STACK agent. Check /api/fleet for status." if success else "Check errors above.",
    }

# ── Backward-compat stubs for edge_discovery.py ────────────────────────────

def flash_tools_available() -> dict:
    """Check which flashing tools are available on this system."""
    tools = {}
    for tool in ["esptool.py", "esptool", "mpremote", "ampy", "arduino-cli", "rkdeveloptool", "upgrade_tool"]:
        tools[tool] = bool(__import__("shutil").which(tool))
    return tools

def rk_detect_device() -> dict:
    return {"detected": False, "note": "rkdeveloptool not configured"}

def rk_read_flash_id() -> dict:
    return {"error": "rkdeveloptool not configured"}

def rk_read_flash(offset: int = 0, count: int = 1) -> dict:
    return {"error": "rkdeveloptool not configured"}

def rk_write_flash(offset: int = 0, path: str = "") -> dict:
    return {"error": "rkdeveloptool not configured"}

def rk_reset_device() -> dict:
    return {"error": "rkdeveloptool not configured"}
