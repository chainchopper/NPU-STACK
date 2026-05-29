"""Edge Fleet discovery, registry, and firmware preparation helpers.

This module powers the existing `/api/devices` routes and intentionally extends
the current NPU-STACK edge-device system instead of introducing a parallel
fleet subsystem.
"""

import asyncio
import json
import logging
import os
import platform
import re
import shutil
import ssl
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

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
    (0x303A, 0x4001): {"family": "esp32-p4", "chip": "ESP32-P4", "npu": True, "flash_mb": 16},
    (0x303A, 0x0010): {"family": "esp32-h2", "chip": "ESP32-H2", "npu": False, "flash_mb": 4},
    # ── UART bridge chips ──
    (0x10C4, 0xEA60): {"family": "uart-bridge", "chip": "Silicon Labs CP210x", "npu": False, "flash_mb": 0},
    (0x10C4, 0xEA70): {"family": "uart-bridge", "chip": "Silicon Labs CP2105", "npu": False, "flash_mb": 0},
    (0x1A86, 0x7523): {"family": "uart-bridge", "chip": "WCH CH340", "npu": False, "flash_mb": 0},
    (0x1A86, 0x55D4): {"family": "uart-bridge", "chip": "WCH CH9102", "npu": False, "flash_mb": 0},
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


# ── Profile catalog ──────────────────────────────────────────────

