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


# Deinit any prior state, then init with frame buffer in DRAM (not PSRAM)
run("import camera, gc; gc.collect()", 2.0)
run("camera.deinit()", 2.0)
run("camera.init(0, format=camera.JPEG, framesize=camera.FRAME_QQVGA, fb_location=camera.DRAM, xclk_freq=camera.XCLK_10MHz); print('init dram ok')", 6.0)
time.sleep(1.0)
for i in range(6):
    out = run("f=camera.capture(); print('c" + str(i) + "', len(f) if f else 0, bytes(f[:3]).hex() if f else '')", 4.0)
    if ("c%d" % i) in out and " 0 " not in out and " 0\n" not in out:
        print("GOT FRAME")
        break
s.close()
