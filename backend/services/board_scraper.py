"""Board Database — structured metadata for supported NPU-STACK boards.

Each board entry lives as a JSON file in backend/data/boards/.
Boards can be scraped from manufacturers or added manually.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
BOARDS_DIR = REPO_ROOT / "backend" / "data" / "boards"

BOARD_MANUFACTURERS: Dict[str, Dict[str, Any]] = {
    "adafruit": {
        "name": "Adafruit",
        "base_url": "https://www.adafruit.com",
        "search_url": "https://www.adafruit.com/api/search/?q={query}",
        "product_url": "https://www.adafruit.com/product/{pid}",
    },
    "sparkfun": {
        "name": "SparkFun",
        "base_url": "https://www.sparkfun.com",
        "search_url": "https://www.sparkfun.com/search/results?term={query}",
    },
    "seedstudio": {
        "name": "Seeed Studio",
        "base_url": "https://www.seeedstudio.com",
        "search_url": "https://www.seeedstudio.com/catalogsearch/result/?q={query}",
    },
    "waveshare": {
        "name": "Waveshare",
        "base_url": "https://www.waveshare.com",
        "search_url": "https://www.waveshare.com/catalogsearch/result/?q={query}",
    },
    "raspberrypi": {
        "name": "Raspberry Pi",
        "base_url": "https://www.raspberrypi.com",
        "docs_url": "https://datasheets.raspberrypi.com",
    },
    "espressif": {
        "name": "Espressif",
        "base_url": "https://www.espressif.com",
        "docs_url": "https://docs.espressif.com/projects/esp-idf/en/latest",
    },
    "arduino": {
        "name": "Arduino",
        "base_url": "https://www.arduino.cc",
        "docs_url": "https://docs.arduino.cc",
    },
    "google": {
        "name": "Google Coral",
        "base_url": "https://coral.ai",
        "docs_url": "https://coral.ai/docs",
    },
}

# ── Canonical board catalog (pre-populated, extended by scraper) ──
CANONICAL_BOARDS: List[Dict[str, Any]] = [
    # ── Raspberry Pi ──
    {
        "id": "rpi5",
        "name": "Raspberry Pi 5",
        "manufacturer": "raspberrypi",
        "chip": "BCM2712",
        "architecture": "aarch64",
        "specs": {"cpu": "Quad Cortex-A76 @ 2.4GHz", "ram": "4/8 GB LPDDR4X", "gpu": "VideoCore VII", "wifi": "802.11ac", "bt": "5.0/BLE"},
        "features": ["GPIO 40-pin", "PCIe 2.0 x1", "MIPI CSI/DSI", "USB 3.0", "Gigabit Ethernet", "RTC"],
        "npu_stack_ops": ["pair", "terminal", "flash-sd", "fleet-enroll", "benchmark", "nirvana-chat"],
        "pinout_url": "https://pinout.xyz",
        "docs_url": "https://www.raspberrypi.com/documentation",
        "image_urls": [],
        "tags": ["sbc", "linux", "gpio", "ai"],
    },
    {
        "id": "rpi-pico2-w",
        "name": "Raspberry Pi Pico 2 W",
        "manufacturer": "raspberrypi",
        "chip": "RP2350",
        "architecture": "arm",
        "specs": {"cpu": "Dual Cortex-M33 + Dual RISC-V @ 150MHz", "ram": "520 KB SRAM", "flash": "4 MB", "wifi": "802.11n", "bt": "5.2/BLE"},
        "features": ["GPIO 26-pin", "PIO", "USB OTG", "ADC", "Temperature Sensor"],
        "npu_stack_ops": ["pair", "terminal", "flash-uf2", "fleet-enroll", "nirvana-chat"],
        "docs_url": "https://datasheets.raspberrypi.com/picow/pico-2-w-datasheet.pdf",
        "image_urls": [],
        "tags": ["microcontroller", "rp2350", "wifi", "ble", "pio"],
    },
    # ── ESP32 Family ──
    {
        "id": "esp32-s3-devkitc",
        "name": "ESP32-S3-DevKitC-1",
        "manufacturer": "espressif",
        "chip": "ESP32-S3",
        "architecture": "xtensa",
        "specs": {"cpu": "Dual Xtensa LX7 @ 240MHz", "ram": "512 KB SRAM", "flash": "8/16 MB", "wifi": "802.11b/g/n", "bt": "5.0/BLE"},
        "features": ["GPIO 36-pin", "USB OTG/JTAG", "AI Accelerator", "PSRAM", "LCD Interface", "Camera Interface"],
        "npu_stack_ops": ["pair", "terminal", "flash-esptool", "esp-now", "fleet-enroll", "nirvana-chat", "gpio-control", "blink"],
        "docs_url": "https://docs.espressif.com/projects/esp-idf/en/latest/esp32s3",
        "image_urls": [],
        "tags": ["esp32", "wifi", "ble", "ai-accelerator", "iot"],
    },
    {
        "id": "esp32-c6-devkitc",
        "name": "ESP32-C6-DevKitC-1",
        "manufacturer": "espressif",
        "chip": "ESP32-C6",
        "architecture": "riscv",
        "specs": {"cpu": "RISC-V 32-bit @ 160MHz", "ram": "512 KB SRAM", "flash": "8 MB", "wifi": "802.11ax (Wi-Fi 6)", "bt": "5.3/BLE", "ieee": "802.15.4 (Thread/Zigbee)"},
        "features": ["GPIO 30-pin", "USB Serial/JTAG", "Wi-Fi 6", "Thread", "Zigbee", "Matter"],
        "npu_stack_ops": ["pair", "terminal", "flash-esptool", "fleet-enroll", "nirvana-chat", "blink"],
        "docs_url": "https://docs.espressif.com/projects/esp-idf/en/latest/esp32c6",
        "image_urls": [],
        "tags": ["esp32", "wifi6", "thread", "zigbee", "matter", "riscv"],
    },
    # ── Arduino ──
    {
        "id": "arduino-nano-esp32",
        "name": "Arduino Nano ESP32",
        "manufacturer": "arduino",
        "chip": "ESP32-S3",
        "architecture": "xtensa",
        "specs": {"cpu": "Dual Xtensa LX7 @ 240MHz", "ram": "512 KB SRAM", "flash": "16 MB", "wifi": "802.11b/g/n", "bt": "5.0/BLE"},
        "features": ["GPIO 14-pin", "USB-C", "RGB LED", "Arduino Cloud", "MicroPython"],
        "npu_stack_ops": ["pair", "terminal", "flash-esptool", "fleet-enroll", "blink", "nirvana-chat"],
        "docs_url": "https://docs.arduino.cc/hardware/nano-esp32",
        "image_urls": [],
        "tags": ["arduino", "esp32", "micropython", "nano"],
    },
    # ── Google Coral ──
    {
        "id": "coral-dev-board",
        "name": "Google Coral Dev Board",
        "manufacturer": "google",
        "chip": "NXP i.MX 8M + Edge TPU",
        "architecture": "aarch64",
        "specs": {"cpu": "Quad Cortex-A53 + Cortex-M4F", "ram": "1/4 GB LPDDR4", "tpu": "Edge TPU (4 TOPS)", "wifi": "802.11ac", "bt": "5.0"},
        "features": ["Edge TPU", "GPIO 40-pin", "MIPI CSI/DSI", "USB 3.0", "Gigabit Ethernet", "HDMI 2.0a"],
        "npu_stack_ops": ["pair", "terminal", "benchmark-tpu", "fleet-enroll", "nirvana-chat"],
        "docs_url": "https://coral.ai/docs/dev-board",
        "image_urls": [],
        "tags": ["tpu", "edge-ai", "ml-accelerator", "sbc"],
    },
    # ── Adafruit ──
    {
        "id": "adafruit-qt-py-esp32-s3",
        "name": "Adafruit QT Py ESP32-S3",
        "manufacturer": "adafruit",
        "chip": "ESP32-S3",
        "architecture": "xtensa",
        "specs": {"cpu": "Dual Xtensa LX7 @ 240MHz", "ram": "2 MB PSRAM", "flash": "8 MB", "wifi": "802.11b/g/n", "bt": "5.0/BLE"},
        "features": ["GPIO 13-pin", "USB-C", "STEMMA QT", "RGB NeoPixel", "CircuitPython"],
        "npu_stack_ops": ["pair", "terminal", "flash-uf2", "fleet-enroll", "blink", "nirvana-chat"],
        "docs_url": "https://learn.adafruit.com/adafruit-qt-py-esp32-s3",
        "image_urls": [],
        "tags": ["adafruit", "circuitpython", "esp32", "stemma-qt", "tiny"],
    },
    {
        "id": "adafruit-metro-esp32-s3",
        "name": "Adafruit Metro ESP32-S3",
        "manufacturer": "adafruit",
        "chip": "ESP32-S3",
        "architecture": "xtensa",
        "specs": {"cpu": "Dual Xtensa LX7 @ 240MHz", "ram": "2 MB PSRAM", "flash": "16 MB", "wifi": "802.11b/g/n", "bt": "5.0/BLE"},
        "features": ["GPIO 21-pin", "USB-C", "Arduino Uno form factor", "CircuitPython", "5V logic compatible"],
        "npu_stack_ops": ["pair", "terminal", "flash-uf2", "fleet-enroll", "blink", "nirvana-chat"],
        "docs_url": "https://learn.adafruit.com/adafruit-metro-esp32-s3",
        "image_urls": [],
        "tags": ["adafruit", "circuitpython", "esp32", "metro", "arduino-compatible"],
    },
    # ── Seeed Studio ──
    {
        "id": "seeed-xiao-esp32-s3",
        "name": "Seeed Studio XIAO ESP32S3",
        "manufacturer": "seedstudio",
        "chip": "ESP32-S3",
        "architecture": "xtensa",
        "specs": {"cpu": "Dual Xtensa LX7 @ 240MHz", "ram": "8 MB PSRAM", "flash": "8 MB", "wifi": "802.11b/g/n", "bt": "5.0/BLE"},
        "features": ["GPIO 11-pin", "USB-C", "Battery support", "MicroSD", "Camera Sensor interface"],
        "npu_stack_ops": ["pair", "terminal", "flash-esptool", "fleet-enroll", "blink", "nirvana-chat"],
        "docs_url": "https://wiki.seeedstudio.com/XIAO_ESP32S3",
        "image_urls": [],
        "tags": ["seeed", "xiao", "esp32", "tiny", "camera"],
    },
    # ── Waveshare ──
    {
        "id": "waveshare-esp32-s3-touch-lcd",
        "name": "Waveshare ESP32-S3 Touch LCD",
        "manufacturer": "waveshare",
        "chip": "ESP32-S3",
        "architecture": "xtensa",
        "specs": {"cpu": "Dual Xtensa LX7 @ 240MHz", "ram": "8 MB PSRAM", "flash": "16 MB", "display": "3.5\" 480x320 TFT Touch", "wifi": "802.11b/g/n", "bt": "5.0/BLE"},
        "features": ["3.5\" Touch LCD", "GPIO", "USB-C", "SD Card", "Speaker", "Battery", "IMU"],
        "npu_stack_ops": ["pair", "terminal", "flash-esptool", "fleet-enroll", "nirvana-chat", "display-test"],
        "docs_url": "https://www.waveshare.com/wiki/ESP32-S3-Touch-LCD-3.5",
        "image_urls": [],
        "tags": ["waveshare", "esp32", "lcd", "touch", "display"],
    },
    # ── SparkFun ──
    {
        "id": "sparkfun-thing-plus-esp32-s3",
        "name": "SparkFun Thing Plus ESP32-S3",
        "manufacturer": "sparkfun",
        "chip": "ESP32-S3",
        "architecture": "xtensa",
        "specs": {"cpu": "Dual Xtensa LX7 @ 240MHz", "ram": "8 MB PSRAM", "flash": "16 MB", "wifi": "802.11b/g/n", "bt": "5.0/BLE"},
        "features": ["GPIO 22-pin", "USB-C", "Qwiic connector", "LiPo charger", "MicroSD", "RGB LED"],
        "npu_stack_ops": ["pair", "terminal", "flash-esptool", "fleet-enroll", "blink", "nirvana-chat"],
        "docs_url": "https://learn.sparkfun.com/tutorials/esp32-s3-thing-plus-hookup-guide",
        "image_urls": [],
        "tags": ["sparkfun", "esp32", "qwiic", "thing-plus"],
    },
]


def ensure_boards_dir() -> Path:
    """Ensure the boards data directory exists, seed canonical boards if empty."""
    BOARDS_DIR.mkdir(parents=True, exist_ok=True)
    existing = list(BOARDS_DIR.glob("*.json"))
    if not existing:
        for board in CANONICAL_BOARDS:
            board["created_at"] = datetime.now().isoformat()
            board["updated_at"] = board["created_at"]
            path = BOARDS_DIR / f"{board['id']}.json"
            path.write_text(json.dumps(board, indent=2, ensure_ascii=False), encoding="utf-8")
    return BOARDS_DIR


def list_boards(manufacturer: Optional[str] = None, tag: Optional[str] = None) -> List[Dict[str, Any]]:
    """List all boards, optionally filtered by manufacturer or tag."""
    boards = []
    for path in sorted(BOARDS_DIR.glob("*.json")):
        try:
            board = json.loads(path.read_text(encoding="utf-8"))
            if manufacturer and board.get("manufacturer") != manufacturer:
                continue
            if tag and tag not in board.get("tags", []):
                continue
            boards.append(board)
        except Exception:
            pass
    return boards


def get_board(board_id: str) -> Optional[Dict[str, Any]]:
    """Get a single board by ID."""
    path = BOARDS_DIR / f"{board_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_board(board: Dict[str, Any]) -> Dict[str, Any]:
    """Create or update a board entry."""
    board_id = board.get("id") or f"board-{uuid.uuid4().hex[:8]}"
    board["id"] = board_id
    board["updated_at"] = datetime.now().isoformat()
    if "created_at" not in board:
        board["created_at"] = board["updated_at"]
    path = BOARDS_DIR / f"{board_id}.json"
    path.write_text(json.dumps(board, indent=2, ensure_ascii=False), encoding="utf-8")
    return board


def delete_board(board_id: str) -> bool:
    """Delete a board entry."""
    path = BOARDS_DIR / f"{board_id}.json"
    if path.exists():
        path.unlink()
        return True
    return False


async def scrape_manufacturer_pages(query: str = "") -> List[Dict[str, Any]]:
    """Lightweight HTTP scraper for manufacturer product pages.
    
    Tries to find board datasheets, pinout diagrams, and specification pages
    from known manufacturer sites. Uses httpx for HTTP requests.
    """
    results = []
    
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        for mfr_key, mfr in BOARD_MANUFACTURERS.items():
            if "search_url" not in mfr:
                continue
            try:
                url = mfr["search_url"].format(query=query or mfr_key)
                resp = await client.get(url, headers={"User-Agent": "NPU-STACK/1.0 Board Scraper"})
                if resp.status_code == 200:
                    results.append({
                        "manufacturer": mfr["name"],
                        "url": url,
                        "status": resp.status_code,
                        "note": f"Fetched {len(resp.text)} bytes",
                    })
            except Exception as e:
                results.append({"manufacturer": mfr["name"], "url": url, "error": str(e)})
    
    return results


# ── Initialize on import ──
ensure_boards_dir()
