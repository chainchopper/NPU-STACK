"""NPU-STACK Internal — Bulk Board Image Scraper

Pulls product images from multiple sources in parallel batches.
Targets: Adafruit, DigiKey, Seeed Studio, Espressif, Raspberry Pi, Orange Pi,
         Radxa, Waveshare, M5Stack, LilyGO

Strategy:
- Uses each source's product listing / API for structured image URLs
- Downloads in parallel batches (8 concurrent workers)
- Organizes by: vendor/board_name/image_<index>.jpg
- Saves metadata JSON per vendor for training catalog
- Stores everything in internal/datasets/boards/

NOT for public repo — this is internal training data pipeline.
"""

import concurrent.futures
import json
import os
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

INTERNAL_DIR = Path(__file__).resolve().parents[1] if "__file__" in dir() else Path("J:/NPU-STACK/internal")
OUTPUT_DIR = INTERNAL_DIR / "datasets" / "boards"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MAX_WORKERS = 8
REQUEST_TIMEOUT = 15
USER_AGENT = "NPU-STACK-Board-Catalog/1.0 (internal training data pipeline)"

# ── Known Product Image URL patterns ─────────────────────────────────────

# Many vendors use predictable URL patterns for product images
BOARD_SOURCES = {
    "adafruit": {
        "base_url": "https://cdn-shop.adafruit.com/970x728/",
        "products_file": "https://www.adafruit.com/api/products?limit=200",
        "image_pattern": "{product_id}-00.jpg",  # Primary product photo
        "type": "api",
        "headers": {"User-Agent": USER_AGENT},
    },
    "seeed": {
        "base_url": "https://files.seeedstudio.com/wiki/",
        "boards_manifest": [
            # XIAO Series
            ("Seeeduino-XIAO-ESP32S3/img/", "xiao_esp32s3_sense"),
            ("Seeeduino-XIAO-ESP32S3/img/", "xiao_esp32s3"),
            ("Seeeduino-XIAO-ESP32C3/img/", "xiao_esp32c3"),
            ("round_display_for_xiao/", "round_display"),
            # Grove Vision
            ("grove-vision-ai-v2/", "grove_vision_ai_v2"),
        ],
        "type": "wiki",
    },
    "espressif": {
        "boards_manifest": [
            ("https://docs.espressif.com/projects/esp-dev-kits/en/latest/_static/", [
                "esp32-s3-devkitc-1-v1.1-layout.png",
                "esp32-s3-box-3.png",
                "esp32-c3-devkitm-1-v1.0.png",
                "esp32-s2-saola-1-v1.2.png",
                "esp32-p4-function-ev-board-v1.0.png",
            ]),
        ],
        "type": "static",
    },
    "raspberrypi": {
        "boards_manifest": [
            ("https://www.raspberrypi.com/app/uploads/2023/03/", [
                "raspberry-pi-5.jpg",
                "raspberry-pi-4-model-b.jpg",
                "raspberry-pi-zero-2-w.jpg",
                "raspberry-pi-pico-w.jpg",
                "raspberry-pi-pico-2.jpg",
            ]),
        ],
        "type": "static",
    },
    "orangepi": {
        "boards_manifest": [
            ("https://www.orangepi.org/img/", [
                "orangepi-5-plus.png",
                "orangepi-5.png",
                "orangepi-3b.png",
                "orangepi-zero2w.png",
                "orangepi-zero3.png",
            ]),
        ],
        "type": "static",
    },
    "digikey": {
        "type": "scrape",
        "search_url": "https://www.digikey.com/en/products/filter/single-board-computers-sbcs-computer-on-module-com/933",
        "note": "Requires headless browser (Playwright) — use separate script",
    },
    "radxa": {
        "boards_manifest": [
            ("https://wiki.radxa.com/images/", [
                "rock-5b-plus.png",
                "rock-5a.png",
                "rock-3c.png",
                "zero-3w.png",
            ]),
        ],
        "type": "static",
    },
    "waveshare": {
        "boards_manifest": [
            ("https://www.waveshare.com/img/product/", [
                "esp32-s3-matrix.jpg",
                "esp32-s3-touch-amoled-1.8.jpg",
                "esp32-s3-geek.jpg",
            ]),
        ],
        "type": "static",
    },
    "m5stack": {
        "boards_manifest": [
            ("https://static-cdn.m5stack.com/resource/docs/products/core/", [
                "CoreS3.png",
                "AtomS3.png",
                "StampS3.png",
                "Cardputer.png",
            ]),
        ],
        "type": "static",
    },
    # More vendors as we discover structured image URLs
}


# ── Core Download Engine ──────────────────────────────────────────────────

def download_image(
    url: str,
    vendor: str,
    board_name: str,
    index: int = 0,
) -> Optional[Dict[str, Any]]:
    """Download a single board image with retry logic."""
    vendor_dir = OUTPUT_DIR / vendor
    vendor_dir.mkdir(parents=True, exist_ok=True)

    # Sanitize filename
    safe_name = board_name.replace("/", "_").replace(" ", "_").replace(":", "_")[:80]
    ext = url.rsplit(".", 1)[-1].split("?")[0][:4]
    if ext not in ("jpg", "jpeg", "png", "gif", "webp"):
        ext = "jpg"
    filename = f"{safe_name}_{index:02d}.{ext}"
    filepath = vendor_dir / filename

    if filepath.exists() and filepath.stat().st_size > 1000:
        return {"vendor": vendor, "board": board_name, "file": str(filepath), "size": filepath.stat().st_size, "cached": True}

    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                data = resp.read()
                if len(data) > 500:  # Must be >500 bytes to be a real image
                    filepath.write_bytes(data)
                    return {"vendor": vendor, "board": board_name, "file": str(filepath), "size": len(data), "cached": False}
        except Exception as e:
            if attempt == 2:
                return {"vendor": vendor, "board": board_name, "error": str(e)[:100]}
            time.sleep(1)
    return None