FIRMWARE_PROFILE_CATALOG = {
    "esp32-micropython-agent": {
        "id": "esp32-micropython-agent",
        "name": "ESP32 MicroPython Agent",
        "target_runtime": "micropython",
        "description": "Wi-Fi edge agent bundle for ESP32-class boards using the existing repo firmware.",
        "supported_families": ["esp32", "esp32-s2", "esp32-s3", "esp32-c3", "esp32-c6", "esp32-h2", "esp32-p4", "esp8266"],
        "install_method": "serial-or-manual-copy",
        "live_install_supported": False,
        "supports_ota": True,
    },
    "circuitpython-control": {
        "id": "circuitpython-control",
        "name": "CircuitPython Control Bundle",
        "target_runtime": "circuitpython",
        "description": "USB/Wi-Fi control bundle for CircuitPython and UF2-capable boards with direct install to mounted CIRCUITPY drives.",
        "supported_families": ["circuitpython", "rp2040", "rp2350", "nrf", "microchip"],
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


def list_firmware_profiles(device: Optional[dict] = None) -> list[dict]:
    profiles = []
    recommended = _recommended_profile_id(device or {}) if device else None
    for profile in FIRMWARE_PROFILE_CATALOG.values():
        entry = dict(profile)
        entry["recommended"] = profile["id"] == recommended
        entry["compatible"] = _profile_matches_device(profile, device) if device else True
        profiles.append(entry)
    return profiles


def _build_capabilities(device: dict) -> dict:
    family = device.get("family", "unknown")
    connection = device.get("connection", "unknown")
    status = device.get("status", "unknown")
    recommended_profile = _recommended_profile_id(device)
    live_install = connection == "usb-mass-storage" and status == "mounted"

    return {
        "pair": True,
        "prepare": recommended_profile is not None,
        "install": live_install and recommended_profile == "circuitpython-control",
        "backup": family.startswith("esp32"),
        "chip_detect": family.startswith("esp32") or family == "uart-bridge",
        "flash": family.startswith("esp32") or status == "bootsel",
        "ota": recommended_profile in {"esp32-micropython-agent", "linux-agent"},
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
    return not _is_low_confidence_device(device)


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

        identified = False
        if port.vid is not None and port.pid is not None:
            info = USB_DEVICE_MAP.get((port.vid, port.pid))
            if info:
                device.update({
                    "family": info["family"],
                    "chip": info["chip"],
                    "has_npu": info["npu"],
                    "flash_mb": info["flash_mb"],
                    "status": "detected",
                })
                identified = True

            if not identified:
                vid_info = USB_VID_MAP.get(port.vid)
                if vid_info:
                    device.update({
                        "family": vid_info["family"],
                        "chip": f"{vid_info['vendor']} Device (PID:{hex(port.pid)})",
                        "has_npu": vid_info["family"] in {"rockchip", "coral", "movidius"},
                        "flash_mb": 0,
                        "status": "detected",
                    })
                    identified = True

        if not identified:
            heuristic = _identify_by_heuristics(port.description or "", port.manufacturer or "", port.hwid or "")
            if heuristic:
                device.update({
                    "family": heuristic["family"],
                    "chip": heuristic["chip"],
                    "has_npu": heuristic["npu"],
                    "flash_mb": heuristic["flash_mb"],
                    "status": "detected",
                })
                identified = True

        if not identified:
            chip_name = port.description or port.manufacturer or "Serial Device"
            if port.vid is not None and port.pid is not None:
                chip_name += f" ({hex(port.vid)}:{hex(port.pid)})"
            device.update({
                "family": "serial",
                "chip": chip_name,
                "has_npu": False,
                "flash_mb": 0,
                "status": "detected",
            })

        devices.append(device)

    logger.info("USB scan found %s device(s)", len(devices))
    return devices


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
        merged = {
            **existing,
            **discovered_device,
            "first_seen": existing.get("first_seen") or now,
            "last_seen": now,
            "nickname": existing.get("nickname", ""),
            "notes": existing.get("notes", ""),
            "firmware_version": existing.get("firmware_version", ""),
            "agent_installed": existing.get("agent_installed", False),
            "paired": existing.get("paired", False),
            "management_state": existing.get("management_state", "paired" if existing.get("paired") else "detected"),
            "preferred_profile_id": existing.get("preferred_profile_id"),
            "last_prepared_bundle_id": existing.get("last_prepared_bundle_id"),
        }

        if _should_preserve_existing_identity(existing, discovered_device):
            for field in ("family", "chip", "has_npu", "flash_mb", "chip_features", "chip_mac", "last_chip_detected_at"):
                existing_value = existing.get(field)
                if existing_value not in (None, "", 0):
                    merged[field] = existing_value

        devices[device_id] = merged

    registry["devices"] = devices
    registry["last_scan"] = now
    save_registry(registry)
    return registry


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
        "agent_port": int(config.get("agent_port") or 9200),
        "hub_url": config.get("command_center_url", ""),
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
        f'AGENT_PORT="{int(config.get("agent_port") or 9200)}"',
        f'CIRCUITPY_WIFI_SSID="{config.get("wifi_ssid", "")}"',
        f'CIRCUITPY_WIFI_PASSWORD="{config.get("wifi_password", "")}"',
        f'COMMAND_CENTER_URL="{config.get("command_center_url", "")}"',
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
        f'NIRVANA_DEVICE_NAME="{_slugify(device_name)}"',
        f'NIRVANA_AGENT_PORT="{int(config.get("agent_port") or 9200)}"',
        f'NIRVANA_COMMAND_CENTER_URL="{config.get("command_center_url", "")}"',
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
    ble: bool = False,
    subnet: bool = False,
    known_only: bool = False,
    known_hosts: Optional[str] = None,
    mdns_timeout: float = 5.0,
    ble_timeout: float = 10.0,
) -> dict:
    all_devices: list[dict] = []
    scan_methods: list[str] = []

    if usb:
        scan_methods.append("usb")
        all_devices.extend(scan_usb_devices())
        all_devices.extend(scan_usb_mass_storage_devices())

    if mdns:
        scan_methods.append("mdns")
        all_devices.extend(scan_mdns(timeout=mdns_timeout))

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
    registry_view = list_registry_devices(include_low_confidence=False)
    return {
        "scan_methods": scan_methods,
        "devices_found": len(all_devices),
        "total_registered": registry_view["count"],
        "hidden_low_confidence": registry_view["hidden_low_confidence"],
        "devices": registry_view["devices"],
        "last_scan": registry_view["last_scan"],
    }
