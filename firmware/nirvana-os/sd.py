"""
NIRVANA OS — SD card storage (Seeed XIAO Round Display).

The Round Display SD slot rides the SAME SPI bus as the GC9A01 display,
with its own chip-select: CS = GPIO2 (D2). SCK/MOSI/MISO shared.
"""
import os

from machine import Pin

import sdcard

SD_CS = 2          # D2
MOUNT_POINT = "/sd"
APPS_DIR = "/sd/apps"

_mounted = False


def mount():
    """Mount the SD card at /sd. Returns True on success."""
    global _mounted
    if _mounted:
        return True
    import display
    try:
        sd = sdcard.SDCard(display.get_spi(), cs=Pin(SD_CS, Pin.OUT))
        os.mount(sd, MOUNT_POINT)
        _mounted = True
        print("[NIRVANA] SD mounted at", MOUNT_POINT)
        return True
    except Exception as e:
        print("[NIRVANA] SD mount failed:", e)
        return False


def is_mounted():
    return _mounted


def list_dir(path=MOUNT_POINT):
    try:
        return os.listdir(path)
    except Exception:
        return []


def read_text(path):
    try:
        with open(path, "r") as f:
            return f.read()
    except Exception:
        return None


def list_apps():
    """Discover Nirvana apps on the SD card.

    Convention: /sd/apps/<name>.py where each file defines
        NAME = "display name"
        def run(): ...
    Returns a list of (module_name, display_name).
    """
    apps = []
    if not _mounted:
        return apps
    for fname in list_dir(APPS_DIR):
        if not fname.endswith(".py"):
            continue
        mod = fname[:-3]  # strip .py
        # Read the NAME constant if present (optional; fall back to filename)
        name = mod
        txt = read_text(APPS_DIR + "/" + fname)
        if txt:
            for line in txt.splitlines():
                line = line.strip()
                if line.startswith("NAME") and "=" in line:
                    try:
                        name = line.split("=", 1)[1].strip().strip('"').strip("'")
                    except Exception:
                        pass
                    break
        apps.append((mod, name))
    return apps
