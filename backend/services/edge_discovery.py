"""Edge Fleet discovery, registry, and firmware preparation helpers.

This module powers the existing `/api/devices` routes and intentionally extends
the current NPU-STACK edge-device system instead of introducing a parallel
fleet subsystem.
"""

import asyncio
import ipaddress
import json
import logging
import os
import platform
import re
import shutil
import ssl
import subprocess
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from backend.services import flash_service

logger = logging.getLogger(__name__)


# ── Paths ────────────────────────────────────────────────────────

BACKEND_ROOT = Path(os.path.dirname(os.path.dirname(__file__)))
DATA_DIR = BACKEND_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

REPO_ROOT = BACKEND_ROOT.parent
FIRMWARE_ASSETS_DIR = REPO_ROOT / "firmware"

FIRMWARE_DIR = DATA_DIR / "firmware_backups"
FIRMWARE_DIR.mkdir(parents=True, exist_ok=True)

PREPARED_DIR = DATA_DIR / "firmware_prepared"
PREPARED_DIR.mkdir(parents=True, exist_ok=True)

REGISTRY_FILE = DATA_DIR / "edge_device_registry.json"


# ── Well-known USB VID:PID mappings ──────────────────────────────

USB_DEVICE_MAP = {
    # ── Espressif native USB ──
    (0x303A, 0x1001): {"family": "esp32-s2", "chip": "ESP32-S2", "npu": False, "flash_mb": 4},
    (0x303A, 0x1002): {"family": "esp32-s3", "chip": "ESP32-S3", "npu": False, "flash_mb": 16},
    (0x303A, 0x0002): {"family": "esp32-s3", "chip": "ESP32-S3 (JTAG)", "npu": False, "flash_mb": 16},
    (0x303A, 0x0003): {"family": "esp32-c3", "chip": "ESP32-C3", "npu": False, "flash_mb": 4},
    (0x303A, 0x1003): {"family": "esp32-c3", "chip": "ESP32-C3", "npu": False, "flash_mb": 4},
    (0x303A, 0x1004): {"family": "esp32-c6", "chip": "ESP32-C6", "npu": False, "flash_mb": 4},
    # 0x4001 is the MicroPython/TinyUSB REPL descriptor for ESP32-S3 (verified
    # on a Seeed XIAO ESP32-S3 Sense running Nirvana OS).
    (0x303A, 0x4001): {"family": "esp32-s3", "chip": "ESP32-S3", "npu": False, "flash_mb": 8},
    (0x303A, 0x0010): {"family": "esp32-h2", "chip": "ESP32-H2", "npu": False, "flash_mb": 4},
    # ── UART bridge chips ──
    (0x10C4, 0xEA60): {"family": "uart-bridge", "chip": "Silicon Labs CP210x", "npu": False, "flash_mb": 0},
    (0x10C4, 0xEA70): {"family": "uart-bridge", "chip": "Silicon Labs CP2105", "npu": False, "flash_mb": 0},
    (0x1A86, 0x7523): {"family": "uart-bridge", "chip": "WCH CH340", "npu": False, "flash_mb": 0},
    (0x1A86, 0x55D4): {"family": "uart-bridge", "chip": "WCH CH9102", "npu": False, "flash_mb": 0},
    (0x1A86, 0x55D3): {"family": "grove-vision", "chip": "Grove Vision AI V2 (WiseEye2)", "npu": True, "flash_mb": 0},
    (0x1A86, 0x55D3): {"family": "uart-bridge", "chip": "WCH CH9102F", "npu": False, "flash_mb": 0},
    (0x1A86, 0x7522): {"family": "uart-bridge", "chip": "WCH CH341", "npu": False, "flash_mb": 0},
    (0x0403, 0x6001): {"family": "uart-bridge", "chip": "FTDI FT232R", "npu": False, "flash_mb": 0},
    (0x0403, 0x6010): {"family": "uart-bridge", "chip": "FTDI FT2232H", "npu": False, "flash_mb": 0},
    (0x0403, 0x6011): {"family": "uart-bridge", "chip": "FTDI FT4232H", "npu": False, "flash_mb": 0},
    (0x0403, 0x6014): {"family": "uart-bridge", "chip": "FTDI FT232H", "npu": False, "flash_mb": 0},
    (0x0403, 0x6015): {"family": "uart-bridge", "chip": "FTDI FT231X", "npu": False, "flash_mb": 0},
    (0x067B, 0x2303): {"family": "uart-bridge", "chip": "Prolific PL2303", "npu": False, "flash_mb": 0},
    (0x067B, 0x23A3): {"family": "uart-bridge", "chip": "Prolific PL2303GS", "npu": False, "flash_mb": 0},
    # ── Raspberry Pi / RP2040 ──
    (0x2E8A, 0x0003): {"family": "rp2040", "chip": "RP2040 (Pico)", "npu": False, "flash_mb": 2},
    (0x2E8A, 0x0005): {"family": "rp2040", "chip": "RP2040 (Pico)", "npu": False, "flash_mb": 2},
    (0x2E8A, 0x000A): {"family": "rp2040", "chip": "RP2040 (CDC)", "npu": False, "flash_mb": 2},
    (0x2E8A, 0x000F): {"family": "rp2350", "chip": "RP2350 (Pico 2)", "npu": False, "flash_mb": 4},
    (0x2E8A, 0x0004): {"family": "rp2040", "chip": "RP2040 (MicroPython)", "npu": False, "flash_mb": 2},
    (0x2E8A, 0x0009): {"family": "rp2040", "chip": "RP2040 (CircuitPython)", "npu": False, "flash_mb": 2},
    # ── Arduino ──
    (0x2341, 0x0043): {"family": "arduino", "chip": "Arduino Uno R3", "npu": False, "flash_mb": 0},
    (0x2341, 0x0001): {"family": "arduino", "chip": "Arduino Uno", "npu": False, "flash_mb": 0},
    (0x2341, 0x0010): {"family": "arduino", "chip": "Arduino Mega 2560", "npu": False, "flash_mb": 0},
    (0x2341, 0x003D): {"family": "arduino", "chip": "Arduino Due", "npu": False, "flash_mb": 0},
    (0x2341, 0x8036): {"family": "arduino", "chip": "Arduino Leonardo", "npu": False, "flash_mb": 0},
    (0x2341, 0x804E): {"family": "arduino", "chip": "Arduino Nano RP2040", "npu": False, "flash_mb": 2},
    (0x2341, 0x0058): {"family": "arduino", "chip": "Arduino Nano ESP32", "npu": False, "flash_mb": 16},
    (0x2341, 0x0070): {"family": "arduino", "chip": "Arduino Uno R4", "npu": False, "flash_mb": 0},
    # ── STMicroelectronics ──
    (0x0483, 0x5740): {"family": "stm32", "chip": "STM32 VCP", "npu": False, "flash_mb": 0},
    (0x0483, 0x3748): {"family": "stm32", "chip": "ST-Link V2", "npu": False, "flash_mb": 0},
    (0x0483, 0x374B): {"family": "stm32", "chip": "ST-Link V2-1", "npu": False, "flash_mb": 0},
    (0x0483, 0x374E): {"family": "stm32", "chip": "ST-Link V3", "npu": False, "flash_mb": 0},
    (0x0483, 0xDF11): {"family": "stm32", "chip": "STM32 DFU Bootloader", "npu": False, "flash_mb": 0},
    # ── Nordic ──
    (0x1915, 0x520F): {"family": "nrf", "chip": "nRF52840 Dongle", "npu": False, "flash_mb": 1},
    (0x1915, 0x521F): {"family": "nrf", "chip": "nRF52833 DK", "npu": False, "flash_mb": 0},
    (0x1915, 0xCAFE): {"family": "nrf", "chip": "nRF52 (UF2 Boot)", "npu": False, "flash_mb": 1},
    (0x1366, 0x0105): {"family": "nrf", "chip": "J-Link (SEGGER)", "npu": False, "flash_mb": 0},
    (0x1366, 0x1015): {"family": "nrf", "chip": "J-Link OB", "npu": False, "flash_mb": 0},
    # ── Adafruit / CircuitPython ──
    (0x239A, 0x8018): {"family": "circuitpython", "chip": "Adafruit CircuitPython Board", "npu": False, "flash_mb": 0},
    (0x239A, 0x8019): {"family": "circuitpython", "chip": "Adafruit Feather M0", "npu": False, "flash_mb": 0},
    (0x239A, 0x80CB): {"family": "circuitpython", "chip": "Adafruit QT Py ESP32-S2", "npu": False, "flash_mb": 4},
    (0x239A, 0x8120): {"family": "circuitpython", "chip": "Adafruit Feather ESP32-S3", "npu": False, "flash_mb": 16},
    (0x239A, 0x80EB): {"family": "circuitpython", "chip": "Adafruit QT Py RP2040", "npu": False, "flash_mb": 2},
    # ── Microchip / SAMD family ──
    (0x04D8, 0x00DD): {"family": "microchip", "chip": "Microchip USB Device", "npu": False, "flash_mb": 0},
    # ── Teensy ──
    (0x16C0, 0x0483): {"family": "teensy", "chip": "Teensy (Serial)", "npu": False, "flash_mb": 0},
    (0x16C0, 0x0478): {"family": "teensy", "chip": "Teensy (HalfKay Boot)", "npu": False, "flash_mb": 0},
    # ── Seeed Studio XIAO ──
    (0x2886, 0x002D): {"family": "seeed-xiao", "chip": "Seeed XIAO SAMD21", "npu": False, "flash_mb": 0},
    (0x2886, 0x002F): {"family": "seeed-xiao", "chip": "Seeed XIAO RP2040", "npu": False, "flash_mb": 2},
    (0x2886, 0x0042): {"family": "seeed-xiao", "chip": "Seeed XIAO nRF52840", "npu": False, "flash_mb": 2},
    (0x2886, 0x0054): {"family": "seeed-xiao", "chip": "Seeed XIAO nRF52840 Sense", "npu": False, "flash_mb": 2},
    (0x2886, 0x0056): {"family": "seeed-xiao", "chip": "Seeed XIAO ESP32-C3", "npu": False, "flash_mb": 4},
    (0x2886, 0x0058): {"family": "seeed-xiao", "chip": "Seeed XIAO ESP32-S3", "npu": False, "flash_mb": 8},
    (0x2886, 0x005A): {"family": "seeed-xiao", "chip": "Seeed XIAO ESP32-S3 Sense", "npu": False, "flash_mb": 8},
    (0x2886, 0x0004): {"family": "seeed-xiao", "chip": "Seeed XIAO (UF2 Boot)", "npu": False, "flash_mb": 2},
    (0x2886, 0x8020): {"family": "seeed-xiao", "chip": "Seeed XIAO (CircuitPython)", "npu": False, "flash_mb": 2},
    # ── M5Stack ──
    (0x303A, 0x80C5): {"family": "esp32-s3", "chip": "M5Stack CoreS3", "npu": False, "flash_mb": 16},
    (0x303A, 0x8002): {"family": "esp32", "chip": "M5Stack Core2", "npu": False, "flash_mb": 16},
    (0x303A, 0x80EE): {"family": "esp32-s3", "chip": "M5Stack Atom S3", "npu": False, "flash_mb": 8},
    (0x303A, 0x80F5): {"family": "esp32-s3", "chip": "M5Stack Stamp S3", "npu": False, "flash_mb": 8},
    (0x303A, 0x80F0): {"family": "esp32-s3", "chip": "M5Stack Cardputer", "npu": False, "flash_mb": 8},
    # ── Adafruit (expanded) ──
    (0x239A, 0x80E8): {"family": "circuitpython", "chip": "Adafruit Feather ESP32-S3 TFT", "npu": False, "flash_mb": 16},
    (0x239A, 0x8118): {"family": "circuitpython", "chip": "Adafruit Matrix Portal S3", "npu": False, "flash_mb": 16},
    (0x239A, 0x80F4): {"family": "circuitpython", "chip": "Adafruit QT Py ESP32-C3", "npu": False, "flash_mb": 4},
    (0x239A, 0x80D6): {"family": "circuitpython", "chip": "Adafruit Feather RP2040", "npu": False, "flash_mb": 8},
    (0x239A, 0x80F1): {"family": "circuitpython", "chip": "Adafruit Feather nRF52840", "npu": False, "flash_mb": 1},
    (0x239A, 0x8136): {"family": "circuitpython", "chip": "Adafruit Metro ESP32-S3", "npu": False, "flash_mb": 16},
    # ── LilyGO / TTGO ──
    (0x1A86, 0x55D4): {"family": "uart-bridge", "chip": "LilyGO T-Display (CH9102)", "npu": False, "flash_mb": 0},
    # ── Waveshare ──
    (0x2E8A, 0x1011): {"family": "rp2040", "chip": "Waveshare RP2040-Zero", "npu": False, "flash_mb": 2},
    (0x2E8A, 0x1033): {"family": "rp2040", "chip": "Waveshare RP2040-Plus", "npu": False, "flash_mb": 16},
    # ── Linux / accelerator boards ──
    (0x2207, 0x0011): {"family": "rockchip", "chip": "Rockchip Maskrom", "npu": True, "flash_mb": 0},
    (0x2207, 0x350A): {"family": "rockchip", "chip": "RK3588 (Loader)", "npu": True, "flash_mb": 0},
    (0x2207, 0x350B): {"family": "rockchip", "chip": "RK3588S (Loader)", "npu": True, "flash_mb": 0},
    (0x2207, 0x330C): {"family": "rockchip", "chip": "RK3308 (LuckFox)", "npu": False, "flash_mb": 0},
    (0x2207, 0x110B): {"family": "rockchip", "chip": "RV1103 (LuckFox Pico)", "npu": True, "flash_mb": 0},
    (0x2207, 0x110C): {"family": "rockchip", "chip": "RV1106 (LuckFox Pico+)", "npu": True, "flash_mb": 0},
    (0x2207, 0x350D): {"family": "rockchip", "chip": "RK3562", "npu": True, "flash_mb": 0},
    (0x1F3A, 0xEFE8): {"family": "allwinner", "chip": "Allwinner FEL", "npu": False, "flash_mb": 0},
    (0x1A6E, 0x089A): {"family": "coral", "chip": "Google Coral USB", "npu": True, "flash_mb": 0},
    (0x18D1, 0x9302): {"family": "coral", "chip": "Google Coral (DFU)", "npu": True, "flash_mb": 0},
    (0x03E7, 0x2485): {"family": "movidius", "chip": "Intel Movidius NCS2", "npu": True, "flash_mb": 0},
    (0x05C6, 0x9008): {"family": "qualcomm", "chip": "Qualcomm EDL", "npu": False, "flash_mb": 0},
}

