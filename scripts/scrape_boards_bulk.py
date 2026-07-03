#!/usr/bin/env python3
"""
BULK Board Scraper — Multi-manufacturer, high-throughput board ingestion.

Uses Playwright headless + manufacturer-specific patterns:
  Adafruit:    /product/{PID} + learn.adafruit.com/{slug}.md?view=all
  SparkFun:    /products/{PID}
  Seeed:       wiki.seeedstudio.com/{slug}
  Waveshare:   waveshare.com/wiki/{slug}
  Coral:       coral.ai/products/{slug}
  Hailo:       hailo.ai/products
  AMD/Kria:    amd.com/en/products/system-on-modules

Outputs: backend/data/boards/{board_id}/ (screenshot, images, diagrams)
         datasets/boards_multimodal_all.jsonl (training entries)
"""
import json, os, re, sys, time, hashlib
from pathlib import Path
from urllib.parse import urljoin, urlparse
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

REPO = Path(__file__).resolve().parents[1]
BOARDS_DIR = REPO / "backend" / "data" / "boards"
DATASET_OUT = REPO / "datasets" / "boards_multimodal_all.jsonl"

os.makedirs(BOARDS_DIR, exist_ok=True)

# ── Bulk product discovery patterns ──
MANUFACTURER_SOURCES = {
    "adafruit": {
        "name": "Adafruit",
        "shop_urls": [
            "https://www.adafruit.com/category/946",   # Boards (83 listed)
            "https://www.adafruit.com/category/943",   # Feather
        ],
        "learn_base": "https://learn.adafruit.com",
        "product_regex": r'/product/(\d+)',
        "learn_slug_regex": r'learn\.adafruit\.com/([^/\s"]+)',
    },
    "sparkfun": {
        "name": "SparkFun",
        "shop_urls": ["https://www.sparkfun.com/categories/302"],  # Dev Boards
        "learn_base": "https://learn.sparkfun.com",
        "product_regex": r'/products/(\d+)',
    },
    "seeed": {
        "name": "Seeed Studio",
        "shop_urls": ["https://wiki.seeedstudio.com/"],
        "learn_base": "https://wiki.seeedstudio.com",
    },
    "waveshare": {
        "name": "Waveshare",
        "shop_urls": ["https://www.waveshare.com/product/development-boards.htm"],
        "learn_base": "https://www.waveshare.com/wiki",
    },
}

# ── Accelerator / NPU boards (manually curated) ──
ACCELERATOR_BOARDS = [
    {
        "id": "coral-dev-board-mini",
        "name": "Google Coral Dev Board Mini",
        "manufacturer": "google",
        "chip": "MediaTek 8167s + Edge TPU",
        "architecture": "aarch64",
        "product_url": "https://coral.ai/products/dev-board-mini/",
        "docs_url": "https://coral.ai/docs/dev-board-mini",
        "specs": {"cpu": "Quad Cortex-A35", "tpu": "Edge TPU (4 TOPS)", "ram": "2 GB LPDDR3", "wifi": "802.11ac", "bt": "5.0"},
        "features": ["Edge TPU", "GPIO 40-pin", "MIPI CSI/DSI", "USB 2.0", "HDMI 2.0a", "Gigabit Ethernet"],
        "tags": ["tpu", "edge-ai", "ml-accelerator", "google"],
    },
    {
        "id": "hailo-8l",
        "name": "Hailo-8L Entry-Level AI Accelerator",
        "manufacturer": "hailo",
        "chip": "Hailo-8L",
        "architecture": "npv",
        "product_url": "https://hailo.ai/products/hailo-8l-ai-accelerator/",
        "docs_url": "https://hailo.ai/developer-zone/documentation/",
        "specs": {"tpu": "Hailo-8L (13 TOPS)", "power": "1.5-3.5W", "interface": "M.2 / PCIe"},
        "features": ["13 TOPS INT8", "Sub-3.5W power", "M.2 form factor", "PCIe Gen3", "Raspberry Pi HAT compatible"],
        "tags": ["npu", "ai-accelerator", "edge-ai", "hailo"],
    },
    {
        "id": "hailo-8",
        "name": "Hailo-8 AI Accelerator",
        "manufacturer": "hailo",
        "chip": "Hailo-8",
        "architecture": "npv",
        "product_url": "https://hailo.ai/products/ai-accelerators/hailo-8-ai-accelerator/",
        "docs_url": "https://hailo.ai/developer-zone/documentation/",
        "specs": {"tpu": "Hailo-8 (26 TOPS)", "power": "2.5-6.5W", "interface": "M.2 / PCIe / Mini PCIe"},
        "features": ["26 TOPS INT8", "Real-time processing", "M.2 2230/2280", "PCIe Gen3", "Mini PCIe"],
        "tags": ["npu", "ai-accelerator", "edge-ai", "hailo"],
    },
    {
        "id": "amd-kria-kv260",
        "name": "AMD Kria KV260 Vision AI Starter Kit",
        "manufacturer": "amd",
        "chip": "Zynq UltraScale+ MPSoC",
        "architecture": "aarch64+fpga",
        "product_url": "https://www.amd.com/en/products/system-on-modules/kria/kv260-vision-ai-starter-kit.html",
        "docs_url": "https://www.amd.com/en/products/system-on-modules/kria/kv260-vision-ai-starter-kit.html#documentation",
        "specs": {"cpu": "Quad Cortex-A53 + Cortex-R5F", "fabric": "FPGA (256K logic cells)", "ram": "4 GB DDR4", "ai": "DPU (Deep Learning Processing Unit)"},
        "features": ["FPGA fabric", "DPU accelerator", "MIPI CSI/DSI", "USB 3.0", "Gigabit Ethernet", "HDMI", "Pmod", "RPi camera connector"],
        "tags": ["fpga", "vision-ai", "dpu", "kria", "amd-xilinx"],
    },
    {
        "id": "amd-ryzen-ai-hawkpoint",
        "name": "AMD Ryzen AI (Hawk Point) NPU",
        "manufacturer": "amd",
        "chip": "Ryzen AI XDNA NPU",
        "architecture": "x86_64",
        "product_url": "https://www.amd.com/en/products/processors/consumer/ryzen-ai.html",
        "docs_url": "https://ryzenai.docs.amd.com/",
        "specs": {"npu": "XDNA NPU (16 TOPS)", "cpu": "Zen 4", "gpu": "RDNA 3", "process": "4nm"},
        "features": ["16 TOPS NPU", "Integrated GPU", "x86 CPU", "ONNX Runtime", "DirectML", "OpenVINO", "Windows Copilot+"],
        "tags": ["npu", "x86", "laptop", "amd", "ryzen-ai", "copilot"],
    },
]

