"""NPU-STACK Device Identity — identify boards from VID:PID + USB descriptors.

No PowerShell — uses pyserial (COM port hwid contains VID:PID) + libusb.
Architecture: xtensa-lx7, arm-cortex-m0, risc-v, bridge-chip
"""
from __future__ import annotations

import json, os, re, time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parents[2]
IDENTITY_CACHE = REPO / "backend" / "data" / "device_identity_cache.json"

# ── Known Board Identity Database (VID, PID) ──────────────────────────────

KNOWN_IDENTITIES: Dict[Tuple[str, str], Dict[str, Any]] = {
    # ── Espressif ──
    ("303A", "1001"): {
        "chip": "ESP32-S3", "vendor": "Espressif", "family": "esp32-s3",
        "architecture": "xtensa-lx7", "board": "ESP32-S3 DevKit / Matrix",
        "npu": False, "flash_mb": 16, "psram_mb": 8, "flash_method": "esptool",
    },
    ("303A", "4001"): {
        "chip": "ESP32-S3/P4 CDC", "vendor": "Espressif", "family": "esp32-s3",
        "architecture": "xtensa-lx7", "board": "ESP32-S3 CDC Device",
        "npu": False, "flash_mb": 16, "flash_method": "esptool",
        "notes": "CDC serial — could be S3 Matrix, P4, or XIAO Sense",
    },
    # ── Adafruit ──
    ("239A", "8018"): {
        "chip": "SAMD21G18", "vendor": "Adafruit", "family": "circuitpython",
        "architecture": "arm-cortex-m0", "board": "Circuit Playground Express",
        "npu": False, "flash_mb": 2, "flash_method": "uf2",
        "features": ["neopixel", "accelerometer", "mic", "speaker", "IR"],
    },
    ("239A", "8019"): {
        "chip": "SAMD21G18", "vendor": "Adafruit", "family": "circuitpython",
        "architecture": "arm-cortex-m0", "board": "Feather M0 Express", "npu": False, "flash_method": "uf2",
    },
    ("239A", "80EB"): {
        "chip": "RP2040", "vendor": "Adafruit", "family": "rp2040",
        "architecture": "arm-cortex-m0+", "board": "QT Py RP2040", "npu": False, "flash_method": "uf2",
    },
    # ── Seeed XIAO ──
    ("2886", "0058"): {
        "chip": "ESP32-S3", "vendor": "Seeed Studio", "family": "seeed-xiao",
        "architecture": "xtensa-lx7", "board": "XIAO ESP32-S3", "npu": False, "flash_method": "esptool",
    },
    ("2886", "0056"): {
        "chip": "ESP32-C3", "vendor": "Seeed Studio", "family": "seeed-xiao",
        "architecture": "risc-v", "board": "XIAO ESP32-C3", "npu": False, "flash_method": "esptool",
    },
    ("2886", "002F"): {
        "chip": "RP2040", "vendor": "Seeed Studio", "family": "seeed-xiao",
        "architecture": "arm-cortex-m0+", "board": "XIAO RP2040", "npu": False, "flash_method": "uf2",
    },
    # ── Microchip bridge ──
    ("04D8", "00DD"): {
        "chip": "MCP2221", "vendor": "Microchip", "family": "bridge",
        "architecture": "bridge-chip", "board": "MCP2221 USB-I2C/UART (GPS)", "npu": False, "flash_method": "none",
    },
    # ── WCH bridge chips ──
    ("1A86", "7523"): {
        "chip": "CH340", "vendor": "WCH", "family": "bridge",
        "architecture": "bridge-chip", "board": "CH340 UART Bridge", "npu": False, "flash_method": "none",
    },
    ("1A86", "55D3"): {
        "chip": "CH343", "vendor": "WCH", "family": "bridge",
        "architecture": "bridge-chip", "board": "CH343 (Grove Vision V2)", "npu": False, "flash_method": "none",
    },
    ("1A86", "7522"): {
        "chip": "CH340K", "vendor": "WCH", "family": "bridge",
        "architecture": "bridge-chip", "board": "CH340K UART Bridge (ESP32 board)", "npu": False, "flash_method": "none",
        "notes": "CH340K is typically on ESP32 dev boards — check serial output for chip ID. If ESP32-S3 ROM boot msg seen, board behind this bridge is an ESP32-S3.",
    },
    # ── Arduino ──
    ("2341", "0074"): {
        "chip": "SAMD21G18", "vendor": "Arduino", "family": "arduino",
        "architecture": "arm-cortex-m0", "board": "Arduino Nano R4",
        "npu": False, "flash_mb": 0, "flash_method": "arduino-ide",
    },
    ("2341", "0043"): {
        "chip": "ATmega328P", "vendor": "Arduino", "family": "arduino",
        "architecture": "avr", "board": "Arduino Uno R3", "npu": False, "flash_method": "arduino-ide",
    },
    # ── Waveshare S3 Matrix (same VID as Espressif, identified by serial pattern) ──
    ("303A", "4001-MATRIX"): {  # Special key: VID-PID serial when "123456" detected
        "chip": "ESP32-S3", "vendor": "Waveshare", "family": "esp32-s3",
        "architecture": "xtensa-lx7", "board": "ESP32-S3 Matrix (Waveshare)",
        "npu": False, "flash_mb": 16, "psram_mb": 8, "flash_method": "esptool",
        "features": ["neopixel-25xWS2812", "accelerometer", "gyroscope"],
        "neopixel_pin": 21, "neopixel_count": 25,
        "notes": "Serial 123456 = Waveshare S3 Matrix. CDC port is MicroPython, CH340K port shows boot ROM.",
    },
    # ── Rockchip ──
    ("2207", "110C"): {
        "chip": "RV1106", "vendor": "Rockchip/LuckFox", "family": "rockchip",
        "architecture": "arm-cortex-a7", "board": "LuckFox Pico Pro/Ultra",
        "npu": True, "npu_tops": 1.0, "flash_method": "rkdeveloptool",
    },
    ("2207", "110B"): {
        "chip": "RV1103", "vendor": "Rockchip/LuckFox", "family": "rockchip",
        "architecture": "arm-cortex-a7", "board": "LuckFox Pico",
        "npu": True, "npu_tops": 0.5, "flash_method": "rkdeveloptool",
    },
    # ── Dell LTE modems (not fleet) ──
    ("413C", "81BC"): {
        "chip": "Qualcomm", "vendor": "Dell", "family": "lte-modem",
        "architecture": "arm", "board": "DW5814e LTE", "npu": False, "flash_method": "none",
    },
    ("413C", "81C5"): {
        "chip": "Qualcomm", "vendor": "Dell", "family": "lte-modem",
        "architecture": "arm", "board": "DW5814e LTE", "npu": False, "flash_method": "none",
    },
}

