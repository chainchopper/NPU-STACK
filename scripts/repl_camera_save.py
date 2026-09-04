import serial
import time
import sys

port = sys.argv[1] if len(sys.argv) > 1 else "COM10"
s = serial.Serial(port, 115200, timeout=5)
time.sleep(0.3)
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


run("import camera, sd, gc; gc.collect()", 2.0)
run("camera.init(0, format=camera.JPEG, framesize=camera.FRAME_VGA, fb_location=camera.DRAM, xclk_freq=camera.XCLK_20MHz); print('init ok')", 6.0)
time.sleep(1.0)
# Discard a few frames for AE/exposure to settle
for i in range(3):
    run("camera.capture()", 3.0)
run("f=camera.capture(); print('frame', len(f) if f else 0, bytes(f[:3]).hex() if f else '')", 5.0)
run("r=sd.save_photo(bytes(f)) if f else None; print('saved:', r)", 6.0)
run("import os; print('photos:', os.listdir('/sd/photos') if 'photos' in os.listdir('/sd') else 'none')", 3.0)
s.close()