def scrape_adafruit() -> List[Dict]:
    """Pull Adafruit product images via their JSON API."""
    results = []
    source = BOARD_SOURCES["adafruit"]
    base = source["base_url"]

    try:
        req = urllib.request.Request(source["products_file"], headers=source["headers"])
        with urllib.request.urlopen(req, timeout=30) as resp:
            products = json.loads(resp.read())
    except Exception as e:
        print(f"Adafruit API failed: {e}")
        return results

    print(f"Adafruit: {len(products)} products found")

    # Filter for boards/microcontrollers — Adafruit has 5,000+ products,
    # most are accessories/sensors. We want actual boards.
    board_keywords = [
        "feather", "qt py", "metro", "itsybitsy", "trinket", "grand central",
        "circuit playground", "esp32", "nrf52", "rp2040", "samd", "matrix portal",
        "pyportal", "pybadge", "monster m4sk", "hallowing", "neotrellis",
        "arduino", "breakout", "board", "microcontroller", "dev board",
        "development", "maker", "adafruit", "featherwing", "wing", "bonnet",
        "piicodev", "stemma", "qt", "cplay", "express",
    ]

    urls_to_download = []
    for p in products[:300]:  # Sample first 300 for speed
        name = (p.get("name") or "").lower()
        pid = p.get("id")
        if not pid:
            continue

        # Check if this product is board-like
        is_board = any(kw in name for kw in board_keywords)
        if not is_board:
            continue

        # Try main product images (max 3 per product)
        for img_idx in range(3):
            url = f"{base}{pid}-0{img_idx}.jpg"
            urls_to_download.append((url, "adafruit", f"{pid}-{name[:60]}", img_idx))

    print(f"Adafruit: {len(urls_to_download)} board images to download")

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(download_image, url, vendor, name, idx)
                   for url, vendor, name, idx in urls_to_download]
        for f in concurrent.futures.as_completed(futures):
            r = f.result()
            if r:
                results.append(r)

    return results


def scrape_static_manifests() -> List[Dict]:
    """Pull images from vendors with static URL manifests."""
    results = []
    urls_to_download = []

    for vendor, source in BOARD_SOURCES.items():
        if source.get("type") != "static":
            continue

        for base_url, files in source.get("boards_manifest", []):
            for fname in files:
                url = base_url.rstrip("/") + "/" + fname.lstrip("/")
                board = fname.rsplit(".", 1)[0].replace("-", " ").replace("_", " ")
                urls_to_download.append((url, vendor, board, 0))

    print(f"Static manifests: {len(urls_to_download)} images")

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(download_image, url, vendor, name, idx)
                   for url, vendor, name, idx in urls_to_download]
        for f in concurrent.futures.as_completed(futures):
            r = f.result()
            if r:
                results.append(r)

    return results


def build_catalog_json() -> Dict[str, Any]:
    """Generate a training-ready catalog JSON from downloaded images."""
    catalog = {"vendors": {}, "total_images": 0}

    for vendor_dir in sorted(OUTPUT_DIR.iterdir()):
        if not vendor_dir.is_dir():
            continue
        vendor = vendor_dir.name
        images = []
        for img in sorted(vendor_dir.glob("*.jpg")) + sorted(vendor_dir.glob("*.png")):
            images.append({
                "file": img.name,
                "path": str(img),
                "size_kb": round(img.stat().st_size / 1024, 1),
            })
        if images:
            catalog["vendors"][vendor] = {
                "count": len(images),
                "images": images,
            }
            catalog["total_images"] += len(images)

    # Save catalog
    catalog_path = OUTPUT_DIR / "board_image_catalog.json"
    catalog_path.write_text(json.dumps(catalog, indent=2))
    print(f"Catalog saved: {catalog['total_images']} images from {len(catalog['vendors'])} vendors -> {catalog_path}")

    return catalog


def main():
    print("=" * 60)
    print("  NPU-STACK Board Image Scraper (Internal)")
    print(f"  Output: {OUTPUT_DIR}")
    print(f"  Workers: {MAX_WORKERS}")
    print("=" * 60)

    start = time.time()
    results = []

    # Phase 1: Adafruit API (bulk)
    print("\n[1/3] Adafruit API...")
    results.extend(scrape_adafruit())

    # Phase 2: Static manifests (parallel)
    print("\n[2/3] Static manifests (Seeed, Espressif, RPi, Orange Pi, Radxa, Waveshare, M5Stack)...")
    results.extend(scrape_static_manifests())

    # Phase 3: Build catalog
    print("\n[3/3] Building catalog...")
    catalog = build_catalog_json()

    elapsed = time.time() - start
    succeeded = [r for r in results if "error" not in r]
    failed = [r for r in results if "error" in r]
    cached = [r for r in succeeded if r.get("cached")]

    print(f"\nDone in {elapsed:.1f}s")
    print(f"  Downloaded: {len(succeeded) - len(cached)}")
    print(f"  Cached: {len(cached)}")
    print(f"  Failed: {len(failed)}")
    print(f"  Total in catalog: {catalog['total_images']}")


if __name__ == "__main__":
    main()
