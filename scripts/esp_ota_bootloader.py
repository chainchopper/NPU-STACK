"""Trigger machine.bootloader() over the REPL, then watch for the download port.

MicroPython's esp32 machine.bootloader() (RTC path, MICROPY_ESP32_USE_BOOTLOADER_RTC=1)
sets RTC_CNTL_FORCE_DOWNLOAD_BOOT and esp_restart()s, which should bring the chip
up in download mode without touching the BOOT button. We then look for the new
download COM port so esptool can flash.
"""
import subprocess
import time

import serial

REPL = "COM10"


def ports():
    out = subprocess.run(
        [r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
         "-NoProfile", "-Command",
         "Get-WmiObject Win32_SerialPort | Where-Object { $_.Name -match 'USB Serial' } | Select-Object -Expand DeviceID"],
        capture_output=True, text=True,
    )
    return set(p.strip() for p in out.stdout.splitlines() if p.strip().startswith("COM"))


before = ports()
print("ports before:", sorted(before))

s = serial.Serial(REPL, 115200, timeout=2)
time.sleep(0.3)
s.write(b"\x03")
time.sleep(0.4)
s.read(s.in_waiting or 1)
s.write(b"import machine; machine.bootloader()\r\n")
time.sleep(1.0)
try:
    s.close()
except Exception:
    pass

# Watch for a new/different download port for up to 15s
print("watching for download port...")
for _ in range(30):
    now = ports()
    new = now - before
    if new:
        print("download port appeared:", sorted(new))
        break
    if not (now & before):
        # original port dropped; the device is resetting
        pass
    time.sleep(0.5)
else:
    print("no new download port detected; ports now:", sorted(ports()))
