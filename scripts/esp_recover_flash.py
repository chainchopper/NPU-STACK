"""Single-session ESP32-S3 download-stub recovery + flash.

Holds COM9 open the whole time (no open/close churn), forces a clean reset
into download mode with the DTR/RTS auto-reset pattern, then hands the still-
open port state to esptool via a subprocess that re-opens it immediately.

If esptool still can't sync, this at least tells us whether the chip emits its
ROM banner on reset (proving the UART path is alive).
"""
import subprocess
import sys
import time

import serial

PORT = "COM9"
ESPTOOL = r"C:\Users\iAMBLACK\.espressif\python_env\idf5.5_py3.14_env\Scripts\esptool.exe"
BUILD = r"j:\NPU-STACK\tools\micropython-xiao-s3\micropython\ports\esp32\build"


def reset_and_read(port):
    s = serial.Serial(port, 115200, timeout=2)
    # esptool's classic reset-to-download: DTR controls GPIO0 (active-low
    # through the transistor = hold BOOT), RTS controls EN (reset).
    # Sequence: GPIO0 low, pulse EN, release EN while GPIO0 low, then GPIO0 high.
    s.setDTR(True)   # GPIO0 low  -> bootloader will see download strap
    s.setRTS(True)   # EN low     -> in reset
    time.sleep(0.1)
    s.setRTS(False)  # EN high    -> boot, samples GPIO0 low -> download mode
    time.sleep(0.05)
    s.setDTR(False)  # GPIO0 released
    time.sleep(0.4)
    banner = s.read(s.in_waiting or 1)
    s.close()
    return banner


print("--- reset into download, read banner ---")
banner = reset_and_read(PORT)
print(banner.decode(errors="replace")[:400] or "(no banner)")

print("--- immediately flash via esptool ---")
cmd = [
    ESPTOOL, "--chip", "esp32s3", "-p", PORT, "-b", "460800",
    "--before", "default_reset", "--after", "hard_reset",
    "write_flash", "--flash_mode", "keep", "--flash_size", "4MB",
    "--flash_freq", "80m",
    "0x0", BUILD + r"\bootloader\bootloader.bin",
    "0x8000", BUILD + r"\partition_table\partition-table.bin",
    "0x10000", BUILD + r"\micropython.bin",
]
proc = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
tail = (proc.stdout + proc.stderr).splitlines()[-12:]
print("\n".join(tail))
print("exit:", proc.returncode)