USB_VID_MAP = {
    0x303A: {"family": "esp32", "vendor": "Espressif"},
    0x10C4: {"family": "uart-bridge", "vendor": "Silicon Labs"},
    0x1A86: {"family": "uart-bridge", "vendor": "WCH"},
    0x0403: {"family": "uart-bridge", "vendor": "FTDI"},
    0x067B: {"family": "uart-bridge", "vendor": "Prolific"},
    0x2E8A: {"family": "rp2040", "vendor": "Raspberry Pi"},
    0x2341: {"family": "arduino", "vendor": "Arduino"},
    0x0483: {"family": "stm32", "vendor": "STMicroelectronics"},
    0x04D8: {"family": "microchip", "vendor": "Microchip"},
    0x1915: {"family": "nrf", "vendor": "Nordic Semiconductor"},
    0x1366: {"family": "nrf", "vendor": "SEGGER"},
    0x239A: {"family": "circuitpython", "vendor": "Adafruit"},
    0x16C0: {"family": "teensy", "vendor": "Teensy/PJRC"},
    0x2886: {"family": "seeed-xiao", "vendor": "Seeed Studio"},
    0x2207: {"family": "rockchip", "vendor": "Rockchip"},
    0x1F3A: {"family": "allwinner", "vendor": "Allwinner"},
    0x1A6E: {"family": "coral", "vendor": "Google"},
    0x18D1: {"family": "google", "vendor": "Google"},
    0x03E7: {"family": "movidius", "vendor": "Intel Movidius"},
    0x05C6: {"family": "qualcomm", "vendor": "Qualcomm"},
}

_HEURISTIC_RULES = [
    (["esp32-s3"], "esp32-s3", "ESP32-S3"),
    (["esp32-s2"], "esp32-s2", "ESP32-S2"),
    (["esp32-c3"], "esp32-c3", "ESP32-C3"),
    (["esp32-c6"], "esp32-c6", "ESP32-C6"),
    (["esp32-h2"], "esp32-h2", "ESP32-H2"),
    (["esp32"], "esp32", "ESP32"),
    (["esp8266", "nodemcu"], "esp8266", "ESP8266"),
    (["esphome"], "esp32", "ESPHome Node"),
    (["wled"], "esp32", "WLED Controller"),
    (["tasmota"], "esp8266", "Tasmota Device"),
    (["micropython"], "esp32", "MicroPython Device"),
    (["circuitpython"], "circuitpython", "CircuitPython Device"),
    (["luckfox"], "rockchip", "LuckFox Pico"),
    (["rv1103", "rv1106"], "rockchip", "LuckFox Pico"),
    (["rockchip", "rk3588", "rk3588s", "rk3576", "rk3568", "rk3566", "rk3562", "radxa", "friendlyelec", "firefly"], "rockchip", "Rockchip SoC"),
    (["rp2040", "pico"], "rp2040", "RP2040"),
    (["rp2350", "pico 2", "pico2"], "rp2350", "RP2350"),
    (["arduino uno r4"], "arduino", "Arduino Uno R4"),
    (["arduino mega"], "arduino", "Arduino Mega"),
    (["arduino nano"], "arduino", "Arduino Nano"),
    (["arduino uno"], "arduino", "Arduino Uno"),
    (["arduino leonardo"], "arduino", "Arduino Leonardo"),
    (["arduino"], "arduino", "Arduino Board"),
    (["teensy"], "teensy", "Teensy"),
    (["seeed", "xiao", "seeeduino"], "seeed-xiao", "Seeed XIAO"),
    (["m5stack", "m5core", "m5stick", "m5atom", "m5stamp", "core2", "cardputer"], "esp32-s3", "M5Stack"),
    (["lilygo", "ttgo", "t-display", "t-embed"], "esp32", "LilyGO"),
    (["waveshare", "rp2040-zero", "rp2040-plus"], "rp2040", "Waveshare RP2040"),
    (["waveshare", "s3-matrix", "esp32-s3-matrix"], "esp32-s3", "Waveshare ESP32-S3 Matrix"),
    (["waveshare", "s3-touch", "s3-amoled", "s3-geek"], "esp32-s3", "Waveshare ESP32-S3"),
    (["stm32", "st-link", "stlink"], "stm32", "STM32"),
    (["nrf52", "nrf53", "nrf91"], "nrf", "Nordic nRF"),
    (["orangepi", "orange pi"], "allwinner", "OrangePi"),
    (["banana pi", "bananapi"], "allwinner", "Banana Pi"),
    (["coral", "edge tpu"], "coral", "Google Coral"),
    (["movidius", "myriad", "ncs2"], "movidius", "Intel NCS"),
    (["quansheng", "uv-k5", "uvk5", "egzumer"], "radio", "Quansheng UV-K5"),
    (["cp210", "cp2102", "cp2104"], "uart-bridge", "Silicon Labs CP210x"),
    (["ch340"], "uart-bridge", "WCH CH340"),
    (["ch341"], "uart-bridge", "WCH CH341"),
    (["ch9102"], "uart-bridge", "WCH CH9102"),
    (["ft232", "ft2232", "ft4232"], "uart-bridge", "FTDI UART"),
    (["pl2303"], "uart-bridge", "Prolific PL2303"),
    (["raspberry pi", "raspberrypi"], "rpi-sbc", "Raspberry Pi"),
    (["jetson"], "nvidia", "NVIDIA Jetson"),
    (["adafruit"], "circuitpython", "Adafruit Board"),
]

DEFAULT_MDNS_SCAN_TYPES = [
    "_nirvana-npu._tcp.local.",
    "_http._tcp.local.",
    "_ssh._tcp.local.",
    "_esphomelib._tcp.local.",
    "_arduino._tcp.local.",
    "_workstation._tcp.local.",
]

_USB_VID_PID_RE = re.compile(r"VID_([0-9A-F]{4})&PID_([0-9A-F]{4})", flags=re.IGNORECASE)
_VIRTUAL_INTERFACE_TOKENS = (
    "tailscale",
    "loopback",
    "vethernet",
    "hyper-v",
    "virtual",
    "wintun",
    "vmware",
    "docker",
    "bluetooth",
)

# Serial ports worth probing for a live MicroPython REPL. We deliberately
# exclude mass-storage and radio bridges so a probe never disturbs them.
_MICROPYTHON_PROBE_FAMILIES = {
    "esp32", "esp32-s2", "esp32-s3", "esp32-c3", "esp32-c6", "esp32-h2", "esp32-p4",
    "esp8266", "seeed-xiao", "rp2040", "rp2350", "arduino", "nrf", "teensy", "stm32",
    "microchip", "unknown", "serial", "uart-bridge",
}

# Marker emitted by the raw-REPL introspection snippet (see _probe_micropython_serial).
_MICROPYTHON_PROBE_MARKER = "NIRVANA_PROBE|"
_MICROPYTHON_PROBE_RE = re.compile(
    rb"NIRVANA_PROBE\|([0-9a-fA-F]+)\|([^|]*)\|([^|]*)\|([^|\r\n]*)\|([01])\|([^|\r\n]*)"
)


# ── Profile catalog ──────────────────────────────────────────────

FIRMWARE_PROFILE_CATALOG = {
    "esp32-micropython-agent": {
        "id": "esp32-micropython-agent",
        "name": "ESP32 MicroPython Agent",
        "target_runtime": "micropython",
        "description": "Wi-Fi edge agent bundle for ESP32-class boards using the existing repo firmware.",
        "supported_families": ["esp32", "esp32-s2", "esp32-s3", "esp32-c3", "esp32-c6", "esp32-h2", "esp32-p4", "esp8266", "seeed-xiao"],
        "install_method": "serial-or-manual-copy",
        "live_install_supported": False,
        "supports_ota": True,
    },
    "circuitpython-control": {
        "id": "circuitpython-control",
        "name": "CircuitPython Control Bundle",
        "target_runtime": "circuitpython",
        "description": "USB/Wi-Fi control bundle for CircuitPython and UF2-capable boards with direct install to mounted CIRCUITPY drives.",
        "supported_families": ["circuitpython", "rp2040", "rp2350", "nrf", "microchip", "seeed-xiao", "teensy"],
        "install_method": "usb-mass-storage-or-manual",
        "live_install_supported": True,
        "supports_ota": False,
    },
    "linux-agent": {
        "id": "linux-agent",
        "name": "Linux Edge Agent",
        "target_runtime": "linux-python",
        "description": "Systemd-ready Linux edge agent bundle for Orange Pi, Raspberry Pi, LuckFox, and other SBC targets.",
        "supported_families": ["rpi-sbc", "rockchip", "allwinner", "nvidia", "coral", "movidius", "qualcomm"],
        "install_method": "scp-or-shell",
        "live_install_supported": False,
        "supports_ota": True,
    },
}


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def _slugify(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in value)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-") or "device"


def _identify_by_heuristics(description: str, manufacturer: str, hwid: str) -> Optional[dict]:
    combined = f"{description} {manufacturer} {hwid}".lower()
    for keywords, family, chip_label in _HEURISTIC_RULES:
        if any(kw in combined for kw in keywords):
            return {
                "family": family,
                "chip": chip_label,
                "npu": family in ("coral", "movidius", "rockchip", "nvidia"),
                "flash_mb": 0,
            }
    return None


def _family_has_npu(family: str) -> bool:
    return family in {"coral", "movidius", "rockchip", "nvidia", "qualcomm"}


def _flash_size_to_mb(flash_size: Optional[str]) -> int:
    if not flash_size:
        return 0
    digits = "".join(ch for ch in str(flash_size) if ch.isdigit())
    if not digits:
        return 0
    try:
        return int(digits)
    except ValueError:
        return 0


