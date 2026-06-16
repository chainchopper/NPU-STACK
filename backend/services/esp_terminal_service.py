"""ESP Serial Terminal Service — COM port detection, serial I/O, and WebSocket bridge.

Provides serial port discovery (Windows COM ports, Linux /dev/tty*) and a
WebSocket-based serial terminal for ESP devices connected via USB.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("esp_terminal")

# Try to import pyserial (optional — terminal disabled if missing)
try:
    import serial
    import serial.tools.list_ports

    HAS_PYSERIAL = True
except ImportError:
    HAS_PYSERIAL = False
    logger.warning("pyserial not installed — ESP serial terminal disabled. Install with: pip install pyserial")

# ── Serial Port Discovery ─────────────────────────────────────────────────

# Known ESP USB VID:PID pairs
ESP_VIDS = {0x303A, 0x10C4, 0x1A86, 0x0403}  # Espressif, CP210x, CH340, FTDI
ESP_PID_PREFIXES = {
    0x303A: None,  # All Espressif native USB
    0x10C4: {0xEA60, 0xEA70, 0xEA71, 0xEA80, 0xEA61, 0x8470, 0x8471, 0x8472, 0x8477},  # CP210x family
    0x1A86: {0x7523, 0x55D4, 0x7522, 0x55D3, 0x55D2},  # CH340/CH343/CH9102
    0x0403: {0x6001, 0x6015, 0x6010, 0x6011, 0x6014},  # FT232/FT231/FT230X
}

# VID-only heuristics: if description contains these, it's likely an ESP bridge
ESP_DESCRIPTION_KEYWORDS = [
    "cp210", "ch340", "ch343", "ch9102", "ft232", "ft231",
    "esp", "esp32", "esp8266", "espressif", "wemos", "nodemcu",
    "d32", "d1 mini", "lolin", "heltec", "ttgo", "m5stack",
]

# Full VID range for common ESP bridge chips (any PID, keyword-based)
ESP_BRIDGE_VIDS = {0x10C4, 0x1A86, 0x0403, 0x239A}  # CP210x, CH34x, FTDI, Adafruit

# ── Multi-family flash method detection ──────────────────────────────

# VID:PID → (family, flash_method, toolchain_label)
FLASH_METHOD_MAP: dict[tuple[int, int], tuple[str, str, str]] = {
    # ── Espressif (esptool) ──
    (0x303A, None): ("esp", "esptool", "esptool.py"),
    # ── RP2040/RP2350 (UF2 mass-storage) ──
    (0x2E8A, 0x0003): ("rp2040", "uf2", "UF2 Bootloader"),
    (0x2E8A, 0x0005): ("rp2040", "uf2", "UF2 Bootloader"),
    (0x2E8A, 0x000A): ("rp2040", "uf2", "UF2 Bootloader (CDC)"),
    (0x2E8A, 0x000F): ("rp2350", "uf2", "UF2 Bootloader"),
    (0x2E8A, 0x0004): ("rp2040", "uf2", "UF2 (MicroPython)"),
    (0x2E8A, 0x0009): ("rp2040", "uf2", "UF2 (CircuitPython)"),
    # Adafruit RP2040 boards
    (0x239A, 0x80EB): ("rp2040", "uf2", "UF2 Bootloader"),
    (0x239A, 0x8018): ("rp2040", "uf2", "UF2 Bootloader"),
    # Arduino Nano RP2040
    (0x2341, 0x804E): ("rp2040", "uf2", "UF2 Bootloader"),
    # ── Rockchip / LuckFox (rockusb / rkdeveloptool) ──
    (0x2207, 0x0006): ("rockchip", "rockusb", "rkdeveloptool"),
    (0x2207, 0x320A): ("rockchip", "rockusb", "rkdeveloptool"),
    (0x2207, 0x330C): ("rockchip", "rockusb", "rkdeveloptool"),
}

# VID-level fallback for flash method
FLASH_VID_FALLBACK: dict[int, tuple[str, str, str]] = {
    0x303A: ("esp", "esptool", "esptool.py"),
    0x2E8A: ("rp2040", "uf2", "UF2 Bootloader"),
    0x2207: ("rockchip", "rockusb", "rkdeveloptool"),
    0x239A: ("rp2040", "uf2", "UF2 Bootloader"),  # Adafruit
}

# Family-level flash method (for fleet devices that may not have VID/PID)
FAMILY_FLASH_MAP: dict[str, tuple[str, str]] = {
    "esp32": ("esptool", "esptool.py"),
    "esp32-s2": ("esptool", "esptool.py"),
    "esp32-s3": ("esptool", "esptool.py"),
    "esp32-c3": ("esptool", "esptool.py"),
    "esp32-c6": ("esptool", "esptool.py"),
    "esp32-h2": ("esptool", "esptool.py"),
    "esp32-p4": ("esptool", "esptool.py"),
    "esp8266": ("esptool", "esptool.py"),
    "rp2040": ("uf2", "UF2 Bootloader"),
    "rp2350": ("uf2", "UF2 Bootloader"),
    "circuitpython": ("uf2", "UF2 / CircuitPython"),
    "rockchip": ("rockusb", "rkdeveloptool"),
    "luckfox": ("rockusb", "rkdeveloptool / scp"),
    "allwinner": ("fel", "sunxi-fel"),
    "rpi-sbc": ("scp", "SSH / SCP"),
    "nvidia": ("scp", "SSH / SCP"),
}

# ── Build command templates per flash method ─────────────────────────

BUILD_COMMAND_TEMPLATES: dict[str, dict[str, str]] = {
    "esptool": {
        "set_target": "idf.py set-target {target}",
        "build": "idf.py build",
        "flash": "idf.py -p {port} flash",
        "monitor": "idf.py -p {port} monitor",
        "full": "idf.py set-target {target} && idf.py build && idf.py -p {port} flash",
    },
    "uf2": {
        "build": "cmake -B build -G Ninja && cmake --build build",
        "flash": "Copy {firmware}.uf2 to RPI-RP2 drive or use: picotool load {firmware}.uf2 -f",
        "monitor": "picocom -b 115200 {port}",
        "full": "cmake -B build -G Ninja && cmake --build build && picotool load build/{firmware}.uf2 -f",
    },
    "rockusb": {
        "build": "make -j$(nproc) CROSS_COMPILE=aarch64-linux-gnu-",
        "flash": "rkdeveloptool db MiniLoaderAll.bin && rkdeveloptool wl 0x0 {firmware}.img && rkdeveloptool rd",
        "monitor": "picocom -b 1500000 {port}",
        "full": "make -j$(nproc) && rkdeveloptool db MiniLoaderAll.bin && rkdeveloptool wl 0x0 {firmware}.img",
    },
    "scp": {
        "build": "make -j$(nproc) CROSS_COMPILE=aarch64-linux-gnu-",
        "flash": "scp {firmware}.bin root@{ip}:/tmp/ && ssh root@{ip} 'install-firmware /tmp/{firmware}.bin'",
        "monitor": "ssh root@{ip} 'journalctl -u edge-agent -f'",
        "full": "make -j$(nproc) && scp {firmware}.bin root@{ip}:/tmp/ && ssh root@{ip} 'install-firmware /tmp/{firmware}.bin'",
    },
    "fel": {
        "build": "make -j$(nproc) CROSS_COMPILE=arm-linux-gnueabihf-",
        "flash": "sunxi-fel -p spiflash-write 0 {firmware}.bin",
        "monitor": "picocom -b 115200 {port}",
        "full": "make -j$(nproc) && sunxi-fel -p spiflash-write 0 {firmware}.bin",
    },
}


def _detect_flash_method(vid: int | None, pid: int | None, desc: str = "") -> tuple[str, str, str]:
    """Resolve (family_label, flash_method, toolchain_label) from VID/PID or description."""
    desc_lower = desc.lower()

    # Exact VID:PID match
    if vid is not None and pid is not None:
        key = (vid, pid)
        if key in FLASH_METHOD_MAP:
            return FLASH_METHOD_MAP[key]
        # VID-wildcard match
        wild_key = (vid, None)
        if wild_key in FLASH_METHOD_MAP:
            return FLASH_METHOD_MAP[wild_key]

    # VID-level fallback
    if vid is not None and vid in FLASH_VID_FALLBACK:
        return FLASH_VID_FALLBACK[vid]

    # Description heuristics
    for kw, method in [
        (["esp32", "esp8266", "espressif"], ("esp", "esptool", "esptool.py")),
        (["rp2040", "rp2350", "pico", "circuitpython"], ("rp2040", "uf2", "UF2 Bootloader")),
        (["rockchip", "luckfox", "rk3588", "rk3566"], ("rockchip", "rockusb", "rkdeveloptool")),
        (["allwinner", "sunxi"], ("allwinner", "fel", "sunxi-fel")),
    ]:
        if any(k in desc_lower for k in kw):
            return method

    return ("unknown", "unknown", "N/A")


def resolve_flash_method(family: str | None, chip: str | None = None) -> tuple[str, str]:
    """Resolve (flash_method, toolchain_label) from a device family string.
    Works for fleet devices that may not have USB VID/PID."""
    if family and family.lower() in FAMILY_FLASH_MAP:
        return FAMILY_FLASH_MAP[family.lower()]
    if chip and any(k in (chip or "").lower() for k in ["rp2040", "rp2350"]):
        return ("uf2", "UF2 Bootloader")
    if chip and any(k in (chip or "").lower() for k in ["rockchip", "luckfox", "rk"]):
        return ("rockusb", "rkdeveloptool")
    return ("unknown", "N/A")


def list_serial_ports() -> Dict[str, Any]:
    """List all serial ports with ESP device detection and flash method tagging."""
    if not HAS_PYSERIAL:
        return {"ports": [], "count": 0, "error": "pyserial not installed", "esp_ports": []}

    ports = []
    esp_ports = []

    for p in serial.tools.list_ports.comports():
        is_esp = False
        chip_guess = None
        desc_lower = (p.description or "").lower()
        family_label = "unknown"

        # Method 1: Exact VID:PID match
        if p.vid is not None and p.pid is not None:
            if p.vid in ESP_VIDS:
                allowed = ESP_PID_PREFIXES.get(p.vid)
                if allowed is None or p.pid in allowed:
                    is_esp = True

            # Chip family guess
            if p.vid == 0x303A:
                chip_guess = _esp32_chip_from_pid(p.pid)

        # Method 2: Bridge chip + description keyword match (CP210x, CH340, FTDI on ESP boards)
        if not is_esp and p.vid is not None and p.vid in ESP_BRIDGE_VIDS:
            if any(kw in desc_lower for kw in ESP_DESCRIPTION_KEYWORDS):
                is_esp = True
            hwid_lower = (p.hwid or "").lower()
            if any(kw in hwid_lower for kw in ESP_DESCRIPTION_KEYWORDS):
                is_esp = True

        # Method 3: Pure description heuristic
        if not is_esp and any(kw in desc_lower for kw in ["esp32", "esp8266", "espressif", "wemos d1", "nodemcu"]):
            is_esp = True

        # Detect flash method
        family_label, flash_method, toolchain = _detect_flash_method(p.vid, p.pid, p.description or "")

        port_info = {
            "device": p.device,
            "name": p.name or p.device,
            "description": p.description or "",
            "hwid": p.hwid or "",
            "vid": f"0x{p.vid:04X}" if p.vid is not None else None,
            "pid": f"0x{p.pid:04X}" if p.pid is not None else None,
            "serial_number": p.serial_number or "",
            "manufacturer": p.manufacturer or "",
            "is_esp": is_esp,
            "chip": chip_guess,
            "family": family_label,
            "flash_method": flash_method,
            "toolchain": toolchain,
        }

        ports.append(port_info)
        if is_esp:
            esp_ports.append(port_info)

    return {
        "ports": ports,
        "count": len(ports),
        "esp_ports": esp_ports,
        "esp_count": len(esp_ports),
        "pyserial_available": True,
    }


def _esp32_chip_from_pid(pid: int) -> Optional[str]:
    """Guess ESP32 chip variant from USB PID."""
    pid_map = {
        0x1001: "ESP32-S2",
        0x1002: "ESP32-S3",
        0x1003: "ESP32-C3",
        0x1004: "ESP32-C6",
        0x1005: "ESP32-H2",
        0x1006: "ESP32-P4",
        0x1000: "ESP32",
    }
    return pid_map.get(pid)


def get_port_info(device: str) -> Optional[Dict[str, Any]]:
    """Get detailed info for a specific serial port."""
    if not HAS_PYSERIAL:
        return None
    for p in serial.tools.list_ports.comports():
        if p.device == device:
            return {
                "device": p.device,
                "name": p.name or p.device,
                "description": p.description or "",
                "baud_rate": 115200,
                "vid": f"0x{p.vid:04X}" if p.vid is not None else None,
                "pid": f"0x{p.pid:04X}" if p.pid is not None else None,
                "serial_number": p.serial_number or "",
            }
    return None


# ── Serial Connection Manager ────────────────────────────────────────────

class SerialConnection:
    """Manages an open serial connection with read loop."""

    def __init__(self, device: str, baud: int = 115200):
        self.device = device
        self.baud = baud
        self._ser: Optional[serial.Serial] = None
        self._read_thread: Optional[threading.Thread] = None
        self._running = False
        self._on_data: Optional[callable] = None  # async callback(bytes)

    @property
    def is_open(self) -> bool:
        return self._ser is not None and self._ser.is_open

    def open(self) -> bool:
        if not HAS_PYSERIAL:
            return False
        try:
            self._ser = serial.Serial(
                port=self.device,
                baudrate=self.baud,
                timeout=0.1,
                write_timeout=2.0,
            )
            self._running = True
            self._read_thread = threading.Thread(target=self._read_loop, daemon=True)
            self._read_thread.start()
            return True
        except Exception as e:
            logger.error(f"Failed to open {self.device}: {e}")
            return False

    def close(self):
        self._running = False
        if self._read_thread:
            self._read_thread.join(timeout=2)
        if self._ser and self._ser.is_open:
            try:
                self._ser.close()
            except Exception:
                pass
        self._ser = None

    def write(self, data: bytes) -> int:
        if not self._ser or not self._ser.is_open:
            return 0
        try:
            return self._ser.write(data)
        except Exception as e:
            logger.error(f"Serial write error: {e}")
            return 0

    def set_on_data(self, callback):
        """Set async callback for received data."""
        self._on_data = callback

    def _read_loop(self):
        """Background read loop — calls on_data callback."""
        loop = asyncio.new_event_loop()
        while self._running and self._ser and self._ser.is_open:
            try:
                if self._ser.in_waiting > 0:
                    data = self._ser.read(self._ser.in_waiting)
                    if data and self._on_data:
                        asyncio.run_coroutine_threadsafe(self._on_data(data), loop)
                else:
                    time.sleep(0.01)
            except Exception as e:
                logger.error(f"Serial read error: {e}")
                break
        loop.close()


# ── Connection Pool ──────────────────────────────────────────────────────

_connections: Dict[str, SerialConnection] = {}
_conn_lock = threading.Lock()


def get_or_create_connection(device: str, baud: int = 115200) -> SerialConnection:
    with _conn_lock:
        if device in _connections:
            conn = _connections[device]
            if conn.is_open:
                return conn
            # Reconnect
            conn.close()
        conn = SerialConnection(device, baud)
        if conn.open():
            _connections[device] = conn
        return conn


def close_connection(device: str):
    with _conn_lock:
        conn = _connections.pop(device, None)
        if conn:
            conn.close()


def close_all_connections():
    with _conn_lock:
        for conn in _connections.values():
            conn.close()
        _connections.clear()
