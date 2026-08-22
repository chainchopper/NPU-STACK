#!/usr/bin/env python3
"""
Generate marketplace app thumbnails.

Runs each marketplace app's main.py through the emulator runner, captures the
first rendered frame (240x240 RGB565), and writes backend/marketplace/apps/<id>/
thumb.png. Idempotent — re-run after app changes.

Usage:
    python scripts/gen_app_thumbs.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MARKET = REPO / "backend" / "marketplace"
CATALOG = MARKET / "catalog.json"
PY = REPO / ".venv" / "Scripts" / "python.exe"
if not PY.exists():
    PY = Path(sys.executable)

W, H = 240, 240


def rgb565_to_png(raw: bytes, path: Path) -> None:
    from PIL import Image
    img = Image.new("RGB", (W, H))
    px = img.load()
    i = 0
    for y in range(H):
        for x in range(W):
            c = (raw[i] << 8) | raw[i + 1]
            i += 2
            px[x, y] = (((c >> 11) & 0x1F) << 3, ((c >> 5) & 0x3F) << 2, (c & 0x1F) << 3)
    img.save(path)


def main() -> int:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    for app in catalog.get("apps", []):
        main_py = MARKET / "apps" / app["id"] / "main.py"
        if not main_py.exists():
            print(f"[skip] {app['id']} (no main.py)")
            continue
        proc = subprocess.Popen(
            [str(PY), "-m", "backend.emulator.runner", str(main_py)],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, cwd=str(REPO),
        )
        try:
            line = proc.stdout.readline()
            if line.startswith(b"FRAME:"):
                n = int(line[6:].strip())
                raw = proc.stdout.read(n)
                thumb = MARKET / "apps" / app["id"] / "thumb.png"
                rgb565_to_png(raw, thumb)
                print(f"[ok] {app['id']} -> {thumb.name} ({thumb.stat().st_size}b)")
            else:
                print(f"[fail] {app['id']}: no frame (got {line[:40]!r})")
        finally:
            proc.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