def _classify_chip_identity(chip_name: str, manufacturer: str = "", description: str = "") -> Optional[dict]:
    if not chip_name:
        return None
    heuristic = _identify_by_heuristics(chip_name, manufacturer, description)
    if heuristic and heuristic.get("family") not in {"uart-bridge", "serial", "unknown"}:
        return heuristic

    lower = chip_name.lower()
    if lower.startswith("esp"):
        return {
            "family": "esp32-s3" if "s3" in lower else
                      "esp32-s2" if "s2" in lower else
                      "esp32-c3" if "c3" in lower else
                      "esp32-c6" if "c6" in lower else
                      "esp32-h2" if "h2" in lower else
                      "esp32-p4" if "p4" in lower else
                      "esp8266" if "8266" in lower else
                      "esp32",
            "chip": chip_name,
            "npu": "p4" in lower,
            "flash_mb": 0,
        }
    return heuristic


def _is_generic_serial_family(family: str) -> bool:
    return family in {"unknown", "serial", "uart-bridge"}


def _classify_micropython_machine(machine: str) -> dict:
    """Map a MicroPython ``os.uname().machine`` string to a family/chip.

    These strings are the ground truth for silicon identity (USB VID/PID can be
    a generic Espressif/TinyUSB descriptor that misidentifies the chip).
    """
    m = (machine or "").lower()
    if "s3" in m:
        return {"family": "esp32-s3", "chip": "ESP32-S3", "npu": False, "flash_mb": 8}
    if "s2" in m:
        return {"family": "esp32-s2", "chip": "ESP32-S2", "npu": False, "flash_mb": 4}
    if "c6" in m:
        return {"family": "esp32-c6", "chip": "ESP32-C6", "npu": False, "flash_mb": 4}
    if "c3" in m:
        return {"family": "esp32-c3", "chip": "ESP32-C3", "npu": False, "flash_mb": 4}
    if "h2" in m:
        return {"family": "esp32-h2", "chip": "ESP32-H2", "npu": False, "flash_mb": 4}
    if "p4" in m:
        return {"family": "esp32-p4", "chip": "ESP32-P4", "npu": True, "flash_mb": 16}
    if "8266" in m:
        return {"family": "esp8266", "chip": "ESP8266", "npu": False, "flash_mb": 0}
    if "rp2350" in m:
        return {"family": "rp2350", "chip": "RP2350", "npu": False, "flash_mb": 4}
    if "rp2040" in m:
        return {"family": "rp2040", "chip": "RP2040", "npu": False, "flash_mb": 2}
    if "esp32" in m:
        return {"family": "esp32", "chip": "ESP32", "npu": False, "flash_mb": 4}
    if "stm32" in m:
        return {"family": "stm32", "chip": "STM32", "npu": False, "flash_mb": 0}
    if "nrf52" in m or "nrf53" in m or "nrf91" in m:
        return {"family": "nrf", "chip": "Nordic nRF", "npu": False, "flash_mb": 1}
    return {}



def _should_preserve_existing_identity(existing: dict, discovered: dict) -> bool:
    existing_family = str(existing.get("family") or "")
    discovered_family = str(discovered.get("family") or "")

    if not existing_family or existing_family == discovered_family:
        return False

    if not _is_generic_serial_family(existing_family) and _is_generic_serial_family(discovered_family):
        return True

    existing_chip = str(existing.get("chip") or "").lower()
    detected_chip_at = existing.get("last_chip_detected_at")
    if detected_chip_at and _is_generic_serial_family(discovered_family):
        return True

    if existing_family == "radio" and discovered_family == "uart-bridge":
        return True

    if (existing_family.startswith("esp") or "quansheng" in existing_chip) and discovered_family == "uart-bridge":
        return True

    return False


def _same_device_identity(existing: dict, discovered: dict) -> bool:
    """Best-effort fingerprint check before carrying paired state across scans."""
    if not existing:
        return False

    if (existing.get("connection") or "") != (discovered.get("connection") or ""):
        return False

    # Stable hardware identity first.
    for field in ("serial_number", "board_id", "mac", "chip_mac"):
        e_val = str(existing.get(field) or "").strip().lower()
        d_val = str(discovered.get(field) or "").strip().lower()
        if e_val and d_val:
            return e_val == d_val

    # Fallbacks per transport.
    connection = discovered.get("connection")
    if connection in {"usb", "usb-mass-storage"}:
        e_port = str(existing.get("port") or existing.get("drive") or "").strip().lower()
        d_port = str(discovered.get("port") or discovered.get("drive") or "").strip().lower()
        return bool(e_port and d_port and e_port == d_port)

    if connection == "wifi":
        e_ip = str(existing.get("ip") or existing.get("host") or "").strip().lower()
        d_ip = str(discovered.get("ip") or discovered.get("host") or "").strip().lower()
        return bool(e_ip and d_ip and e_ip == d_ip)

    if connection == "ble":
        e_addr = str(existing.get("address") or "").strip().lower()
        d_addr = str(discovered.get("address") or "").strip().lower()
        return bool(e_addr and d_addr and e_addr == d_addr)

    return True