# ── Image download helpers ──
def download_image(page, url, board_dir, prefix, min_size=5000):
    """Download image from URL, save to board_dir."""
    try:
        if url.startswith("//"): url = "https:" + url
        elif url.startswith("/"):
            parsed = urlparse(page.url)
            url = f"{parsed.scheme}://{parsed.netloc}{url}"

        resp = page.request.get(url, timeout=15000)
        if resp.status != 200 or not resp.body():
            return None
        body = resp.body()
        if len(body) < min_size:
            return None

        ct = resp.headers.get("content-type", "")
        ext_map = {"jpeg": ".jpg", "jpg": ".jpg", "png": ".png", "svg": ".svg", "webp": ".webp", "gif": ".gif"}
        ext = ".png"
        for k, v in ext_map.items():
            if k in ct:
                ext = v; break

        fname = f"{prefix}_{hashlib.md5(url.encode()).hexdigest()[:8]}{ext}"
        fpath = board_dir / fname
        fpath.write_bytes(body)
        return str(fpath.relative_to(REPO)).replace("\\", "/")
    except Exception:
        return None


def scrape_product_page(page, url, board_dir, board_data):
    """Scrape a single product page and download assets."""
    print(f"    Navigating: {url[:100]}")
    try:
        page.goto(url, timeout=25000, wait_until="domcontentloaded")
        time.sleep(2)
    except PWTimeout:
        print(f"    Timeout: {url[:80]}")
        return board_data

    # Full page screenshot
    try:
        ss_path = board_dir / "screenshot.png"
        page.screenshot(path=str(ss_path), full_page=True)
        board_data["screenshot"] = str(ss_path.relative_to(REPO)).replace("\\", "/")
    except Exception:
        pass

    # Download product images (not icons, not spacers)
    saved = []
    for img in page.query_selector_all("img"):
        src = (img.get_attribute("src") or "").strip()
        alt = (img.get_attribute("alt") or "").lower()
        if not src or any(s in src.lower() for s in ["icon", "logo", "spacer", "pixel", "badge", "avatar"]):
            continue
        if any(s in alt.lower() for s in ["icon", "logo"]):
            continue
        f = download_image(page, src, board_dir, "img", min_size=5000)
        if f:
            saved.append(f)

    # Download pinout/diagram images specifically
    diagram_selectors = "img[src*='pinout'], img[src*='diagram'], img[src*='mechanical'], img[src*='schematic'], img[src*='dimension'], img[src*='block']"
    diagrams = []
    for img in page.query_selector_all(diagram_selectors):
        src = img.get_attribute("src") or img.get_attribute("data-src")
        if src:
            f = download_image(page, src, board_dir, "diagram", min_size=3000)
            if f:
                diagrams.append(f)

    board_data["image_urls"] = saved
    board_data["diagram_urls"] = diagrams
    board_data["scraped_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")

    # Extract text content
    try:
        text = page.inner_text("body")
        lines = [l.strip() for l in text.split("\n") if l.strip() and len(l.strip()) > 3][:300]
        board_data["scraped_text"] = lines
    except Exception:
        pass

    return board_data


