import serial
import time
import sys

port = sys.argv[1] if len(sys.argv) > 1 else "COM10"
s = serial.Serial(port, 115200, timeout=5)
time.sleep(0.3)
s.write(b"\x03")
time.sleep(0.5)
s.read(s.in_waiting or 1)
# Soft-reboot so the freshly copied camera_capture.py is the one imported
s.write(b"\x04")
time.sleep(3.0)
s.write(b"\x03")
time.sleep(0.5)
s.read(s.in_waiting or 1)


def drain(wait):
    end = time.time() + wait
    buf = b""
    while time.time() < end:
        try:
            n = s.in_waiting
        except Exception:
            break
        if n:
            buf += s.read(n)
        else:
            time.sleep(0.05)
    return buf.decode(errors="replace")


def run(c, wait=3.0):
    s.write(c.encode() + b"\r\n")
    out = drain(wait)
    print(">>>", c)
    print(out)
    return out


run("import camera_capture, sd, gc; gc.collect()", 2.0)
run("camera_capture.init(); print('init ok')", 6.0)
run("f=camera_capture.capture(); print('captured', len(f) if f else 0)", 8.0)
run("r=sd.save_photo(f); print('saved:', r)", 6.0)
run("import os; print('photos:', os.listdir('/sd/photos') if 'photos' in os.listdir('/sd') else 'none')", 3.0)
s.close()