def _compact_text(value: str, limit: int = 160) -> str:
    compact = " ".join(str(value or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def _extract_html_title(text: str) -> str:
    if not text:
        return ""
    match = re.search(r"<title[^>]*>(.*?)</title>", text, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return _compact_text(match.group(1), limit=120)


def _parse_http_probe(raw_text: str) -> dict:
    if not raw_text:
        return {}

    header_block, _, body = raw_text.partition("\r\n\r\n")
    if not body and "\n\n" in raw_text:
        header_block, _, body = raw_text.partition("\n\n")

    headers = {}
    for line in header_block.splitlines()[1:]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        headers[key.strip().lower()] = value.strip()

    return {
        "server_header": headers.get("server", ""),
        "location": headers.get("location", ""),
        "page_title": _extract_html_title(body),
        "body_preview": _compact_text(body, limit=220),
    }


def _classify_network_endpoint(
    hostname: str = "",
    server_header: str = "",
    page_title: str = "",
    body_preview: str = "",
    ssh_banner: str = "",
) -> dict:
    evidence = " ".join(filter(None, [hostname, server_header, page_title, body_preview, ssh_banner]))
    heuristic = _identify_by_heuristics(evidence, "", "") or {}
    description = _compact_text(page_title or server_header or ssh_banner or hostname or "Network device")
    family = heuristic.get("family", "unknown")

    return {
        "family": family,
        "chip": heuristic.get("chip") or description or "unknown",
        "has_npu": heuristic.get("npu", _family_has_npu(family)),
        "description": description,
    }


def _device_tier(family: str) -> str:
    if family in {"rockchip", "allwinner", "rpi-sbc", "nvidia", "coral", "movidius", "qualcomm"}:
        return "sbc"
    if family in {"unknown", "serial", "uart-bridge", "microchip"}:
        return "unknown"
    return "mcu"


def _is_low_confidence_device(device: dict) -> bool:
    if device.get("connection") != "wifi":
        return False
    if device.get("paired"):
        return False

    family = device.get("family")
    status = device.get("status")
    device_id = str(device.get("id") or "")
    description = (device.get("description") or "").strip().lower()
    chip = (device.get("chip") or "").strip().lower()

    if family not in {"unknown", "serial"}:
        return False

    if status in {"reachable", "offline"}:
        return True

    return device_id.startswith("net-") and description in {"", "unknown"} and chip in {"", "unknown"}


def _profile_matches_device(profile: dict, device: dict) -> bool:
    family = device.get("family", "unknown")
    chip = (device.get("chip") or "").lower()
    if family in profile["supported_families"]:
        return True
    if profile["id"] == "esp32-micropython-agent" and family == "circuitpython":
        return "esp32" in chip or "s2" in chip or "s3" in chip
    return False


def _recommended_profile_id(device: dict) -> Optional[str]:
    for profile in FIRMWARE_PROFILE_CATALOG.values():
        if _profile_matches_device(profile, device):
            return profile["id"]
    return None


def _build_protocols(device: dict) -> list[str]:
    family = str(device.get("family") or "").lower()
    connection = str(device.get("connection") or "").lower()
    protocols: list[str] = []

    if connection == "usb" or family in {"uart-bridge", "esp32", "esp32-s2", "esp32-s3", "esp32-c3", "esp32-c6", "esp32-h2", "esp32-p4", "esp8266", "rp2040", "rp2350", "arduino", "stm32", "nrf", "microchip", "teensy", "radio"}:
        protocols.append("uart")
    if family in {"esp32", "esp32-s2", "esp32-s3", "esp32-c3", "esp32-c6", "esp32-h2", "esp32-p4", "esp8266", "rp2040", "rp2350", "arduino", "stm32", "nrf", "microchip", "teensy", "circuitpython"}:
        protocols.extend(["gpio", "i2c", "spi"])
    if family in {"rockchip", "allwinner", "rpi-sbc", "nvidia", "coral", "movidius", "qualcomm"}:
        protocols.extend(["ssh", "http", "mqtt"])
    if _recommended_profile_id(device) in {"esp32-micropython-agent", "linux-agent"}:
        protocols.append("ota")

    deduped: list[str] = []
    seen = set()
    for protocol in protocols:
        if protocol not in seen:
            deduped.append(protocol)
            seen.add(protocol)
    return deduped


def _build_transport_modes(device: dict) -> list[str]:
    connection = str(device.get("connection") or "").lower()
    transport_modes: list[str] = []

    if connection == "usb" and device.get("port"):
        transport_modes.append("serial")
    if connection == "usb-mass-storage" and device.get("drive"):
        transport_modes.append("mass-storage")
    if device.get("agent_endpoint") or device.get("agent_port"):
        transport_modes.append("http-agent")
    if device.get("transport_preference") == "agent-poll":
        transport_modes.append("agent-poll")
    if device.get("ip") or device.get("host"):
        transport_modes.extend(["network", "ssh"])

    deduped: list[str] = []
    seen = set()
    for mode in transport_modes:
        if mode not in seen:
            deduped.append(mode)
            seen.add(mode)
    return deduped


def list_firmware_profiles(device: Optional[dict] = None) -> list[dict]:
    profiles = []
    recommended = _recommended_profile_id(device or {}) if device else None
    for profile in FIRMWARE_PROFILE_CATALOG.values():
        entry = dict(profile)
        entry["recommended"] = profile["id"] == recommended
        entry["compatible"] = _profile_matches_device(profile, device) if device else True
        profiles.append(entry)
    return profiles


def _family_supports_flash(family: str, status: str, connection: str) -> bool:
    """Determine if a device can be flashed via USB tools."""
    if family.startswith("esp32") or status == "bootsel":
        return True
    if family == "rockchip" and connection == "usb":
        tools = flash_service.flash_tools_available()
        return tools.get("rkdeveloptool", False) or tools.get("upgrade_tool", False)
    return False


def _build_capabilities(device: dict) -> dict:
    family = device.get("family", "unknown")
    connection = device.get("connection", "unknown")
    status = device.get("status", "unknown")
    recommended_profile = _recommended_profile_id(device)
    live_install = connection == "usb-mass-storage" and status == "mounted"
    transport_modes = _build_transport_modes(device)
    telemetry_present = bool(device.get("telemetry"))
    can_run_remote = any(mode in {"http-agent", "agent-poll", "ssh"} for mode in transport_modes)
    can_open_console = bool(device.get("port")) or can_run_remote

    return {
        "pair": True,
        "prepare": recommended_profile is not None,
        "install": live_install and recommended_profile == "circuitpython-control",
        "backup": family.startswith("esp32"),
        "chip_detect": family.startswith("esp32") or family == "uart-bridge",
        "flash": _family_supports_flash(family, status, connection),
        "ota": recommended_profile in {"esp32-micropython-agent", "linux-agent"},
        "console": can_open_console,
        "telemetry": telemetry_present or can_run_remote,
        "sensor_poll": telemetry_present or can_run_remote,
        "shell": can_run_remote,
        "reboot": can_run_remote,
        "build": recommended_profile is not None,
        "protocols": _build_protocols(device),
        "transport_modes": transport_modes,
    }


def _enrich_device(device: dict) -> dict:
    now = datetime.now(timezone.utc)
    last_seen = _parse_iso(device.get("last_seen") or device.get("discovered_at"))
    age_seconds = (now - last_seen).total_seconds() if last_seen else 999999
    recent_window = 600 if device.get("connection") in {"usb", "usb-mass-storage", "ble"} else 300
    available = age_seconds <= recent_window or device.get("status") in {"online", "mounted", "bootsel"}

    device.setdefault("nickname", "")
    device.setdefault("notes", "")
    device.setdefault("firmware_version", "")
    device.setdefault("agent_installed", False)
    device.setdefault("paired", False)
    device.setdefault("management_state", "paired" if device.get("paired") else "detected")
    device["tier"] = _device_tier(device.get("family", "unknown"))
    device["recommended_profile"] = _recommended_profile_id(device)
    device["profiles"] = list_firmware_profiles(device)
    device["capabilities"] = _build_capabilities(device)
    device["confidence"] = "low" if _is_low_confidence_device(device) else ("high" if device.get("family") not in {"unknown", "serial", "uart-bridge"} else "medium")
    device["available"] = available
    device["group"] = "paired" if device.get("paired") else "detected"
    if not available and device.get("status") in {"detected", "reachable", "visible", "mounted"}:
        device["status"] = "offline"
    return device


def _should_persist_device(device: dict) -> bool:
    return True


def _should_hide_from_default_listing(device: dict) -> bool:
    return _is_low_confidence_device(device) and not device.get("paired")


def _load_json_file(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json_file(path: Path, data: dict):
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _read_text_file(path: Path, default: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return default


def _normalize_identity_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _extract_usb_vid_pid(*values: str) -> tuple[Optional[int], Optional[int]]:
    for value in values:
        match = _USB_VID_PID_RE.search(str(value or ""))
        if not match:
            continue
        return int(match.group(1), 16), int(match.group(2), 16)
    return None, None


def _classify_usb_identity(
    vid: Optional[int],
    pid: Optional[int],
    description: str = "",
    manufacturer: str = "",
    hwid: str = "",
) -> dict:
    if vid is not None and pid is not None:
        info = USB_DEVICE_MAP.get((vid, pid))
        if info:
            return {
                "family": info["family"],
                "chip": info["chip"],
                "has_npu": info["npu"],
                "flash_mb": info["flash_mb"],
                "status": "detected",
            }

        vid_info = USB_VID_MAP.get(vid)
        if vid_info:
            family = vid_info["family"]
            return {
                "family": family,
                "chip": f"{vid_info['vendor']} Device (PID:{hex(pid)})",
                "has_npu": _family_has_npu(family),
                "flash_mb": 0,
                "status": "detected",
            }

    heuristic = _identify_by_heuristics(description or "", manufacturer or "", hwid or "")
    if heuristic:
        return {
            "family": heuristic["family"],
            "chip": heuristic["chip"],
            "has_npu": heuristic["npu"],
            "flash_mb": heuristic["flash_mb"],
            "status": "detected",
        }

    chip_name = description or manufacturer or "USB Device"
    if vid is not None and pid is not None:
        chip_name += f" ({hex(vid)}:{hex(pid)})"
    return {
        "family": "serial" if "serial" in chip_name.lower() else "unknown",
        "chip": chip_name,
        "has_npu": False,
        "flash_mb": 0,
        "status": "detected",
    }


def _run_powershell_json(command: str, timeout: float = 15.0) -> list[dict]:
    if platform.system() != "Windows":
        return []

    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except Exception as exc:
        logger.debug("PowerShell probe failed: %s", exc)
        return []

    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        if stderr:
            logger.debug("PowerShell probe returned %s: %s", completed.returncode, stderr)
        return []

    payload = (completed.stdout or "").strip()
    if not payload:
        return []

    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        start = min((index for index in (payload.find("["), payload.find("{")) if index != -1), default=-1)
        if start < 0:
            logger.debug("PowerShell probe produced non-JSON output")
            return []
        try:
            parsed = json.loads(payload[start:])
        except Exception as exc:
            logger.debug("Failed to parse PowerShell JSON payload: %s", exc)
            return []

    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    if isinstance(parsed, dict):
        return [parsed]
    return []


def _is_virtual_interface(alias: str) -> bool:
    lowered = str(alias or "").lower()
    return any(token in lowered for token in _VIRTUAL_INTERFACE_TOKENS)


def _is_candidate_neighbor_ip(ip_address: str) -> bool:
    try:
        candidate = ipaddress.ip_address(str(ip_address or ""))
    except ValueError:
        return False

    if candidate.version != 4 or candidate.is_loopback or candidate.is_multicast or candidate.is_unspecified:
        return False

    octets = str(candidate).split(".")
    return octets[-1] not in {"0", "255"}


def _is_candidate_neighbor_mac(mac_address: str) -> bool:
    normalized = str(mac_address or "").strip().upper().replace(":", "-")
    if not normalized or normalized in {"FF-FF-FF-FF-FF-FF", "00-00-00-00-00-00"}:
        return False
    return not normalized.startswith(("01-00-5E", "33-33"))


def _safe_device_id_fragment(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-") or "device"


def _windows_drive_letters() -> list[str]:
    if platform.system() != "Windows":
        return []
    import ctypes

    letters = []
    bitmask = ctypes.windll.kernel32.GetLogicalDrives()
    for index in range(26):
        if bitmask & (1 << index):
            letters.append(chr(65 + index) + ":\\")
    return letters


def _get_volume_label_windows(drive: str) -> str:
    if platform.system() != "Windows":
        return ""
    try:
        import ctypes
        import ctypes.wintypes

        volume_name = ctypes.create_unicode_buffer(261)
        fs_name = ctypes.create_unicode_buffer(261)
        ctypes.windll.kernel32.GetVolumeInformationW(
            ctypes.c_wchar_p(drive),
            volume_name,
            ctypes.sizeof(volume_name),
            None,
            None,
            None,
            fs_name,
            ctypes.sizeof(fs_name),
        )
        return volume_name.value or ""
    except Exception:
        return ""


def _parse_boot_out_chip(boot_out_content: str, fallback_label: str = "") -> str:
    for line in boot_out_content.splitlines():
        line = line.strip()
        if ";" in line:
            return line.split(";", 1)[1].strip()
    return fallback_label or "CircuitPython Device"


def scan_usb_mass_storage_devices() -> list[dict]:
    """Detect BOOTSEL and mounted CIRCUITPY drives on Windows."""
    if platform.system() != "Windows":
        return []

    import ctypes

    devices: list[dict] = []
    for drive in _windows_drive_letters():
        try:
            drive_type = ctypes.windll.kernel32.GetDriveTypeW(drive)
            if drive_type != 2:  # DRIVE_REMOVABLE
                continue

            label = _get_volume_label_windows(drive)
            info_uf2 = Path(drive) / "INFO_UF2.TXT"
            boot_out = Path(drive) / "boot_out.txt"

            if info_uf2.exists():
                content = _read_text_file(info_uf2)
                board_id = ""
                model = label or "UF2 Device"
                for line in content.splitlines():
                    if "Board-ID:" in line:
                        board_id = line.split(":", 1)[1].strip()
                    elif "Model:" in line:
                        model = line.split(":", 1)[1].strip()

                family = "nrf" if "nrf" in board_id.lower() else ("rp2350" if "2350" in model.lower() else "rp2040")
                devices.append({
                    "id": f"bootsel-{drive[0].lower()}",
                    "drive": drive,
                    "volume_label": label,
                    "board_id": board_id,
                    "chip": model,
                    "family": family,
                    "has_npu": False,
                    "flash_mb": 0,
                    "connection": "usb-mass-storage",
                    "status": "bootsel",
                    "discovered_at": _utcnow_iso(),
                })
                continue

            if boot_out.exists() or label.upper() == "CIRCUITPY":
                content = _read_text_file(boot_out)
                chip = _parse_boot_out_chip(content, label or "CircuitPython Device")
                devices.append({
                    "id": f"circuitpy-{drive[0].lower()}",
                    "drive": drive,
                    "volume_label": label or "CIRCUITPY",
                    "boot_out": content,
                    "chip": chip,
                    "family": "circuitpython",
                    "has_npu": False,
                    "flash_mb": 0,
                    "connection": "usb-mass-storage",
                    "status": "mounted",
                    "discovered_at": _utcnow_iso(),
                })
        except Exception as exc:
            logger.debug("Mass-storage drive inspection failed for %s: %s", drive, exc)

    return devices


def scan_windows_usb_pnp_devices(serial_devices: Optional[list[dict]] = None) -> list[dict]:
    """Broader Windows USB discovery for boards that do not expose a COM port."""
    if platform.system() != "Windows":
        return []

    raw_devices = _run_powershell_json(
        """
        $devices = Get-PnpDevice -PresentOnly |
            Where-Object { $_.Status -eq 'OK' -and $_.InstanceId -like 'USB\\VID_*' } |
            Select-Object Class,FriendlyName,InstanceId,Manufacturer,Status
        $devices | ConvertTo-Json -Depth 4 -Compress
        """,
        timeout=20.0,
    )
    if not raw_devices:
        return []

    serial_devices = serial_devices or []
    serial_tokens: set[str] = set()
    serial_vid_pid: set[tuple[int, int]] = set()
    for device in serial_devices:
        vid = device.get("vid")
        pid = device.get("pid")
        if isinstance(vid, int) and isinstance(pid, int):
            serial_vid_pid.add((vid, pid))

        for token in [device.get("serial_number"), device.get("port")]:
            normalized = _normalize_identity_token(token)
            if normalized:
                serial_tokens.add(normalized)

        hwid = str(device.get("hwid") or "")
        serial_match = re.search(r"SER=([^\s]+)", hwid, flags=re.IGNORECASE)
        if serial_match:
            serial_tokens.add(_normalize_identity_token(serial_match.group(1)))

    discovered: list[dict] = []
    seen_ids: set[str] = set()
    for entry in raw_devices:
        instance_id = str(entry.get("InstanceId") or "")
        class_name = str(entry.get("Class") or "")
        friendly_name = str(entry.get("FriendlyName") or class_name or "USB Device")
        manufacturer = str(entry.get("Manufacturer") or "")
        lowered_name = friendly_name.lower()
        lowered_class = class_name.lower()

        if any(token in lowered_name for token in ("host controller", "root hub", "generic usb hub")):
            continue
        if lowered_class == "net":
            continue

        vid, pid = _extract_usb_vid_pid(instance_id, friendly_name)
        classification = _classify_usb_identity(vid, pid, friendly_name, manufacturer, instance_id)
        instance_tail = _normalize_identity_token(instance_id.split("\\")[-1])

        if instance_tail and instance_tail in serial_tokens:
            continue
        if vid is not None and pid is not None and (vid, pid) in serial_vid_pid:
            continue
        if friendly_name in {"USB Composite Device", "USB Mass Storage Device"} and classification.get("family") in {"unknown", "serial", "uart-bridge"}:
            continue
        if classification.get("family") in {"unknown", "serial", "uart-bridge"}:
            continue

        device_id = f"usb-pnp-{_safe_device_id_fragment(instance_id)}"
        if device_id in seen_ids:
            continue
        seen_ids.add(device_id)

        discovered.append({
            "id": device_id,
            "instance_id": instance_id,
            "device_class": class_name,
            "description": friendly_name,
            "manufacturer": manufacturer,
            "vid": vid,
            "pid": pid,
            "hwid": instance_id,
            "connection": "usb",
            "discovered_at": _utcnow_iso(),
            **classification,
        })

    logger.info("Windows USB PnP scan found %s additional device(s)", len(discovered))
    return discovered


# ═══════════════════════════════════════════════════════════════════
#  USB / Serial Discovery
# ═══════════════════════════════════════════════════════════════════

def scan_usb_devices() -> list[dict]:
    try:
        import serial.tools.list_ports
    except ImportError:
        logger.warning("pyserial not installed — USB scan disabled")
        return []

    devices = []
    for port in serial.tools.list_ports.comports():
        device = {
            "id": f"usb-{port.device.replace('/', '-').replace('\\', '-')}",
            "port": port.device,
            "description": port.description or "",
            "manufacturer": port.manufacturer or "",
            "serial_number": port.serial_number or "",
            "hwid": port.hwid or "",
            "vid": port.vid,
            "pid": port.pid,
            "connection": "usb",
            "discovered_at": _utcnow_iso(),
        }

        device.update(_classify_usb_identity(
            port.vid,
            port.pid,
            port.description or "",
            port.manufacturer or "",
            port.hwid or "",
        ))

        devices.append(device)

    devices.extend(scan_windows_usb_pnp_devices(serial_devices=devices))

    logger.info("USB scan found %s device(s)", len(devices))
    return devices


# ═══════════════════════════════════════════════════════════════════
#  MicroPython / Nirvana OS Serial Probe
# ═══════════════════════════════════════════════════════════════════

def _should_probe_port(family: str) -> bool:
    return family in _MICROPYTHON_PROBE_FAMILIES


def _probe_micropython_serial(port: str, timeout: float = 2.5) -> Optional[dict]:
    """Probe a serial port for a live MicroPython REPL.

    Interrupts any running program, enters raw REPL, evaluates a small
    introspection snippet, then soft-resets the board so it returns to its
    normal program. Returns identity fields on success, ``None`` otherwise.
    """
    import serial

    try:
        ser = serial.Serial(port, baudrate=115200, timeout=0.2, write_timeout=1.0)
    except Exception as exc:
        logger.debug("MicroPython probe: cannot open %s (%s)", port, exc)
        return None

    snippet = (
        "import machine, os\r\n"
        "uid = machine.unique_id().hex()\r\n"
        "ip = ''\r\n"
        "try:\r\n"
        "    import network\r\n"
        "    w = network.WLAN(network.STA_IF)\r\n"
        "    if w.isconnected():\r\n"
        "        ip = w.ifconfig()[0]\r\n"
        "except Exception:\r\n"
        "    pass\r\n"
        "nirvana = '0'\r\n"
        "version = ''\r\n"
        "try:\r\n"
        "    if 'config.json' in os.listdir('/'):\r\n"
        "        nirvana = '1'\r\n"
        "except Exception:\r\n"
        "    pass\r\n"
        "try:\r\n"
        "    import sys\r\n"
        "    _main = sys.modules.get('main') or sys.modules.get('__main__')\r\n"
        "    if _main is not None and hasattr(_main, 'VERSION'):\r\n"
        "        version = str(_main.VERSION)\r\n"
        "except Exception:\r\n"
        "    pass\r\n"
        "if not version:\r\n"
        "    try:\r\n"
        "        with open('/main.py') as f:\r\n"
        "            _content = f.read()\r\n"
        "        import re as _re\r\n"
        "        _m = _re.search(r'VERSION\\s*=\\s*[\"\\']([^\"\\']+)[\"\\']', _content)\r\n"
        "        if _m:\r\n"
        "            version = _m.group(1)\r\n"
        "    except Exception:\r\n"
        "        pass\r\n"
        "if not version:\r\n"
        "    try:\r\n"
        "        with open('/version.json') as f:\r\n"
        "            import json\r\n"
        "            version = json.load(f).get('version', '')\r\n"
        "    except Exception:\r\n"
        "        pass\r\n"
        "print('NIRVANA_PROBE|%s|%s|%s|%s|%s|%s' % (uid, os.uname().machine, os.uname().release, ip, nirvana, version))\r\n"
    )

    try:
        # Interrupt any running program, then enter raw REPL.
        ser.write(b"\x03\x03")
        time.sleep(0.3)
        ser.reset_input_buffer()
        ser.write(b"\x01")
        time.sleep(0.15)
        ser.reset_input_buffer()

        ser.write(snippet.encode("utf-8") + b"\x04")

        out = b""
        deadline = time.time() + timeout
        while time.time() < deadline:
            chunk = ser.read(256)
            if not chunk:
                continue
            out += chunk
            if _MICROPYTHON_PROBE_MARKER.encode() in out and b"\r\n" in out:
                break

        # Restore the board to its normal program via soft reset.
        try:
            ser.write(b"import machine\r\nmachine.soft_reset()\r\n\x04")
        except Exception:
            pass
        time.sleep(0.2)
    except Exception as exc:
        logger.debug("MicroPython probe on %s failed: %s", port, exc)
        out = b""
    finally:
        try:
            ser.close()
        except Exception:
            pass

    if not out:
        return None

    match = _MICROPYTHON_PROBE_RE.search(out)
    if not match:
        return None

    uid = match.group(1).decode("ascii", "replace").strip().lower()
    if not uid:
        return None

    return {
        "device_id": uid,
        "machine": match.group(2).decode("ascii", "replace").strip(),
        "release": match.group(3).decode("ascii", "replace").strip(),
        "ip": match.group(4).decode("ascii", "replace").strip(),
        "nirvana": match.group(5) == b"1",
        "version": match.group(6).decode("ascii", "replace").strip(),
    }


def _known_board_ports() -> set[str]:
    """Serial ports already tied to a stable unique id in the registry.

    Generic ``usb-*`` entries for these ports must be dropped from scan
    results so they never duplicate the identified ``nirvana-``/``mp-`` entry.
    """
    registry = load_registry()
    ports: set[str] = set()
    for device in registry.get("devices", {}).values():
        if device.get("board_id") and device.get("port"):
            ports.add(str(device["port"]))
    return ports


def scan_micropython_boards(usb_devices: Optional[list[dict]] = None, skip_known: bool = True) -> list[dict]:
    """Probe candidate serial ports for live MicroPython/Nirvana boards.

    Returns registry-ready device dicts keyed by the board's stable unique id
    (``nirvana-<uid>`` for our firmware, ``mp-<uid>`` for stock MicroPython).
    Callers should drop the matching generic ``usb-*`` entries to avoid dupes.
    """
    try:
        import serial.tools.list_ports
    except ImportError:
        logger.warning("pyserial not installed — MicroPython board probe disabled")
        return []

    if usb_devices is None:
        usb_devices = scan_usb_devices()

    port_map: dict[str, dict] = {}
    for device in usb_devices:
        port = device.get("port")
        if port:
            port_map[port] = device

    known_ports: set[str] = _known_board_ports() if skip_known else set()

    boards: list[dict] = []
    for port in serial.tools.list_ports.comports():
        usb = port_map.get(port.device, {})
        family = str(usb.get("family") or "unknown")
        if not _should_probe_port(family):
            continue
        if skip_known and port.device in known_ports:
            continue

        probe = _probe_micropython_serial(port.device)
        if not probe:
            continue

        uid = probe["device_id"]
        is_nirvana = bool(probe["nirvana"])
        machine = probe["machine"]

        # The MicroPython machine string is the ground truth for silicon.
        # Seeed XIAO boards expose a specific Seeed VID only in bootloader
        # mode; in MicroPython mode the descriptor is a generic Espressif one.
        machine_identity = _classify_micropython_machine(machine) or {}
        usb_family = str(usb.get("family") or "")
        if usb_family == "seeed-xiao":
            family = "seeed-xiao"
        elif machine_identity:
            family = machine_identity["family"]
        else:
            family = "micropython"

        chip = machine_identity.get("chip") or str(usb.get("chip") or "").strip() or machine
        has_npu = bool(machine_identity.get("npu", usb.get("has_npu", _family_has_npu(family))))
        flash_mb = machine_identity.get("flash_mb") or usb.get("flash_mb", 0)

        boards.append({
            "id": f"{'nirvana' if is_nirvana else 'mp'}-{uid}",
            "board_id": uid,
            "port": port.device,
            "description": usb.get("description") or port.description or "",
            "manufacturer": usb.get("manufacturer") or port.manufacturer or "",
            "serial_number": usb.get("serial_number") or port.serial_number or "",
            "hwid": usb.get("hwid") or port.hwid or "",
            "vid": usb.get("vid", port.vid),
            "pid": usb.get("pid", port.pid),
            "connection": "usb",
            "runtime": "micropython",
            "firmware": "nirvana-os" if is_nirvana else "micropython",
            "firmware_version": probe["version"],
            "machine": machine,
            "release": probe["release"],
            "ip": probe["ip"],
            "status": "online" if probe["ip"] else "detected",
            "agent_installed": is_nirvana,
            "family": family,
            "chip": chip,
            "has_npu": has_npu,
            "flash_mb": flash_mb,
            "discovered_at": _utcnow_iso(),
        })

    if boards:
        logger.info("MicroPython probe identified %s board(s): %s",
                    len(boards), [b["id"] for b in boards])
    return boards


# ═══════════════════════════════════════════════════════════════════
#  mDNS / Zeroconf Discovery
# ═══════════════════════════════════════════════════════════════════

def scan_mdns(service_type: str = "_nirvana-npu._tcp.local.", timeout: float = 5.0) -> list[dict]:
    try:
        from zeroconf import Zeroconf, ServiceBrowser, ServiceListener
    except ImportError:
        logger.warning("zeroconf not installed — mDNS scan disabled")
        return []

    discovered: list[dict] = []

    class Listener(ServiceListener):
        def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
            info = zc.get_service_info(type_, name)
            if not info:
                return

            addresses = [addr for addr in info.parsed_addresses() if ":" not in addr]
            props = {}
            for key, value in (info.properties or {}).items():
                try:
                    props[key.decode()] = value.decode() if isinstance(value, bytes) else str(value)
                except Exception:
                    continue

            heuristic = _identify_by_heuristics(
                f"{name} {info.server}",
                props.get("model", "") or props.get("board", "") or props.get("product", ""),
                " ".join(addresses),
            )
            family = props.get("family") or (heuristic or {}).get("family") or "unknown"
            chip = props.get("chip") or (heuristic or {}).get("chip") or name.replace("._http._tcp.local.", "").replace("._ssh._tcp.local.", "")
            has_npu = props.get("npu", "").lower() == "true" if "npu" in props else (heuristic or {}).get("npu", _family_has_npu(family))

            discovered.append({
                "id": f"mdns-{name.replace(' ', '-')}",
                "name": name,
                "service_type": type_,
                "host": info.server,
                "addresses": addresses,
                "ip": addresses[0] if addresses else None,
                "port": info.port,
                "properties": props,
                "family": family,
                "chip": chip,
                "has_npu": has_npu,
                "connection": "wifi",
                "status": "online",
                "discovered_at": _utcnow_iso(),
            })

        def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
            return None

        def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
            return None

    zc = Zeroconf()
    try:
        listeners = []
        scan_types: list[str] = []
        for candidate in [service_type, *DEFAULT_MDNS_SCAN_TYPES]:
            if candidate and candidate not in scan_types:
                scan_types.append(candidate)

        for scan_type in scan_types:
            listener = Listener()
            listeners.append((scan_type, listener, ServiceBrowser(zc, scan_type, listener)))
        time.sleep(timeout)
    finally:
        zc.close()

    seen_ips: set[str] = set()
    unique: list[dict] = []
    for device in discovered:
        ip = device.get("ip")
        if ip and ip in seen_ips:
            continue
        if ip:
            seen_ips.add(ip)
        unique.append(device)

    logger.info("mDNS scan found %s device(s)", len(unique))
    return unique


# ═══════════════════════════════════════════════════════════════════
#  Subnet Scan
# ═══════════════════════════════════════════════════════════════════

def get_local_subnets() -> list[str]:
    if platform.system() == "Windows":
        interface_rows = _run_powershell_json(
            """
            $rows = Get-NetIPAddress -AddressFamily IPv4 |
                Where-Object {
                    $_.IPAddress -and
                    $_.IPAddress -notlike '127.*' -and
                    $_.PrefixLength -gt 0 -and
                    $_.InterfaceAlias
                } |
                Select-Object IPAddress,PrefixLength,InterfaceAlias
            $rows | ConvertTo-Json -Depth 4 -Compress
            """,
            timeout=15.0,
        )
        subnets: list[str] = []
        for row in interface_rows:
            alias = str(row.get("InterfaceAlias") or "")
            if _is_virtual_interface(alias):
                continue
            ip = str(row.get("IPAddress") or "")
            if not _is_candidate_neighbor_ip(ip):
                continue
            subnet = ".".join(ip.split(".")[:3])
            if subnet not in subnets:
                subnets.append(subnet)
        if subnets:
            return subnets

    import socket

    subnets = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip.startswith("127."):
                continue
            subnet = ".".join(ip.split(".")[:3])
            if subnet not in subnets:
                subnets.append(subnet)
    except Exception:
        pass
    return subnets


async def scan_network_neighbors(timeout: float = 0.35) -> list[dict]:
    """Discover adjacent LAN devices from the OS neighbor/ARP table."""
    if platform.system() != "Windows":
        return []

    neighbor_rows = _run_powershell_json(
        """
        $rows = Get-NetNeighbor -AddressFamily IPv4 |
            Select-Object IPAddress,LinkLayerAddress,InterfaceAlias,State
        $rows | ConvertTo-Json -Depth 4 -Compress
        """,
        timeout=15.0,
    )
    if not neighbor_rows:
        return []

    base_devices: list[dict] = []
    seen_ips: set[str] = set()
    for row in neighbor_rows:
        ip = str(row.get("IPAddress") or "").strip()
        mac = str(row.get("LinkLayerAddress") or "").strip().upper().replace(":", "-")
        interface_alias = str(row.get("InterfaceAlias") or "").strip()
        if not _is_candidate_neighbor_ip(ip) or not _is_candidate_neighbor_mac(mac):
            continue
        if _is_virtual_interface(interface_alias):
            continue
        if ip in seen_ips:
            continue
        seen_ips.add(ip)

        base_devices.append({
            "id": f"lan-{ip.replace('.', '-')}",
            "ip": ip,
            "mac": mac,
            "host": None,
            "interface": interface_alias,
            "connection": "network",
            "family": "unknown",
            "chip": "LAN Neighbor",
            "description": f"Neighbor on {interface_alias}" if interface_alias else "Neighbor table entry",
            "has_npu": False,
            "status": "visible",
            "discovered_at": _utcnow_iso(),
        })

    if not base_devices:
        return []

    probes = await asyncio.gather(
        *[_probe_network_target(device["ip"], timeout=timeout) for device in base_devices]
    )

    devices: list[dict] = []
    for base_device, probe in zip(base_devices, probes):
        if probe:
            devices.append({
                **base_device,
                **probe,
                "id": base_device["id"],
                "mac": base_device["mac"],
                "interface": base_device["interface"],
                "connection": "network",
                "family": probe.get("family") or base_device["family"],
                "chip": probe.get("chip") or base_device["chip"],
                "description": probe.get("description") or base_device["description"],
                "status": probe.get("status") or "visible",
            })
        else:
            devices.append(base_device)

    logger.info("Neighbor-table scan found %s network device(s)", len(devices))
    return devices


def _parse_known_host_tokens(raw_hosts: Optional[str] = None) -> list[str]:
    tokens: list[str] = []
    raw_sources = [raw_hosts, os.getenv("EDGE_KNOWN_HOSTS", "")]

    try:
        registry = load_registry()
        for device in registry.get("devices", {}).values():
            if device.get("connection") != "wifi":
                continue
            if not (device.get("paired") or device.get("status") in {"online", "reachable"}):
                continue
            raw_sources.extend([device.get("host", ""), device.get("ip", "")])
    except Exception:
        pass

    for raw_source in raw_sources:
        for token in re.split(r"[\s,;]+", str(raw_source or "")):
            token = token.strip()
            if token:
                tokens.append(token)

    deduped: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        lowered = token.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        deduped.append(token)
    return deduped


def _parse_probe_target(target: str) -> tuple[str, Optional[int], Optional[str]]:
    candidate = str(target or "").strip()
    if not candidate:
        return "", None, None

    parsed = urlparse(candidate if "://" in candidate else f"//{candidate}")
    host = parsed.hostname or candidate
    scheme = parsed.scheme or None
    port = parsed.port

    if port is None and scheme == "https":
        port = 443
    elif port is None and scheme == "http":
        port = 80

    return host, port, scheme


async def _probe_http_endpoint(host: str, port: int, timeout: float = 0.5, use_ssl: bool = False) -> dict:
    reader = None
    writer = None
    ssl_context = None
    if use_ssl:
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port, ssl=ssl_context if use_ssl else None),
            timeout=timeout,
        )
        request = (
            f"GET / HTTP/1.0\r\n"
            f"Host: {host}\r\n"
            "User-Agent: NPU-STACK/1.0\r\n"
            "Accept: text/html, */*\r\n"
            "Connection: close\r\n\r\n"
        )
        writer.write(request.encode("ascii", errors="ignore"))
        await writer.drain()
        raw = await asyncio.wait_for(reader.read(4096), timeout=timeout)
        return _parse_http_probe(raw.decode("utf-8", errors="ignore"))
    except Exception:
        return {}
    finally:
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass


async def _probe_ssh_banner(host: str, port: int, timeout: float = 0.5) -> str:
    reader = None
    writer = None
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout)
        raw = await asyncio.wait_for(reader.read(256), timeout=timeout)
        return _compact_text(raw.decode("utf-8", errors="ignore"), limit=160)
    except Exception:
        return ""
    finally:
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass


async def _probe_network_target(target: str, ports: Optional[list[int]] = None, timeout: float = 0.5) -> Optional[dict]:
    host, hinted_port, scheme = _parse_probe_target(target)
    if not host:
        return None

    default_ports = ports or [80, 81, 8080, 8000, 22]
    probe_ports = [hinted_port] if hinted_port else default_ports

    for port in probe_ports:
        try:
            _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout)
            peer = writer.get_extra_info("peername") or ()
            resolved_ip = peer[0] if peer else host
            writer.close()
            await writer.wait_closed()

            hostname = host if resolved_ip != host else ""

            server_header = ""
            page_title = ""
            body_preview = ""
            location = ""
            ssh_banner = ""
            service = "tcp"

            use_ssl = scheme == "https" or port == 443
            if port in {80, 81, 443, 8080, 8000} or scheme in {"http", "https"}:
                service = "https" if use_ssl else "http"
                probe = await _probe_http_endpoint(host, port, timeout=timeout, use_ssl=use_ssl)
                server_header = probe.get("server_header", "")
                page_title = probe.get("page_title", "")
                body_preview = probe.get("body_preview", "")
                location = probe.get("location", "")
            elif port == 22:
                service = "ssh"
                ssh_banner = await _probe_ssh_banner(host, port, timeout=timeout)

            classification = _classify_network_endpoint(
                hostname=hostname or host,
                server_header=server_header,
                page_title=page_title,
                body_preview=body_preview,
                ssh_banner=ssh_banner,
            )

            safe_id_host = str(resolved_ip or host).replace(".", "-").replace(":", "-")
            return {
                "id": f"net-{safe_id_host}-{port}",
                "ip": resolved_ip,
                "host": hostname or (host if host != resolved_ip else None),
                "target": target,
                "port": port,
                "connection": "wifi",
                "service": service,
                "family": classification.get("family", "unknown"),
                "chip": classification.get("chip", hostname or host or "unknown"),
                "description": classification.get("description", hostname or host or "Network device"),
                "has_npu": classification.get("has_npu", False),
                "status": "reachable",
                "server_header": server_header or None,
                "page_title": page_title or None,
                "location": location or None,
                "ssh_banner": ssh_banner or None,
                "discovered_at": _utcnow_iso(),
            }
        except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
            continue

    return None


async def scan_known_hosts(targets: list[str], ports: Optional[list[int]] = None, timeout: float = 0.5) -> list[dict]:
    if not targets:
        return []

    results = await asyncio.gather(*[_probe_network_target(target, ports=ports, timeout=timeout) for target in targets])
    devices = [device for device in results if device]

    unique: list[dict] = []
    seen: set[tuple[str, int]] = set()
    for device in devices:
        key = (str(device.get("ip") or device.get("host") or device.get("target")), int(device.get("port") or 0))
        if key in seen:
            continue
        seen.add(key)
        unique.append(device)
    return unique


async def scan_subnet(subnet: str, ports: Optional[list[int]] = None, timeout: float = 0.5) -> list[dict]:
    devices: list[dict] = []
    ports = ports or [80, 81, 8080, 8000, 22]

    for batch_start in range(1, 255, 50):
        batch_end = min(batch_start + 50, 255)
        batch_results = await asyncio.gather(
            *[_probe_network_target(f"{subnet}.{index}", ports=ports, timeout=timeout) for index in range(batch_start, batch_end)]
        )
        devices.extend([device for device in batch_results if device])

    return devices


# ═══════════════════════════════════════════════════════════════════
#  ESP32 Firmware Operations
# ═══════════════════════════════════════════════════════════════════

def esp_detect_chip(port: str) -> dict:
    try:
        import esptool
    except ImportError:
        return {"error": "esptool not installed. Run: pip install esptool"}

    try:
        import io
        import sys

        command = ["--port", port, "chip_id"]
        old_stdout = sys.stdout
        sys.stdout = captured = io.StringIO()
        try:
            esptool.main(command)
        except SystemExit:
            pass
        finally:
            sys.stdout = old_stdout

        output = captured.getvalue()
        result = {"raw_output": output, "status": "identified"}
        for line in output.split("\n"):
            lower = line.lower()
            if "chip is" in lower:
                result["chip"] = line.split("Chip is")[-1].strip() if "Chip is" in line else line.split("chip is")[-1].strip()
            elif "chip type:" in lower:
                result["chip"] = line.split(":", 1)[-1].strip()
            elif lower.startswith("connected to esp") and "chip" not in result:
                result["chip"] = line.split("Connected to", 1)[-1].split(" on ", 1)[0].strip()
            elif "features:" in lower:
                result["features"] = line.split(":", 1)[-1].strip()
            elif "mac:" in lower:
                result["mac"] = line.split(":", 1)[-1].strip()
            elif "flash size" in lower:
                result["flash_size"] = line.split(":", 1)[-1].strip()
        return result
    except Exception as exc:
        return {"error": str(exc), "status": "failed"}


def esp_backup_firmware(port: str, flash_size_mb: int = 4, output_name: str = "") -> dict:
    try:
        import esptool
    except ImportError:
        return {"error": "esptool not installed"}

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    port_clean = port.replace("/", "_").replace("\\", "_").replace(":", "")
    filename = f"{output_name or port_clean}_backup_{timestamp}.bin"
    filepath = str(FIRMWARE_DIR / filename)
    size_hex = hex(flash_size_mb * 1024 * 1024)

    try:
        esptool.main(["--port", port, "--baud", "460800", "read_flash", "0", size_hex, filepath])
        size_bytes = os.path.getsize(filepath) if os.path.exists(filepath) else 0
        return {
            "status": "success",
            "file": filepath,
            "filename": filename,
            "size_bytes": size_bytes,
            "flash_size_mb": flash_size_mb,
            "port": port,
            "backed_up_at": _utcnow_iso(),
        }
    except Exception as exc:
        return {"error": str(exc), "status": "failed", "port": port}


def esp_flash_firmware(port: str, firmware_path: str, flash_offset: str = "0x0") -> dict:
    try:
        import esptool
    except ImportError:
        return {"error": "esptool not installed"}

    if not os.path.exists(firmware_path):
        return {"error": f"Firmware file not found: {firmware_path}"}

    try:
        esptool.main(["--port", port, "--baud", "460800", "write_flash", "--flash_mode", "dio", flash_offset, firmware_path])
        return {
            "status": "success",
            "port": port,
            "firmware": firmware_path,
            "offset": flash_offset,
            "flashed_at": _utcnow_iso(),
        }
    except Exception as exc:
        return {"error": str(exc), "status": "failed"}


# ═══════════════════════════════════════════════════════════════════
#  RP2040 / Mass-storage Operations
# ═══════════════════════════════════════════════════════════════════

def rp2040_detect() -> list[dict]:
    return [device for device in scan_usb_mass_storage_devices() if device.get("status") == "bootsel"]


def rp2040_flash_uf2(drive_letter: str, uf2_path: str) -> dict:
    if not os.path.exists(uf2_path):
        return {"error": f"UF2 file not found: {uf2_path}"}

    target = os.path.join(drive_letter, os.path.basename(uf2_path))
    try:
        shutil.copy2(uf2_path, target)
        return {
            "status": "success",
            "uf2": uf2_path,
            "drive": drive_letter,
            "flashed_at": _utcnow_iso(),
            "note": "Device will reboot automatically after flashing.",
        }
    except Exception as exc:
        return {"error": str(exc), "status": "failed"}


# ═══════════════════════════════════════════════════════════════════
#  BLE Discovery
# ═══════════════════════════════════════════════════════════════════

async def scan_ble(timeout: float = 10.0) -> list[dict]:
    try:
        from bleak import BleakScanner
    except ImportError:
        logger.warning("bleak not installed — BLE scan disabled")
        return []

    devices = []
    try:
        for discovered in await BleakScanner.discover(timeout=timeout):
            name = discovered.name or "Unknown"
            devices.append({
                "id": f"ble-{discovered.address.replace(':', '-')}",
                "name": name,
                "address": discovered.address,
                "rssi": discovered.rssi,
                "connection": "ble",
                "family": "esp32" if "esp" in name.lower() else "unknown",
                "chip": name,
                "has_npu": False,
                "status": "visible",
                "is_edge_device": any(keyword in name.lower() for keyword in ["esp", "nirvana", "npu", "pico", "orange", "luckfox", "nrf"]),
                "discovered_at": _utcnow_iso(),
            })
    except Exception as exc:
        logger.error("BLE scan error: %s", exc)

    logger.info("BLE scan found %s device(s)", len(devices))
    return devices


# ═══════════════════════════════════════════════════════════════════
#  Registry helpers
# ═══════════════════════════════════════════════════════════════════

def load_registry() -> dict:
    if REGISTRY_FILE.exists():
        try:
            return _load_json_file(REGISTRY_FILE)
        except Exception:
            logger.warning("Failed to read edge registry — falling back to empty registry")
    return {"devices": {}, "last_scan": None}


def save_registry(registry: dict):
    _write_json_file(REGISTRY_FILE, registry)


def get_device_from_registry(device_id: str) -> Optional[dict]:
    registry = load_registry()
    device = registry.get("devices", {}).get(device_id)
    return _enrich_device(dict(device)) if device else None


def list_registry_devices(include_low_confidence: bool = False) -> dict:
    registry = load_registry()
    enriched = [_enrich_device(dict(device)) for device in registry.get("devices", {}).values()]
    hidden_low_confidence = sum(1 for device in enriched if _should_hide_from_default_listing(device))
    if not include_low_confidence:
        enriched = [device for device in enriched if not _should_hide_from_default_listing(device)]

    enriched.sort(
        key=lambda device: (
            0 if device.get("paired") else 1,
            0 if device.get("available") else 1,
            -( _parse_iso(device.get("last_seen")) or datetime.fromtimestamp(0, tz=timezone.utc)).timestamp(),
            device.get("nickname") or device.get("chip") or device.get("id"),
        )
    )

    return {
        "devices": enriched,
        "count": len(enriched),
        "paired_count": sum(1 for device in enriched if device.get("paired")),
        "detected_count": sum(1 for device in enriched if not device.get("paired")),
        "available_count": sum(1 for device in enriched if device.get("available")),
        "hidden_low_confidence": hidden_low_confidence,
        "last_scan": registry.get("last_scan"),
    }


def merge_into_registry(discovered: list[dict]) -> dict:
    registry = load_registry()
    devices = registry.get("devices", {})
    now = _utcnow_iso()

    for existing_id, existing_device in list(devices.items()):
        enriched_existing = _enrich_device(dict(existing_device))
        if _should_hide_from_default_listing(enriched_existing) and not enriched_existing.get("available"):
            devices.pop(existing_id, None)

    for discovered_device in discovered:
        if not _should_persist_device(discovered_device):
            continue

        device_id = discovered_device["id"]
        existing = devices.get(device_id, {})
        preserve_pairing = bool(existing.get("paired") and _same_device_identity(existing, discovered_device))
        merged = {
            **existing,
            **discovered_device,
            "first_seen": existing.get("first_seen") or now,
            "last_seen": now,
            "nickname": existing.get("nickname", ""),
            "notes": existing.get("notes", ""),
            "firmware_version": discovered_device.get("firmware_version") or existing.get("firmware_version", ""),
            "agent_installed": bool(discovered_device.get("agent_installed") or existing.get("agent_installed", False)),
            "paired": preserve_pairing,
            "management_state": existing.get("management_state", "paired" if preserve_pairing else "detected"),
            "preferred_profile_id": existing.get("preferred_profile_id"),
            "last_prepared_bundle_id": existing.get("last_prepared_bundle_id"),
        }

        if _should_preserve_existing_identity(existing, discovered_device):
            for field in ("family", "chip", "has_npu", "flash_mb", "chip_features", "chip_mac", "last_chip_detected_at"):
                existing_value = existing.get(field)
                if existing_value not in (None, "", 0):
                    merged[field] = existing_value

        devices[device_id] = merged

    # Dedup: drop generic usb-* entries that share a port with a board that has
    # a stable unique id (board_id). A single physical board must never appear
    # as both `usb-COMx` and `nirvana-<uid>` / `mp-<uid>`.
    identified_ports = {
        str(device.get("port"))
        for device in devices.values()
        if device.get("board_id") and device.get("port")
    }
    if identified_ports:
        for existing_id, existing_device in list(devices.items()):
            if str(existing_id).startswith("usb-") and str(existing_device.get("port") or "") in identified_ports:
                devices.pop(existing_id, None)

    registry["devices"] = devices
    registry["last_scan"] = now
    save_registry(registry)
    return registry


def register_board_heartbeat(
    device_id: str,
    ip: str = "",
    firmware: str = "",
    machine: str = "",
    family: str = "",
    chip: str = "",
) -> dict:
    """Upsert a Nirvana board that phoned home over WiFi.

    Keys the device by its stable unique id so a heartbeat and a later USB
    scan resolve to the same registry entry.
    """
    if not device_id:
        return {"status": "ignored", "reason": "missing device_id"}

    device_id = str(device_id).strip().lower()
    registry = load_registry()
    devices = registry.setdefault("devices", {})
    existing = devices.get(f"nirvana-{device_id}", {})
    now = _utcnow_iso()

    machine = machine or existing.get("machine") or ""
    chip_identity = _classify_micropython_machine(machine) or {}
    family = family or existing.get("family") or chip_identity.get("family") or "seeed-xiao"
    chip = chip or existing.get("chip") or chip_identity.get("chip") or "Nirvana Board"

    merged = {
        **existing,
        "id": f"nirvana-{device_id}",
        "board_id": device_id,
        "connection": existing.get("connection") or "wifi",
        "status": "online",
        "ip": ip or existing.get("ip", ""),
        "agent_installed": True,
        "firmware": "nirvana-os",
        "firmware_version": firmware or existing.get("firmware_version", ""),
        "machine": machine,
        "family": family,
        "chip": chip,
        "first_seen": existing.get("first_seen") or now,
        "last_seen": now,
        "nickname": existing.get("nickname", ""),
        "notes": existing.get("notes", ""),
        "paired": existing.get("paired", False),
        "management_state": existing.get("management_state", "detected"),
        "preferred_profile_id": existing.get("preferred_profile_id"),
    }
    devices[f"nirvana-{device_id}"] = merged
    registry["last_scan"] = now
    save_registry(registry)
    return {"status": "registered", "device": _enrich_device(dict(merged))}


# ═══════════════════════════════════════════════════════════════════
#  Firmware bundle preparation
# ═══════════════════════════════════════════════════════════════════

def _bundle_metadata_path(bundle_dir: Path) -> Path:
    return bundle_dir / "metadata.json"


def _zip_bundle(bundle_dir: Path, archive_path: Path):
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for file_path in bundle_dir.rglob("*"):
            if file_path == archive_path:
                continue
            archive.write(file_path, file_path.relative_to(bundle_dir))


def _device_display_name(device: dict, overrides: dict) -> str:
    return (
        overrides.get("device_name")
        or device.get("nickname")
        or device.get("chip")
        or device.get("id")
    )


def _esp32_bundle_files(bundle_dir: Path, device: dict, config: dict):
    source = FIRMWARE_ASSETS_DIR / "esp32-agent" / "main.py"
    shutil.copy2(source, bundle_dir / "main.py")
    device_name = _device_display_name(device, config)
    runtime_config = {
        "wifi_ssid": config.get("wifi_ssid", ""),
        "wifi_password": config.get("wifi_password", ""),
        "device_name": _slugify(device_name),
        "device_id": device.get("id"),
        "agent_port": int(config.get("agent_port") or 9200),
        "hub_url": config.get("command_center_url") or os.getenv("NPU_STACK_COMMAND_CENTER_URL", ""),
        "shared_secret": config.get("shared_secret") or os.getenv("NPU_STACK_AGENT_SHARED_SECRET", ""),
        "mqtt_broker": config.get("mqtt_broker", ""),
    }
    _write_json_file(bundle_dir / "config.json", runtime_config)
    (bundle_dir / "README.txt").write_text(
        "\n".join([
            "NPU-STACK ESP32 MicroPython Agent Bundle",
            "",
            f"Target device: {device_name}",
            "",
            "What is included:",
            "- main.py        -> existing repo ESP32 agent",
            "- config.json    -> generated device/network settings",
            "",
            "Install steps:",
            "1. Flash a MicroPython-compatible base image onto the board.",
            "2. Copy main.py and config.json to the device filesystem.",
            "3. Reboot the board and scan again from NPU-STACK.",
        ]),
        encoding="utf-8",
    )


def _circuitpython_bundle_files(bundle_dir: Path, device: dict, config: dict):
    source = FIRMWARE_ASSETS_DIR / "circuitpython-agent" / "code.py"
    shutil.copy2(source, bundle_dir / "code.py")
    device_name = _device_display_name(device, config)
    settings_lines = [
        f'DEVICE_NAME="{_slugify(device_name)}"',
        f'DEVICE_ID="{device.get("id")}"',
        f'AGENT_PORT="{int(config.get("agent_port") or 9200)}"',
        f'CIRCUITPY_WIFI_SSID="{config.get("wifi_ssid", "")}"',
        f'CIRCUITPY_WIFI_PASSWORD="{config.get("wifi_password", "")}"',
        f'COMMAND_CENTER_URL="{config.get("command_center_url") or os.getenv("NPU_STACK_COMMAND_CENTER_URL", "")}"',
        f'NPU_AGENT_SHARED_SECRET="{config.get("shared_secret") or os.getenv("NPU_STACK_AGENT_SHARED_SECRET", "")}"',
        f'MQTT_BROKER="{config.get("mqtt_broker", "")}"',
    ]
    (bundle_dir / "settings.toml").write_text("\n".join(settings_lines) + "\n", encoding="utf-8")
    (bundle_dir / "README.txt").write_text(
        "\n".join([
            "NPU-STACK CircuitPython Control Bundle",
            "",
            f"Target device: {device_name}",
            "",
            "What is included:",
            "- code.py        -> lightweight CircuitPython health/control service",
            "- settings.toml  -> generated network and management settings",
            "",
            "Install steps:",
            "1. If the board is not yet running CircuitPython, flash a board-compatible CircuitPython/UF2 image first.",
            "2. Mount the board as CIRCUITPY.",
            "3. Use NPU-STACK Install Bundle for direct copy, or copy the files manually.",
            "4. Safely eject the drive and reset the board.",
        ]),
        encoding="utf-8",
    )


def _linux_bundle_files(bundle_dir: Path, device: dict, config: dict):
    source_dir = FIRMWARE_ASSETS_DIR / "linux-agent"
    for file_name in ["nirvana_agent.py", "install.sh", "nirvana-agent.service"]:
        shutil.copy2(source_dir / file_name, bundle_dir / file_name)

    device_name = _device_display_name(device, config)
    env_lines = [
        f'NIRVANA_DEVICE_ID="{device.get("id")}"',
        f'NIRVANA_DEVICE_NAME="{_slugify(device_name)}"',
        f'NIRVANA_AGENT_PORT="{int(config.get("agent_port") or 9200)}"',
        f'NIRVANA_COMMAND_CENTER_URL="{config.get("command_center_url") or os.getenv("NPU_STACK_COMMAND_CENTER_URL", "")}"',
        f'NIRVANA_AGENT_SHARED_SECRET="{config.get("shared_secret") or os.getenv("NPU_STACK_AGENT_SHARED_SECRET", "")}"',
        f'NIRVANA_MQTT_BROKER="{config.get("mqtt_broker", "")}"',
    ]
    (bundle_dir / "nirvana.env").write_text("\n".join(env_lines) + "\n", encoding="utf-8")
    (bundle_dir / "README.txt").write_text(
        "\n".join([
            "NPU-STACK Linux Edge Agent Bundle",
            "",
            f"Target device: {device_name}",
            "",
            "What is included:",
            "- nirvana_agent.py      -> existing repo Linux edge agent",
            "- install.sh            -> repo install helper",
            "- nirvana-agent.service -> systemd unit",
            "- nirvana.env           -> generated environment values",
            "",
            "Install steps:",
            "1. Copy the bundle to the Linux edge device.",
            "2. Source nirvana.env or export the values manually.",
            "3. Run install.sh from the target device shell.",
        ]),
        encoding="utf-8",
    )


def prepare_firmware_bundle(device_id: str, profile_id: Optional[str] = None, config: Optional[dict] = None) -> dict:
    config = config or {}
    registry = load_registry()
    raw_device = registry.get("devices", {}).get(device_id)
    if not raw_device:
        return {"error": f"Device '{device_id}' not found", "status": "failed"}

    device = _enrich_device(dict(raw_device))
    selected_profile_id = profile_id or device.get("recommended_profile")
    if not selected_profile_id or selected_profile_id not in FIRMWARE_PROFILE_CATALOG:
        return {"error": f"No compatible firmware profile found for '{device_id}'", "status": "failed"}

    profile = FIRMWARE_PROFILE_CATALOG[selected_profile_id]
    bundle_id = f"{_slugify(device_id)}-{selected_profile_id}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    bundle_dir = PREPARED_DIR / bundle_id
    bundle_dir.mkdir(parents=True, exist_ok=True)

    if selected_profile_id == "esp32-micropython-agent":
        _esp32_bundle_files(bundle_dir, device, config)
    elif selected_profile_id == "circuitpython-control":
        _circuitpython_bundle_files(bundle_dir, device, config)
    elif selected_profile_id == "linux-agent":
        _linux_bundle_files(bundle_dir, device, config)
    else:
        return {"error": f"Unsupported profile '{selected_profile_id}'", "status": "failed"}

    archive_path = PREPARED_DIR / f"{bundle_id}.zip"
    _zip_bundle(bundle_dir, archive_path)

    metadata = {
        "bundle_id": bundle_id,
        "device_id": device_id,
        "device_name": _device_display_name(device, config),
        "profile_id": selected_profile_id,
        "profile_name": profile["name"],
        "created_at": _utcnow_iso(),
        "bundle_dir": str(bundle_dir),
        "archive_path": str(archive_path),
        "download_url": f"/api/devices/prepared/{bundle_id}/download",
        "installable": profile.get("live_install_supported") and device.get("connection") == "usb-mass-storage" and device.get("status") == "mounted",
        "instructions": _read_text_file(bundle_dir / "README.txt").splitlines(),
        "config": {key: value for key, value in config.items() if value not in (None, "")},
    }
    _write_json_file(_bundle_metadata_path(bundle_dir), metadata)

    registry["devices"][device_id]["last_prepared_bundle_id"] = bundle_id
    registry["devices"][device_id]["preferred_profile_id"] = selected_profile_id
    registry["devices"][device_id]["management_state"] = "prepared"
    save_registry(registry)
    return {"status": "success", **metadata}


def list_prepared_bundles(device_id: Optional[str] = None) -> list[dict]:
    bundles = []
    for bundle_dir in PREPARED_DIR.iterdir():
        if not bundle_dir.is_dir():
            continue
        metadata_path = _bundle_metadata_path(bundle_dir)
        if not metadata_path.exists():
            continue
        try:
            metadata = _load_json_file(metadata_path)
        except Exception:
            continue
        if device_id and metadata.get("device_id") != device_id:
            continue
        bundles.append(metadata)
    bundles.sort(key=lambda bundle: bundle.get("created_at", ""), reverse=True)
    return bundles


def get_prepared_bundle(bundle_id: str) -> Optional[dict]:
    bundle_dir = PREPARED_DIR / bundle_id
    metadata_path = _bundle_metadata_path(bundle_dir)
    if not metadata_path.exists():
        return None
    try:
        return _load_json_file(metadata_path)
    except Exception:
        return None


def install_prepared_bundle(device_id: str, bundle_id: Optional[str] = None) -> dict:
    registry = load_registry()
    raw_device = registry.get("devices", {}).get(device_id)
    if not raw_device:
        return {"error": f"Device '{device_id}' not found", "status": "failed"}

    device = _enrich_device(dict(raw_device))
    selected_bundle_id = bundle_id or device.get("last_prepared_bundle_id")
    if not selected_bundle_id:
        return {"error": "No prepared bundle selected for this device", "status": "failed"}

    bundle = get_prepared_bundle(selected_bundle_id)
    if not bundle:
        return {"error": f"Prepared bundle '{selected_bundle_id}' not found", "status": "failed"}

    profile_id = bundle.get("profile_id")
    bundle_dir = Path(bundle["bundle_dir"])
    if profile_id != "circuitpython-control":
        return {
            "status": "manual-step-required",
            "bundle_id": selected_bundle_id,
            "instructions": bundle.get("instructions", []),
            "error": "This profile currently requires manual installation.",
        }

    drive = device.get("drive")
    if not drive or not os.path.exists(drive):
        return {"error": "Target CIRCUITPY drive is not mounted", "status": "failed"}

    copied_files = []
    try:
        for file_name in ["code.py", "settings.toml", "README.txt"]:
            source_path = bundle_dir / file_name
            if not source_path.exists():
                continue
            target_path = Path(drive) / file_name
            if file_name == "code.py" and target_path.exists():
                shutil.copy2(target_path, Path(drive) / "code.py.bak")
            shutil.copy2(source_path, target_path)
            copied_files.append(str(target_path))
    except Exception as exc:
        return {"error": str(exc), "status": "failed", "drive": drive}

    registry["devices"][device_id]["agent_installed"] = True
    registry["devices"][device_id]["paired"] = True
    registry["devices"][device_id]["management_state"] = "managed"
    save_registry(registry)

    return {
        "status": "success",
        "bundle_id": selected_bundle_id,
        "drive": drive,
        "files": copied_files,
        "installed_at": _utcnow_iso(),
    }


def detect_chip_for_device(device_id: str) -> dict:
    registry = load_registry()
    raw_device = registry.get("devices", {}).get(device_id)
    if not raw_device:
        return {"error": f"Device '{device_id}' not found", "status": "failed"}

    port = raw_device.get("port")
    if not port:
        return {"error": f"Device '{device_id}' has no serial port to probe", "status": "failed"}

    detection = esp_detect_chip(port)
    if detection.get("error"):
        return {**detection, "device_id": device_id, "port": port}

    chip_name = detection.get("chip") or raw_device.get("chip") or "ESP Device"
    classification = _classify_chip_identity(
        chip_name,
        manufacturer=raw_device.get("manufacturer", ""),
        description=raw_device.get("description", ""),
    ) or {}

    family = classification.get("family") or raw_device.get("family", "unknown")
    flash_mb = raw_device.get("flash_mb") or classification.get("flash_mb") or _flash_size_to_mb(detection.get("flash_size"))
    has_npu = classification.get("npu", _family_has_npu(family))
    detected_at = _utcnow_iso()

    updated = {
        **raw_device,
        "family": family,
        "chip": chip_name,
        "flash_mb": flash_mb,
        "has_npu": has_npu,
        "status": "detected",
        "last_seen": detected_at,
        "chip_features": detection.get("features", ""),
        "chip_mac": detection.get("mac", ""),
        "last_chip_detected_at": detected_at,
    }
    registry.setdefault("devices", {})[device_id] = updated
    save_registry(registry)

    return {
        "status": "success",
        "device_id": device_id,
        "port": port,
        "chip": chip_name,
        "family": family,
        "flash_mb": flash_mb,
        "recommended_profile": _recommended_profile_id(updated),
        "device": _enrich_device(dict(updated)),
        **{key: value for key, value in detection.items() if key != "status"},
    }


# ═══════════════════════════════════════════════════════════════════
#  Full discovery orchestrator
# ═══════════════════════════════════════════════════════════════════

async def run_full_discovery(
    usb: bool = True,
    mdns: bool = True,
    neighbors: bool = True,
    ble: bool = False,
    subnet: bool = False,
    known_only: bool = False,
    known_hosts: Optional[str] = None,
    mdns_timeout: float = 5.0,
    ble_timeout: float = 10.0,
    include_low_confidence: bool = False,
) -> dict:
    all_devices: list[dict] = []
    scan_methods: list[str] = []

    if usb:
        scan_methods.append("usb")
        usb_devices = scan_usb_devices()
        all_devices.extend(usb_devices)
        all_devices.extend(scan_usb_mass_storage_devices())

        mp_boards = scan_micropython_boards(usb_devices=usb_devices)
        # Drop generic usb-* entries for ports that are already identified as
        # stable boards (registry board_id) or were identified in this scan.
        identified_ports = _known_board_ports() | {board["port"] for board in mp_boards}
        if identified_ports:
            all_devices = [
                device for device in all_devices
                if not (device.get("port") and device["port"] in identified_ports)
            ]
        if mp_boards:
            scan_methods.append("micropython")
            all_devices.extend(mp_boards)

    if mdns:
        scan_methods.append("mdns")
        all_devices.extend(scan_mdns(timeout=mdns_timeout))

    if neighbors:
        scan_methods.append("neighbors")
        all_devices.extend(await scan_network_neighbors())

    if ble:
        scan_methods.append("ble")
        all_devices.extend(await scan_ble(timeout=ble_timeout))

    if subnet:
        if known_only:
            known_targets = _parse_known_host_tokens(known_hosts)
            scan_methods.append("known-hosts")
            all_devices.extend(await scan_known_hosts(known_targets))
        else:
            scan_methods.append("subnet")
            for subnet_prefix in get_local_subnets():
                all_devices.extend(await scan_subnet(subnet_prefix))

    merge_into_registry(all_devices)
    registry_view = list_registry_devices(include_low_confidence=include_low_confidence)
    return {
        "scan_methods": scan_methods,
        "devices_found": len(all_devices),
        "total_registered": registry_view["count"],
        "hidden_low_confidence": registry_view["hidden_low_confidence"],
        "devices": registry_view["devices"],
        "last_scan": registry_view["last_scan"],
    }


# ── Auto-Poll Background Scanner ─────────────────────────────────────────

_poll_thread = None
_poll_stop = False
_poll_interval_seconds = 30


def _poll_worker():
    """Background thread that scans USB devices and updates the registry."""
    global _poll_stop
    logger.info("Fleet auto-poll worker started (interval: %ss)", _poll_interval_seconds)
    while not _poll_stop:
        try:
            # Always run USB scan (cheap and reliable)
            usb_devices = scan_usb_devices()
            usb_devices.extend(scan_usb_mass_storage_devices())

            # Probe for live MicroPython/Nirvana boards only on ports that are
            # not yet identified (skip_known=True), so we never reboot a board
            # that is already registered with a stable unique id.
            mp_boards = scan_micropython_boards(usb_devices=usb_devices, skip_known=True)
            # Drop generic usb-* entries for ports already tied to a stable id
            # (or identified in this pass) so they never duplicate the entry.
            identified_ports = _known_board_ports() | {board["port"] for board in mp_boards}
            if identified_ports:
                usb_devices = [
                    device for device in usb_devices
                    if not (device.get("port") and device["port"] in identified_ports)
                ]
            devices = usb_devices + mp_boards
            if devices:
                merge_into_registry(devices)
                logger.debug("Auto-poll: %d USB device(s) merged", len(devices))
        except Exception as e:
            logger.warning("Auto-poll error: %s", e)
        time.sleep(_poll_interval_seconds)
    logger.info("Fleet auto-poll worker stopped")


def start_auto_poll(interval_seconds: int = 30, blocking: bool = False):
    """Start background fleet scanner.

    Polls USB devices every N seconds and merges into the registry.
    Call this from backend startup (lifespan).
    """
    import threading
    global _poll_thread, _poll_stop, _poll_interval_seconds
    _poll_interval_seconds = interval_seconds
    _poll_stop = False
    if _poll_thread and _poll_thread.is_alive():
        logger.info("Auto-poll already running")
        return
    _poll_thread = threading.Thread(target=_poll_worker, daemon=True, name="fleet-poll")
    _poll_thread.start()
    if blocking:
        _poll_thread.join()
    return _poll_thread


def stop_auto_poll():
    """Stop the background fleet scanner."""
    global _poll_stop
    _poll_stop = True
    logger.info("Fleet auto-poll stop requested")
