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


def _wait_for_repl(mp, tries=20):
    """Poll `mpremote ls` until the board's MicroPython REPL is reachable."""
    for i in range(tries):
        r = subprocess.run([str(a) for a in mp + ["ls"]],
                           capture_output=True, text=True)
        if r.returncode == 0:
            print("MicroPython REPL ready.")
            return True
        print("  waiting for REPL (%d/%d) ..." % (i + 1, tries))
        time.sleep(2)
    return False


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

    mp = [VENV_PY, "-m", "mpremote"]
    if args.port:
        mp += ["connect", args.port]

    # The XIAO's native USB ignores esptool's software reset, so after flashing
    # it needs a physical reset (RESET button or unplug/replug) to boot MicroPython.
    if not _wait_for_repl(mp):
        print("ERROR: could not reach the MicroPython REPL.")
        print("Press RESET on the XIAO (or unplug/replug USB), then re-run:")
        print("  python scripts/flash_nirvana_os.py --port " + (args.port or "COMx") + " --no-flash")
        sys.exit(1)

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
                      (FW_DIR / "uQR.py", "uQR.py"),
                      (FW_DIR / "wifi_provision.py", "wifi_provision.py"),
                      (cfg_src, "config.json")):
        run(mp + ["cp", str(src), ":" + dest])

    print("\nNIRVANA OS flashed. Open the serial REPL (115200) to see the boot banner.")


if __name__ == "__main__":
    main()
