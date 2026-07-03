#!/usr/bin/env python3
"""
Board Scraper — Playwright-based scraper for manufacturer product pages.

Pulls: page screenshots, spec tables, pinout diagrams, datasheet links, product images.
Stores: backend/data/boards/{board_id}/
Generates: updated board JSON + multimodal training dataset entries.

Usage: python scripts/scrape_boards.py [board_id] [--all] [--dataset]
"""
import json, os, sys, re, time, hashlib
from pathlib import Path
from urllib.parse import urljoin, urlparse
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

REPO = Path(__file__).resolve().parents[1]
BOARDS_DIR = REPO / "backend" / "data" / "boards"
DATASET_DIR = REPO / "datasets"
IMAGES_DIR = DATASET_DIR / "images" / "boards"
DATASET_OUT = DATASET_DIR / "boards_multimodal.jsonl"

os.makedirs(IMAGES_DIR, exist_ok=True)

# ── Per-manufacturer scraping strategies ──
MANUFACTURER_STRATEGIES = {
    "raspberrypi": {
        "product_selectors": ["#main-content", ".product-detail", ".entry-content"],
        "spec_selectors": ["table.specs tr", ".specifications li", ".product-specs li", ".product-details dd"],
        "image_selectors": ["img.product-image", ".product-gallery img", ".entry-content img:not(.icon)"],
        "diagram_selectors": ["img[src*='pinout']", "img[src*='diagram']", "img[src*='mechanical']", "img[src*='schematic']"],
    },
    "espressif": {
        "product_selectors": [".document", ".section", ".rst-content", "article"],
        "spec_selectors": ["table.docutils tr", "table.colwidths-auto tr", ".wy-table-bordered tr"],
        "image_selectors": [".document img", ".figure img", ".rst-content img"],
        "diagram_selectors": ["img[src*='pinout']", "img[src*='block']", "img[src*='schematic']", "img[src*='devkit']"],
    },
    "adafruit": {
        "product_selectors": [".learn-guide-content", ".product-page", ".main-content"],
        "spec_selectors": [".specs-table tr", "table.product-specs tr", ".technical-details li", "dl dt"],
        "image_selectors": [".product-image img", ".guide-content img", ".learn-guide-content img:not(.icon)"],
        "diagram_selectors": ["img[src*='pinout']", "img[src*='diagram']", "img[src*='wiring']", "img[src*='mechanical']"],
    },
    "arduino": {
        "product_selectors": [".product-content", ".tech-specs", ".documentation-content"],
        "spec_selectors": ["table.tech-specs-table tr", ".product-tech-specs li", ".specifications tr"],
        "image_selectors": [".product-image img", ".product-gallery img", "img.pinout", ".product-content img"],
        "diagram_selectors": ["img[src*='pinout']", "img[src*='mechanical']", "img[src*='schematic']"],
    },
    "seedstudio": {
        "product_selectors": [".wiki-content", ".product-main", ".main-content", "article"],
        "spec_selectors": ["table.spec tr", ".spec-table tr", ".wiki-content table tr", ".features li"],
        "image_selectors": [".wiki-content img", ".product-image img", "article img"],
        "diagram_selectors": ["img[src*='pinout']", "img[src*='dimension']", "img[src*='mechanical']", "img[src*='schematic']"],
    },
    "waveshare": {
        "product_selectors": [".wiki-content", ".product-detail", ".main-content"],
        "spec_selectors": [".spec-table tr", "table.parameters tr", ".wiki-content table tr"],
        "image_selectors": [".wiki-content img", ".product-image img", ".gallery img"],
        "diagram_selectors": ["img[src*='pinout']", "img[src*='schematic']", "img[src*='interface']", "img[src*='dimension']"],
    },
    "sparkfun": {
        "product_selectors": [".tutorial-content", ".product-info", ".hookup-guide"],
        "spec_selectors": [".specs-table tr", ".features-list li", ".technical-info table tr"],
        "image_selectors": [".tutorial-content img", ".product-image img", ".hookup-guide img"],
        "diagram_selectors": ["img[src*='pinout']", "img[src*='diagram']", "img[src*='wiring']", "img[src*='schematic']"],
    },
    "google": {
        "product_selectors": [".main-content", ".documentation", "article"],
        "spec_selectors": ["table.specs tr", ".specifications li", ".datasheet tr"],
        "image_selectors": [".product-image img", "article img:not(.icon)"],
        "diagram_selectors": ["img[src*='pinout']", "img[src*='diagram']", "img[src*='mechanical']"],
    },
}

