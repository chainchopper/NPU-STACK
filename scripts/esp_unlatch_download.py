"""Try to break an ESP32-S3 out of a latched download mode over USB-CDC.

The chip reports boot:0x22 (DOWNLOAD) and "waiting for download" even though
BOOT is not held. Try several DTR/RTS reset sequences to force a normal boot
(GPIO0 sampled high at reset release).
"""
import serial
import time
import sys

PORT = sys.argv[1] if len(sys.argv) > 1 else "COM9"


def read_boot(s, wait=1.2):
    time.sleep(wait)
    data = s.read(s.in_waiting or 1)
    return data.decode(errors="replace")


def attempt(name, seq):
    print("=== %s ===" % name)
    try:
        s = serial.Serial(PORT, 115200, timeout=2)
    except Exception as e:
        print("open failed:", e)
        return None
    try:
        for action, state, delay in seq:
            if action == "dtr":
                s.setDTR(state)
            elif action == "rts":
                s.setRTS(state)
            time.sleep(delay)
        out = read_boot(s)
        print(repr(out[:300]))
        return out
    finally:
        s.close()


# Classic esptool reset-into-app: DTR=False (GPIO0 high), pulse RTS (EN).
attempt("rts pulse, dtr low", [
    ("dtr", False, 0.05),   # GPIO0 = high (don't hold boot)
    ("rts", True, 0.10),    # EN low = reset
    ("rts", False, 0.05),   # EN high = release
    ("dtr", False, 0.05),
])

# Full cycle: both low then release EN first, then GPIO0.
attempt("both low, release EN then GPIO0", [
    ("dtr", True, 0.05),
    ("rts", True, 0.05),
    ("rts", False, 0.05),   # release reset while GPIO0 high
    ("dtr", False, 0.05),
])

# 1200-baud touch is for USB-CDC ACM bootloader entry on some boards; not here,
# but try a plain toggle with a longer settle.
attempt("long settle reset", [
    ("rts", True, 0.30),
    ("dtr", False, 0.10),
    ("rts", False, 0.30),
])

print("done")