# ── Architecture → Template ───────────────────────────────────────────────

ARCHITECTURES = {
    "xtensa-lx7":     {"label": "ESP32",         "group": "esp32",    "template": "micropython-esp32"},
    "arm-cortex-m0":  {"label": "ARM Cortex-M0",  "group": "arm-mcu", "template": "circuitpython"},
    "arm-cortex-m0+": {"label": "ARM Cortex-M0+", "group": "arm-mcu", "template": "circuitpython"},
    "arm-cortex-m55": {"label": "ARM Cortex-M55", "group": "arm-mcu", "template": "circuitpython"},
    "arm-cortex-a7":  {"label": "ARM Cortex-A7",  "group": "arm-linux","template": "linux-sbc"},
    "arm-cortex-a53": {"label": "ARM Cortex-A53", "group": "arm-linux","template": "linux-sbc"},
    "risc-v":         {"label": "RISC-V",         "group": "risc-v",  "template": "micropython-esp32"},
    "bridge-chip":    {"label": "Bridge Chip",    "group": "bridge",  "template": None},
    "arm":            {"label": "ARM",            "group": "arm",     "template": "linux-sbc"},
    "avr":            {"label": "AVR ATmega",   "group": "avr",     "template": None},
}


# ── Identification ────────────────────────────────────────────────────────

