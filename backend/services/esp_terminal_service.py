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
    0x10C4: {0xEA60},  # CP2102
    0x1A86: {0x7523, 0x55D4},  # CH340/CH343
    0x0403: {0x6001, 0x6015},  # FT232/FT231
}


def list_serial_ports() -> Dict[str, Any]:
    """List all serial ports with ESP device detection."""
    if not HAS_PYSERIAL:
        return {"ports": [], "count": 0, "error": "pyserial not installed", "esp_ports": []}

    ports = []
    esp_ports = []

    for p in serial.tools.list_ports.comports():
        is_esp = False
        chip_guess = None

        if p.vid is not None and p.pid is not None:
            if p.vid in ESP_VIDS:
                allowed = ESP_PID_PREFIXES.get(p.vid)
                if allowed is None or p.pid in allowed:
                    is_esp = True

            # Chip family guess
            if p.vid == 0x303A:
                chip_guess = _esp32_chip_from_pid(p.pid)

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
