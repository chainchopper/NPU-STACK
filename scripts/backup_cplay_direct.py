"""Backup Adafruit CPlay Express CIRCUITPY at D: — read individual files only."""
import shutil, time
from pathlib import Path

SRC = Path("D:/")
DST = Path("J:/NPU-STACK/backend/data/firmware_backups/adafruit-playground-" + time.strftime("%Y%m%d-%H%M%S"))
DST.mkdir(parents=True, exist_ok=True)

KNOWNFILES = [
    "boot_out.txt", "code.py", "main.py", "secrets.py",
    "settings.toml", "npu_config.json",
]

# Also try common lib files
TRYFILES = ["boot_out.txt", "code.py", "main.py", "secrets.py",
            "settings.toml", "lib/adafruit_imageload", "lib/adafruit_st7789",
            "lib/adafruit_display_text", "lib/adafruit_led_animation"]

count = 0
total = 0

for fname in KNOWNFILES:
    src = SRC / fname
    try:
        if src.exists() and src.is_file():
            dst = DST / fname
            shutil.copy2(str(src), str(dst))
            sz = dst.stat().st_size
            count += 1
            total += sz
            print(f"  OK {fname} ({sz} bytes)")
    except Exception as e:
        print(f"  SKIP {fname}: {e}")

# Try to read boot_out.txt for board info
boot = SRC / "boot_out.txt"
try:
    info = boot.read_text(encoding="utf-8", errors="replace")
    print(f"\nBoard: {info[:200]}")
except Exception as e:
    print(f"\nNo boot_out.txt: {e}")

print(f"\nBACKUP: {count} files, {total} bytes -> {DST}")
