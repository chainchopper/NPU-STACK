#!/usr/bin/env python3
"""
Scrape + organize Seeed XIAO / Round Display reference assets.

Downloads the public Seeed CDN assets for the XIAO ESP32-S3 (Sense) and the
1.28" Round Display carrier (pinout PNGs, photos, datasheet PDFs, schematic
ZIPs, 3D-model STLs) into backend/data/boards/assets/ and writes an
assets.json manifest plus a board JSON `assets`/`pinout_image_urls` patch.

Sources (public Seeed wiki):
    https://wiki.seeedstudio.com/xiao_esp32s3_pin_multiplexing/
    https://wiki.seeedstudio.com/get_start_round_display/

Pure stdlib (urllib) — no pip deps. Idempotent: skips files that already exist
unless --force is passed.

Usage:
    python scripts/scrape_xiao_assets.py            # download missing files
    python scripts/scrape_xiao_assets.py --force    # re-download everything
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BOARD_ID = "seeed-xiao-esp32-s3"
ASSETS_DIR = REPO_ROOT / "backend" / "data" / "boards" / "assets" / BOARD_ID
BOARD_JSON = REPO_ROOT / "backend" / "data" / "boards" / f"{BOARD_ID}.json"

USER_AGENT = "NPU-STACK/1.0 (board reference asset scraper)"

# (source_url, relative_path, label)
# category is derived from the path prefix.
ASSETS = [
    # ── XIAO ESP32-S3 Sense pinouts ──
    ("https://files.seeedstudio.com/wiki/SeeedStudio-XIAO-ESP32S3/img/XIAO_ESP32-S3_front_pinout.png",
     "pinout/XIAO_ESP32-S3_front_pinout.png", "XIAO ESP32-S3 Sense — front pinout"),
    ("https://files.seeedstudio.com/wiki/SeeedStudio-XIAO-ESP32S3/img/XIAO_ESP32-S3_back_pinout.png",
     "pinout/XIAO_ESP32-S3_back_pinout.png", "XIAO ESP32-S3 Sense — back pinout"),

    # ── Round Display pinouts ──
    ("https://files.seeedstudio.com/wiki/round_display_for_xiao/round-pinout.png",
     "round-display/round-pinout.png", "Round Display v1.0 pinout"),
    ("https://files.seeedstudio.com/wiki/round_display_for_xiao/round-display-v1.1-pinout.png",
     "round-display/round-display-v1.1-pinout.png", "Round Display v1.1 pinout"),

    # ── Round Display photos / screenshots ──
    ("https://files.seeedstudio.com/wiki/round_display_for_xiao/rounddisplay.jpg",
     "round-display/rounddisplay.jpg", "Round Display product shot"),
    ("https://files.seeedstudio.com/wiki/round_display_for_xiao/50.jpg",
     "round-display/50.jpg", "XIAO plugged into Round Display"),
    ("https://files.seeedstudio.com/wiki/round_display_for_xiao/51.jpg",
     "round-display/51.jpg", "Round Display orientation"),
    ("https://files.seeedstudio.com/wiki/round_display_for_xiao/58.png",
     "round-display/58.png", "HardwareTest menu"),
    ("https://files.seeedstudio.com/wiki/round_display_for_xiao/59.jpg",
     "round-display/59.jpg", "Round Display power switch"),
    ("https://files.seeedstudio.com/wiki/round_display_for_xiao/60.gif",
     "round-display/60.gif", "HardwareTest demo"),
    ("https://files.seeedstudio.com/wiki/round_display_for_xiao/63.png",
     "round-display/63.png", "RTC library reference"),
    ("https://files.seeedstudio.com/wiki/round_display_for_xiao/r1.png",
     "round-display/r1.png", "TFT Clock example"),
    ("https://files.seeedstudio.com/wiki/round_display_for_xiao/r3.png",
     "round-display/r3.png", "TFT Clock running"),
    ("https://files.seeedstudio.com/wiki/round_display_for_xiao/107.jpg",
     "round-display/107.jpg", "Arduino Life demo"),
    ("https://files.seeedstudio.com/wiki/round_display_for_xiao/108.png",
     "round-display/108.png", "Seeed GFX config tool"),
    ("https://files.seeedstudio.com/wiki/round_display_for_xiao/100.png",
     "round-display/100.png", "XIAO RP2040 compile settings"),
    ("https://files.seeedstudio.com/wiki/round_display_for_xiao/c1.png",
     "round-display/c1.png", "TP firmware update step 1"),
    ("https://files.seeedstudio.com/wiki/round_display_for_xiao/c2.png",
     "round-display/c2.png", "TP firmware update success"),
    ("https://files.seeedstudio.com/wiki/round_display_for_xiao/c3.png",
     "round-display/c3.png", "TP firmware update step 2"),

    # ── Datasheets (PDF) ──
    ("https://files.seeedstudio.com/wiki/round_display_for_xiao/charge-IC-datasheet.pdf",
     "datasheets/charge-IC-datasheet.pdf", "Battery charge IC datasheet"),
    ("https://files.seeedstudio.com/wiki/round_display_for_xiao/ETA3410-datasheet.pdf",
     "datasheets/ETA3410-datasheet.pdf", "ETA3410 datasheet"),
    ("https://files.seeedstudio.com/wiki/round_display_for_xiao/RTC-PCF8563-datasheet.pdf",
     "datasheets/RTC-PCF8563-datasheet.pdf", "RTC PCF8563 datasheet"),
    ("https://files.seeedstudio.com/wiki/round_display_for_xiao/GJX0128A4-15HY_Datasheet.pdf",
     "datasheets/GJX0128A4-15HY_Datasheet.pdf", "1.28\" a-Si TFT LCD datasheet"),
    ("https://files.seeedstudio.com/wiki/round_display_for_xiao/SeeedStudio_Round_Display_for_XIAO_v1.0_SCH_230308.pdf",
     "datasheets/SeeedStudio_Round_Display_for_XIAO_v1.0_SCH_230308.pdf", "Round Display v1.0 schematic"),
    ("https://files.seeedstudio.com/wiki/round_display_for_xiao/SeeedStudio_Round_Display_for_XIAO_v1.1_SCH_230407.pdf",
     "datasheets/SeeedStudio_Round_Display_for_XIAO_v1.1_SCH_230407.pdf", "Round Display v1.1 schematic"),

    # ── Schematics + PCB (ZIP) ──
    ("https://files.seeedstudio.com/wiki/round_display_for_xiao/SeeedStudio_Round_Display_for_XIAO_v1.0_SCH&PCB_230308.zip",
     "schematics/SeeedStudio_Round_Display_for_XIAO_v1.0_SCH&PCB_230308.zip", "Round Display v1.0 SCH+PCB"),
    ("https://files.seeedstudio.com/wiki/round_display_for_xiao/SeeedStudio_Round_Display_for_XIAO_v1.1_SCH&PCB_230407.zip",
     "schematics/SeeedStudio_Round_Display_for_XIAO_v1.1_SCH&PCB_230407.zip", "Round Display v1.1 SCH+PCB"),

    # ── 3D models ──
    ("https://files.seeedstudio.com/wiki/round_display_for_xiao/Round-Display-shell-3D-Model.stl",
     "3d-models/Round-Display-shell-3D-Model.stl", "Round Display shell 3D model"),
    ("https://files.seeedstudio.com/wiki/round_display_for_xiao/Seeed_Studio-XIAO-ESP32-S3-Sense-Case-With-Round-Screen.stl",
     "3d-models/Seeed_Studio-XIAO-ESP32-S3-Sense-Case-With-Round-Screen.stl",
     "XIAO ESP32-S3 Sense case with round screen 3D model"),
]


def download(url: str, dest: Path, force: bool) -> str:
    """Download url -> dest. Returns 'ok' | 'skip' | 'error:<msg>'."""
    if dest.exists() and not force:
        return "skip"
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
        dest.write_bytes(data)
        return f"ok ({len(data)} bytes)"
    except Exception as e:  # noqa: BLE001
        return f"error: {e}"


# Structured board metadata hydrated into the board JSON (local-only, since
# backend/data/ is gitignored). Kept here so a fresh clone can regenerate the
# full board page by running this script once.
BOARD_META = {
    "name": "Seeed Studio XIAO ESP32-S3 Sense",
    "display_name": "XIAO ESP32-S3 Sense",
    "chip": "ESP32-S3",
    "architecture": "xtensa",
    "compatibility": [
        "Seeed 1.28\" Round Touch Display for XIAO (GC9A01 240x240 + CHSC6X touch + PCF8563 RTC)",
        "Seeed Studio Expansion Base for XIAO (Grove, OLED, battery)",
        "All Seeed XIAO-series expansion boards (I2C/SPI/UART via D4-D10)",
        "Wio-SX1262 extension board via B2B connector (XIAO ESP32-S3 Plus only)",
        "MicroPython (ESP32_GENERIC_S3) · Nirvana OS app layer · Arduino ESP32 core · ESP-IDF",
    ],
    "requirements": [
        "Power: 5V USB-C (or 3.7V LiPo on the battery pad)",
        "Firmware: MicroPython ESP32_GENERIC_S3 + Nirvana OS app layer (flash-once, OTA)",
        "Toolchain: baked in — Arduino core + ESP-IDF available, no external install required",
        "Soldered headers required to use the D0-D10 pin functions",
        "Round Display carrier: insert XIAO with its USB-C facing outward; switch ON",
    ],
    "round_display": {
        "display": "GC9A01 240x240 SPI (65K colors)",
        "wiring": {
            "TFT CS": "D1 / GPIO2", "TFT DC": "D3 / GPIO4", "TFT BL": "D6 / GPIO43",
            "I2C SDA": "D4 / GPIO5", "I2C SCL": "D5 / GPIO6",
            "SD CS (carrier)": "D2 / GPIO3",
        },
        "touch": {
            "controller": "CHSC6X (CHSC5816) @ I2C 0x2E", "INT": "D7 / GPIO44 (active low)",
            "RST": "D0 / GPIO1 (active low)", "read_format": "[count, rsv, X, rsv, Y] 5 bytes",
        },
        "rtc": "PCF8563 @ I2C 0x51",
        "extras": ["TF card slot (32GB FAT)", "JST 1.25 battery", "charge chip", "on/off switch"],
    },
    "pinout": {
        "headers": ["Pin", "Chip Pin", "Functions"],
        "rows": [
            ["5V", "VBUS", "Power input/output"],
            ["3V3", "3V3_OUT", "Power output (700mA)"],
            ["GND", "-", "Ground"],
            ["D0", "GPIO1", "Analog / TOUCH1 / ADC · touch RST on Round Display"],
            ["D1", "GPIO2", "Analog / TOUCH2 / ADC · TFT CS on Round Display"],
            ["D2", "GPIO3", "Analog / TOUCH3 / ADC · SD CS on Round Display"],
            ["D3", "GPIO4", "Analog / TOUCH4 / ADC · TFT DC on Round Display"],
            ["D4", "GPIO5", "Analog / SDA / TOUCH5 (I2C data)"],
            ["D5", "GPIO6", "Analog / SCL / TOUCH6 (I2C clock)"],
            ["D6", "GPIO43", "TX / UART transmit · TFT BL on Round Display"],
            ["D7", "GPIO44", "RX / UART receive · touch INT on Round Display"],
            ["D8", "GPIO7", "Analog / SCK / TOUCH7 (SPI clock)"],
            ["D9", "GPIO8", "Analog / MISO / TOUCH8 (SPI data)"],
            ["D10", "GPIO9", "Analog / MOSI / TOUCH9 (SPI data)"],
            ["D11 (Sense)", "GPIO42", "Analog / TOUCH12 (no ADC) · PDM mic CLK"],
            ["D12 (Sense)", "GPIO41", "Analog / TOUCH13 (no ADC) · PDM mic DATA"],
            ["USER_LED", "GPIO21", "Onboard user LED"],
        ],
        "special": [
            ["PDM mic CLK", "GPIO42", "Onboard digital microphone clock"],
            ["PDM mic DATA", "GPIO41", "Onboard digital microphone data"],
            ["SD CS (Sense)", "GPIO3", "Onboard microSD chip select"],
            ["SD SCK / MISO / MOSI", "GPIO7 / 8 / 9", "Onboard microSD SPI"],
            ["Camera SCL / SDA", "GPIO39 / GPIO40", "OV2640/OV3660 I2C (SCCB)"],
            ["Camera DVP", "GPIO10-18, 38, 47, 48", "XMCLK / Y0-Y9 / VSYNC / HREF / PCLK"],
        ],
    },
}


def patch_board_meta() -> None:
    """Merge structured metadata into the board JSON (idempotent)."""
    if not BOARD_JSON.exists():
        print("[warn] board JSON missing — run the backend once to seed it, then re-run this script")
        return
    board = json.loads(BOARD_JSON.read_text(encoding="utf-8"))
    board.update(BOARD_META)
    BOARD_JSON.write_text(json.dumps(board, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[info] patched {BOARD_JSON.name} metadata (pinout {len(BOARD_META['pinout']['rows'])} rows)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="re-download existing files")
    args = ap.parse_args()

    manifest = {"board_id": BOARD_ID, "assets": []}
    pinout_urls = []
    ok = skip = fail = 0

    for url, rel, label in ASSETS:
        dest = ASSETS_DIR / rel
        status = download(url, dest, args.force)
        if status.startswith("ok"):
            ok += 1
            print(f"[ok]   {rel}  {status}")
        elif status == "skip":
            skip += 1
            print(f"[skip] {rel}")
        else:
            fail += 1
            print(f"[FAIL] {rel}  {status}")

        if status.startswith("ok") or status == "skip":
            category = rel.split("/", 1)[0]
            manifest["assets"].append({
                "url": url,
                "path": f"backend/data/boards/assets/{BOARD_ID}/{rel}",
                "category": category,
                "label": label,
                "ext": Path(rel).suffix.lstrip(".").lower(),
            })
            if category == "pinout":
                pinout_urls.append(f"backend/data/boards/assets/{BOARD_ID}/{rel}")

    # Write manifest
    manifest_path = ASSETS_DIR / "assets.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    # Patch the board JSON with structured metadata + asset refs
    patch_board_meta()
    if BOARD_JSON.exists():
        board = json.loads(BOARD_JSON.read_text(encoding="utf-8"))
        board["assets"] = manifest["assets"]
        if pinout_urls:
            board["pinout_image_urls"] = pinout_urls
        board["assets_manifest"] = f"backend/data/boards/assets/{BOARD_ID}/assets.json"
        BOARD_JSON.write_text(json.dumps(board, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[info] patched {BOARD_JSON.name} with {len(manifest['assets'])} assets")

    print(f"\nDone: {ok} downloaded, {skip} skipped, {fail} failed.")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