def identify_all_devices() -> List[Dict[str, Any]]:
    """Identify all USB devices via pyserial + libusb. No PowerShell, no hangs."""
    devices, seen = [], set()
    import serial.tools.list_ports

    # Phase 1: pyserial COM ports (hwid field contains VID:PID)
    for p in serial.tools.list_ports.comports():
        if not p.vid:
            continue
        vid, pid = f"{p.vid:04X}", f"{p.pid:04X}"
        info = KNOWN_IDENTITIES.get((vid, pid), {}).copy()

        # ── Special detection: Waveshare S3 Matrix (serial "123456") ──
        if vid == "303A" and pid == "4001" and p.serial_number == "123456":
            info = KNOWN_IDENTITIES.get(("303A", "4001-MATRIX"), info).copy()

        # ── Special detection: CH340K with ESP32-S3 behind it ──
        if vid == "1A86" and pid == "7522":
            info["notes"] = info.get("notes", "") + " — probe serial output for chip ID (ESP32-S3 boot ROM detected)"

        if not info:
            info = {"family": "unknown", "architecture": "unknown", "board": p.description or "USB Device"}

        arch = info.get("architecture", "unknown")
        ai = ARCHITECTURES.get(arch, {"label": "Unknown", "group": "unknown", "template": None})
        did = f"{vid}{pid}-{p.device.replace(':','')[:8]}-{info.get('board','')[:20].lower().replace(' ','-')}"

        devices.append({
            "id": did, "port": p.device,
            "vid": f"0x{vid}", "pid": f"0x{pid}", "vidpid": f"{vid}:{pid}",
            "board": info.get("board", ""), "vendor": info.get("vendor", ""),
            "chip": info.get("chip", ""), "family": info.get("family", "unknown"),
            "architecture": arch, "architecture_label": ai.get("label", arch),
            "architecture_group": ai.get("group", "unknown"),
            "npu": info.get("npu", False), "npu_tops": info.get("npu_tops"),
            "flash_method": info.get("flash_method", "unknown"),
            "flash_mb": info.get("flash_mb"),
            "template": ai.get("template"),
            "serial": p.serial_number or "",
            "description": p.description or "",
            "features": info.get("features", []),
            "notes": info.get("notes", ""),
            "source": "pyserial",
        })
        seen.add((vid, pid))

    # Phase 2: libusb for devices without COM ports (Rockchip, Grove Vision)
    try:
        import ctypes, usb.backend.libusb1, usb.core
        DLL = r"C:\Windows\System32\libusb-1.0.dll"
        be = usb.backend.libusb1.get_backend(find_library=lambda x: DLL)
        if be:
            for d in usb.core.find(find_all=True, backend=be):
                vid, pid = f"{d.idVendor:04X}", f"{d.idProduct:04X}"
                key = (vid, pid)
                if key in seen or key not in KNOWN_IDENTITIES:
                    continue
                info = KNOWN_IDENTITIES[key]
                arch = info.get("architecture", "unknown")
                ai = ARCHITECTURES.get(arch, {"label": "Unknown", "group": "unknown", "template": None})
                did = f"{info.get('vendor','').lower().replace(' ','-')}-bus{d.bus}-addr{d.address}"
                devices.append({
                    "id": did, "port": str(d.port_numbers) if d.port_numbers else "",
                    "vid": f"0x{vid}", "pid": f"0x{pid}", "vidpid": f"{vid}:{pid}",
                    "board": info.get("board", ""), "vendor": info.get("vendor", ""),
                    "chip": info.get("chip", ""), "family": info.get("family", "unknown"),
                    "architecture": arch, "architecture_label": ai.get("label", arch),
                    "architecture_group": ai.get("group", "unknown"),
                    "npu": info.get("npu", False), "npu_tops": info.get("npu_tops"),
                    "flash_method": info.get("flash_method", "unknown"),
                    "template": ai.get("template"),
                    "source": "libusb", "notes": info.get("notes", ""),
                })
    except Exception:
        pass

    return sorted(devices, key=lambda d: (d.get("architecture_group", "z"), d.get("port", "")))


def get_architecture_summary() -> Dict[str, int]:
    groups = {}
    for d in identify_all_devices():
        g = d.get("architecture_group", "unknown")
        groups[g] = groups.get(g, 0) + 1
    return groups


def save_identity_cache():
    devices = identify_all_devices()
    data = {"scanned_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "devices": devices, "architecture_summary": get_architecture_summary()}
    IDENTITY_CACHE.parent.mkdir(parents=True, exist_ok=True)
    IDENTITY_CACHE.write_text(json.dumps(data, indent=2))
    return data