def slug_to_id(name):
    """Convert product name to board ID."""
    slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')[:40]
    return slug


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Bulk board scraper")
    parser.add_argument("--adafruit", action="store_true", help="Scrape Adafruit boards")
    parser.add_argument("--accelerators", action="store_true", help="Add accelerator/NPU boards")
    parser.add_argument("--all", action="store_true", help="Scrape everything")
    parser.add_argument("--limit", type=int, default=0, help="Limit per manufacturer")
    parser.add_argument("--dataset", action="store_true", help="Generate training dataset")
    args = parser.parse_args()

    all_scraped = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1400, "height": 900},
            user_agent="NPU-STACK/1.0 BoardScraper (research/archival)")
        page = context.new_page()

        do_adafruit = args.adafruit or args.all
        do_accel = args.accelerators or args.all

        # ── Adafruit bulk scrape ──
        if do_adafruit:
            print("\n=== ADAFRUIT BULK SCRAPE ===")
            product_ids = set()

            # Step 1: Discover product IDs from category pages
            for cat_url in MANUFACTURER_SOURCES["adafruit"]["shop_urls"]:
                print(f"\n  Scanning category: {cat_url}")
                try:
                    page.goto(cat_url, timeout=30000, wait_until="domcontentloaded")
                    time.sleep(3)
                    links = page.query_selector_all("a[href*='/product/']")
                    for l in links:
                        href = l.get_attribute("href") or ""
                        m = re.search(r'/product/(\d+)', href)
                        if m:
                            product_ids.add(m.group(1))
                except Exception as e:
                    print(f"    Error: {e}")

            print(f"\n  Found {len(product_ids)} product IDs")

            # Step 2: For each product, try to find Learn guide and scrape
            count = 0
            for pid in sorted(product_ids, key=lambda x: int(x)):
                if args.limit and count >= args.limit:
                    break
                prod_url = f"https://www.adafruit.com/product/{pid}"
                try:
                    page.goto(prod_url, timeout=20000, wait_until="domcontentloaded")
                    time.sleep(1.5)

                    # Get product name
                    title_el = page.query_selector("h1, .product-title, .product_name")
                    prod_name = (title_el.inner_text() if title_el else f"Adafruit Product {pid}").strip()[:80]

                    # Skip accessories only if the name is clearly NOT a dev board
                    skip_words = ["header", "cable", "antenna", "proto wing", "charger",
                                  "terminal", "doubler", "tripler", "quad", "kit", "pack",
                                  "bundle", "accessory", "short", "battery", "jst", "paper",
                                  "gift", "freebie", "notify", "sensor wing", "relay wing",
                                  "motor wing", "stepper wing", "oled add", "gps wing"]
                    name_lower = prod_name.lower()
                    is_board = any(w in name_lower for w in ["feather", "board", "dev", "metro", "qt py",
                                                            "express", "xiao", "itsy", "huzzah", "hallowing",
                                                            "pybadge", "pygamer", "clue", "cpx", "grand central",
                                                            "trinket", "gemma", "flora", "playground", "ruler",
                                                            "neotrellis", "memento", "fruit jam", "pico"])
                    if not is_board and any(w in name_lower for w in skip_words):
                        continue
                    if not is_board and not any(w in name_lower for w in ["micro", "controller", "chip", "rp2040", "rp2350", "esp32", "nrf52", "nrf52840", "atsamd", "samd", "atmega", "stm32", "cortex", "s3", "s2", "c6"]):
                        continue

                    board_id = slug_to_id(prod_name)
                    if not board_id:
                        continue

                    board_dir = BOARDS_DIR / board_id
                    board_dir.mkdir(parents=True, exist_ok=True)

                    # Find Learn guide link
                    learn_link = None
                    for a in page.query_selector_all("a[href*='learn.adafruit.com']"):
                        href = a.get_attribute("href") or ""
                        if "/product/" not in href and "/categories/" not in href:
                            learn_link = href
                            break

                    board = {
                        "id": board_id,
                        "name": prod_name,
                        "manufacturer": "adafruit",
                        "product_url": prod_url,
                        "docs_url": learn_link or prod_url,
                        "features": [],
                        "tags": ["adafruit"],
                        "npu_stack_ops": ["pair", "terminal", "fleet-enroll", "blink", "nirvana-chat"],
                    }

                    # Scrape product page
                    board = scrape_product_page(page, prod_url, board_dir, board)

                    # If Learn guide found, scrape that too
                    if learn_link and "learn.adafruit.com" in learn_link:
                        guide_dir = board_dir / "learn"
                        guide_dir.mkdir(parents=True, exist_ok=True)
                        # Try markdown version
                        md_url = learn_link.rstrip("/") + ".md?view=all"
                        try:
                            page.goto(md_url, timeout=20000, wait_until="domcontentloaded")
                            time.sleep(1)
                            guide_text = page.inner_text("body")
                            board["learn_guide"] = guide_text[:5000]  # first 5K chars

                            # Screenshot the guide
                            page.screenshot(path=str(guide_dir / "guide.png"), full_page=True)

                            # Download guide images
                            for img in page.query_selector_all("img[src*='learn']"):
                                src = img.get_attribute("src") or ""
                                f = download_image(page, src, guide_dir, "learn", min_size=5000)
                                if f and "image_urls" in board:
                                    board["image_urls"].append(f)
                        except Exception:
                            pass

                    # Save board JSON
                    fpath = BOARDS_DIR / f"{board_id}.json"
                    fpath.write_text(json.dumps(board, indent=2, ensure_ascii=False), encoding="utf-8")
                    all_scraped.append(board)
                    count += 1
                    if count % 10 == 0:
                        print(f"    Progress: {count} boards scraped")

                except Exception as e:
                    pass

            print(f"  Adafruit: {count} boards scraped")

        # ── Accelerator/NPU boards ──
        if do_accel:
            print("\n=== ACCELERATOR / NPU BOARDS ===")
            for ac in ACCELERATOR_BOARDS:
                board_dir = BOARDS_DIR / ac["id"]
                board_dir.mkdir(parents=True, exist_ok=True)

                ac.setdefault("npu_stack_ops", ["pair", "terminal", "benchmark", "nirvana-chat"])
                ac.setdefault("features", [])
                ac.setdefault("tags", [])

                # Scrape product page if URL exists
                if ac.get("product_url"):
                    try:
                        ac = scrape_product_page(page, ac["product_url"], board_dir, ac)
                    except Exception:
                        pass

                fpath = BOARDS_DIR / f"{ac['id']}.json"
                fpath.write_text(json.dumps(ac, indent=2, ensure_ascii=False), encoding="utf-8")
                all_scraped.append(ac)
                print(f"    {ac['name']}: added")

        browser.close()

    # ── Generate multimodal dataset ──
    if args.dataset:
        system = "You are Nirvana, the AI core of NPU-STACK. You analyze images of microcontroller boards, NPU accelerators, embedded AI hardware, and development kits. You identify chips, interfaces, GPIO pinouts, and key features from visual inspection."

        dataset_entries = []
        for board in all_scraped:
            sid = board.get("id", "")
            name = board.get("name", "")
            specs_str = ", ".join(f"{k}: {v}" for k, v in board.get("specs", {}).items())
            features_str = ", ".join(board.get("features", []))
            chip = board.get("chip", "unknown")

            # Screenshot entry
            if board.get("screenshot"):
                dataset_entries.append({
                    "messages": [
                        {"role": "system", "content": [{"type": "text", "text": system}]},
                        {"role": "user", "content": [
                            {"type": "image", "image": str(REPO / board["screenshot"])},
                            {"type": "text", "text": f"Identify this hardware. What chip does it use? What are its key features? What manufacturer produces this?"}
                        ]},
                        {"role": "assistant", "content": [{"type": "text", "text": f"This is the {name} by {board.get('manufacturer', 'unknown')}. It uses a {chip} processor. Specifications: {specs_str}. Key features: {features_str}. Tags: {', '.join(board.get('tags', []))}."}]},
                    ]
                })

            # Diagram entries
            for diag in board.get("diagram_urls", [])[:2]:
                dataset_entries.append({
                    "messages": [
                        {"role": "system", "content": [{"type": "text", "text": system}]},
                        {"role": "user", "content": [
                            {"type": "image", "image": str(REPO / diag)},
                            {"type": "text", "text": f"This is a technical diagram for the {name}. What does this diagram show?"}
                        ]},
                        {"role": "assistant", "content": [{"type": "text", "text": f"This diagram shows the layout/specification for the {name} ({chip}). It illustrates key interfaces: {features_str}."}]},
                    ]
                })

        if dataset_entries:
            with open(DATASET_OUT, "w", encoding="utf-8") as f:
                for e in dataset_entries:
                    f.write(json.dumps(e, ensure_ascii=False) + "\n")
            print(f"\nDataset: {DATASET_OUT} ({len(dataset_entries)} entries)")

    print(f"\nDone — {len(all_scraped)} total boards")


if __name__ == "__main__":
    main()