# ── Download helpers ──
def download_image(page, url, board_dir, prefix):
    """Download an image from a URL, save to board_dir with prefix."""
    try:
        # Handle relative URLs
        if url.startswith("//"):
            url = "https:" + url
        elif url.startswith("/"):
            base = page.url
            parsed = urlparse(base)
            url = f"{parsed.scheme}://{parsed.netloc}{url}"

        resp = page.request.get(url, timeout=15000)
        if resp.status != 200 or not resp.body():
            return None

        content_type = resp.headers.get("content-type", "")
        ext = ".png"
        if "jpeg" in content_type or "jpg" in content_type:
            ext = ".jpg"
        elif "svg" in content_type:
            ext = ".svg"
        elif "webp" in content_type:
            ext = ".webp"
        elif "gif" in content_type:
            ext = ".gif"

        # Skip tiny images (icons, spacers)
        body = resp.body()
        if len(body) < 5000:  # skip anything under 5KB
            return None

        fname = f"{prefix}_{hashlib.md5(url.encode()).hexdigest()[:8]}{ext}"
        fpath = board_dir / fname
        fpath.write_bytes(body)
        return str(fpath.relative_to(REPO)).replace("\\", "/")
    except Exception:
        return None


def scrape_board(board, pw):
    """Scrape a single board's manufacturer page using Playwright."""
    board_id = board["id"]
    docs_url = board.get("product_url") or board.get("docs_url", "")
    manufacturer = board.get("manufacturer", "")

    if not docs_url:
        print(f"  [{board_id}] No docs_url — skipping scrape")
        return board

    board_dir = BOARDS_DIR / board_id
    board_dir.mkdir(parents=True, exist_ok=True)

    strategy = MANUFACTURER_STRATEGIES.get(manufacturer, MANUFACTURER_STRATEGIES["espressif"])

    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(
        viewport={"width": 1400, "height": 900},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 NPU-STACK/1.0 BoardScraper"
    )
    page = context.new_page()

    try:
        print(f"  [{board_id}] Navigating to {docs_url[:80]}...")
        page.goto(docs_url, timeout=30000, wait_until="domcontentloaded")
        time.sleep(3)  # Let JS render

        # Take screenshot
        screenshot_path = board_dir / "screenshot.png"
        page.screenshot(path=str(screenshot_path), full_page=True)
        board["screenshot"] = str(screenshot_path.relative_to(REPO)).replace("\\", "/")
        print(f"    Screenshot: {board['screenshot']}")

        # Extract text content for specs
        body_text = page.inner_text("body")
        lines = [l.strip() for l in body_text.split("\n") if l.strip() and len(l.strip()) > 3]
        board["scraped_text"] = lines[:200]  # first 200 non-empty lines

        # Find and download product images
        image_urls = set()
        for sel in strategy["image_selectors"]:
            try:
                for img in page.query_selector_all(sel):
                    src = img.get_attribute("src") or img.get_attribute("data-src")
                    if src and ("icon" not in src.lower()) and ("logo" not in src.lower()):
                        image_urls.add(src)
            except Exception:
                pass

        # Find and download pinout/diagram images specifically
        diagram_urls = set()
        for sel in strategy["diagram_selectors"]:
            try:
                for img in page.query_selector_all(sel):
                    src = img.get_attribute("src") or img.get_attribute("data-src")
                    if src:
                        diagram_urls.add(src)
            except Exception:
                pass

        # Download images
        saved_images = []
        for i, url in enumerate(list(image_urls)[:10]):
            fname = download_image(page, url, board_dir, f"img_{i:02d}")
            if fname:
                saved_images.append(fname)

        saved_diagrams = []
        for i, url in enumerate(list(diagram_urls)[:5]):
            fname = download_image(page, url, board_dir, f"diagram_{i:02d}")
            if fname:
                saved_diagrams.append(fname)

        board["image_urls"] = saved_images
        board["diagram_urls"] = saved_diagrams
        print(f"    Downloaded: {len(saved_images)} images, {len(saved_diagrams)} diagrams")

    except PWTimeout:
        print(f"    Timeout loading {docs_url}")
    except Exception as e:
        print(f"    Error: {e}")
    finally:
        browser.close()

    board["scraped_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    return board


def generate_dataset_entries(board):
    """Generate multimodal training entries from a board."""
    entries = []
    board_id = board["id"]
    board_name = board["name"]

    system = "You are Nirvana, the AI core of NPU-STACK. You analyze images of microcontroller boards, development kits, and embedded hardware. You identify board models, chips, pinouts, and connectivity features from visual inspection."

    # Screenshot entry
    if board.get("screenshot"):
        entries.append({
            "messages": [
                {"role": "system", "content": [{"type": "text", "text": system}]},
                {"role": "user", "content": [
                    {"type": "image", "image": str(REPO / board["screenshot"])},
                    {"type": "text", "text": f"Identify this board. What chip does it use? What interfaces and GPIO headers are visible? What manufacturer produces this board?"}
                ]},
                {"role": "assistant", "content": [
                    {"type": "text", "text": f"This is the {board_name} by {board.get('manufacturer', 'unknown')}. It uses a {board.get('chip', '')} processor ({board.get('architecture', '')} architecture). Key features: {', '.join(board.get('features', []))}. Specifications: {', '.join(f'{k}: {v}' for k, v in board.get('specs', {}).items())}."}
                ]},
            ]
        })

    # Diagram entries
    for i, diag in enumerate(board.get("diagram_urls", [])[:2]):
        entries.append({
            "messages": [
                {"role": "system", "content": [{"type": "text", "text": system}]},
                {"role": "user", "content": [
                    {"type": "image", "image": str(REPO / diag)},
                    {"type": "text", "text": f"This is a technical diagram for the {board_name}. Describe what pins, connectors, and interfaces are labeled in this diagram."}
                ]},
                {"role": "assistant", "content": [
                    {"type": "text", "text": f"This appears to be a pinout or mechanical diagram for the {board_name} ({board.get('chip', '')}). It shows the GPIO pin layout and interface connectors for NPU-STACK operations. Key interfaces visible: {', '.join(board.get('features', [])[:6])}."}
                ]},
            ]
        })

    return entries


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Scrape board documentation pages")
    parser.add_argument("board_id", nargs="?", help="Scrape a specific board ID")
    parser.add_argument("--all", action="store_true", help="Scrape all boards")
    parser.add_argument("--dataset", action="store_true", help="Generate multimodal training dataset from scraped content")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of boards to scrape")
    args = parser.parse_args()

    # Load boards
    boards = []
    for f in sorted(BOARDS_DIR.glob("*.json")):
        boards.append(json.loads(f.read_text(encoding="utf-8")))

    target_ids = set()
    if args.board_id:
        target_ids.add(args.board_id)
    if args.all:
        target_ids = {b["id"] for b in boards}

    if not target_ids:
        print("Usage: python scripts/scrape_boards.py <board_id> [--all] [--dataset]")
        print(f"Available boards: {[b['id'] for b in boards]}")
        return

    scraped = []
    count = 0

    with sync_playwright() as pw:
        for board in boards:
            if board["id"] not in target_ids:
                continue
            if args.limit and count >= args.limit:
                break

            updated = scrape_board(board, pw)
            scraped.append(updated)

            # Save updated board JSON
            fpath = BOARDS_DIR / f"{board['id']}.json"
            fpath.write_text(json.dumps(updated, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"  Saved: {fpath}")
            count += 1

    # Generate dataset
    if args.dataset:
        all_entries = []
        for board in scraped:
            entries = generate_dataset_entries(board)
            all_entries.extend(entries)

        if all_entries:
            with open(DATASET_OUT, "w", encoding="utf-8") as f:
                for e in all_entries:
                    f.write(json.dumps(e, ensure_ascii=False) + "\n")
            print(f"\nDataset: {DATASET_OUT} ({len(all_entries)} entries)")

    print(f"\nDone — scraped {len(scraped)} boards")


if __name__ == "__main__":
    main()
