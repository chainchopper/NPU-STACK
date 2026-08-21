"""Glean board names + slugs from pinout.xyz for NPU-STACK board profile cards.

pinout.xyz is a curated Raspberry Pi HAT/pHAT/add-on pinout database. This
script pulls the board list (name + slug + url) into a JSON the Board Explorer
can use to enrich board profile cards. Per-board pin usage can be gleaned in a
second pass by fetching each ``/pinout/<slug>`` page.

NOTE: pinout.xyz sits behind Cloudflare and blocks plain urllib (403). Either
pass a previously-saved HTML file (``--file boards.html``) or use the
Playwright-based scraper (``scripts/scrape_boards.py``) to save the page first.

Usage:
    python scripts/glean_pinout_xyz.py                # live fetch (may 403)
    python scripts/glean_pinout_xyz.py --file boards.html
"""
import argparse
import json
import re
import sys
import urllib.request

SOURCE = "https://pinout.xyz/boards"
OUT = "backend/data/pinout_xyz_boards.json"


def _extract(html: str) -> list:
    boards = []
    seen = set()
    # Skip pin-function nav links — they aren't boards.
    NAV = {"gpio", "3v3_power", "5v_power", "ground", "1_wire", "dpi", "gpclk",
           "pwm", "i2c", "spi", "uart", "jtag", "pcm", "sdio", "wiringpi"}
    for m in re.finditer(r'href="(?:https?://pinout\.xyz)?(/pinout/([a-z0-9_]+)/?)"[^>]*>([^<]+)<', html):
        path, slug, name = m.group(1), m.group(2), m.group(3).strip()
        if slug in seen or not name or slug in NAV:
            continue
        seen.add(slug)
        boards.append({
            "slug": slug,
            "name": name,
            "url": "https://pinout.xyz" + path,
        })
    return boards


def glean(html: str = "") -> list:
    if not html:
        req = urllib.request.Request(SOURCE, headers={"User-Agent": "Mozilla/5.0 (NPU-STACK board gleaner)"})
        try:
            html = urllib.request.urlopen(req, timeout=25).read().decode("utf-8", "replace")
        except Exception as exc:  # noqa: BLE001
            print("fetch failed:", exc)
            return []
    return _extract(html)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", help="path to a saved pinout.xyz/boards HTML file")
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()

    html = ""
    if args.file:
        with open(args.file, encoding="utf-8") as f:
            html = f.read()

    boards = glean(html)
    if not boards:
        print("no boards gleaned (Cloudflare may be blocking — save the page and use --file)")
        return 1
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"source": SOURCE, "count": len(boards), "boards": boards}, f, indent=2)
    print(f"gleaned {len(boards)} boards -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
