"""
Flash NIRVANA OS onto an ESP32-S3 (Seeed XIAO Sense / generic S3).

  1. erase flash + write MicroPython ESP32_GENERIC_S3 .bin (esptool)
  2. upload boot.py / main.py / config.json (mpremote)

The XIAO enters download mode by HOLDING the BOOT button while plugging in USB.

Usage:
  python scripts/flash_nirvana_os.py            # auto-detect port
  python scripts/flash_nirvana_os.py --port COM4
  python scripts/flash_nirvana_os.py --no-flash # only (re)upload app files
"""
import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
VENV_PY = REPO / ".venv" / "Scripts" / "python.exe"
FW_DIR = REPO / "firmware" / "nirvana-os"
BIN = REPO / "firmware" / "micropython-esp32" / "ESP32_GENERIC_S3-20260406-v1.28.0.bin"


def run(args):
    print("> " + " ".join(str(a) for a in args))
    return subprocess.run([str(a) for a in args])


def main():
    ap = argparse.ArgumentParser(description="Flash NIRVANA OS to an ESP32-S3")
    ap.add_argument("--port", default=None, help="serial port (COM4) — auto-detect if omitted")
    ap.add_argument("--baud", default="460800")
    ap.add_argument("--no-flash", action="store_true", help="skip firmware, only upload app files")
    ap.add_argument("--no-erase", action="store_true", help="skip erase_flash")
    args = ap.parse_args()

    if not BIN.exists():
        sys.exit("firmware not found: " + str(BIN))

    port = ["--port", args.port] if args.port else []

    if not args.no_flash:
        if not args.no_erase:
            run([VENV_PY, "-m", "esptool"] + port + ["erase_flash"])
        run([VENV_PY, "-m", "esptool"] + port +
            ["--baud", args.baud, "write_flash", "0", str(BIN)])
        print("waiting for the board to reboot into MicroPython ...")
        time.sleep(6)

    mp = [VENV_PY, "-m", "mpremote"]
    if args.port:
        mp += ["connect", args.port]

    # config: use the user's real config.json if present, else the example template
    cfg_src = FW_DIR / "config.json"
    if not cfg_src.exists():
        cfg_src = FW_DIR / "config.example.json"

    for src, dest in ((FW_DIR / "boot.py", "boot.py"),
                      (FW_DIR / "main.py", "main.py"),
                      (FW_DIR / "gc9a01.py", "gc9a01.py"),
                      (FW_DIR / "display.py", "display.py"),
                      (FW_DIR / "touch.py", "touch.py"),
                      (FW_DIR / "sdcard.py", "sdcard.py"),
                      (FW_DIR / "sd.py", "sd.py"),
                      (FW_DIR / "menu.py", "menu.py"),
                      (cfg_src, "config.json")):
        run(mp + ["cp", str(src), ":" + dest])

    print("\nNIRVANA OS flashed. Open the serial REPL (115200) to see the boot banner.")


if __name__ == "__main__":
    main()
