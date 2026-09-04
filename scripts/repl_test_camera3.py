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
            time.sleep(0.1)
    return buf.decode(errors="replace")


def run(c, wait=2.0):
    s.write(c.encode() + b"\r\n")
    out = drain(wait)
    print(">>>", c)
    print(out)
    return out


run("import camera, camera_capture", 2.0)
run("camera_capture.init(); print('init done')", 5.0)
# Retry capture several times - the sensor often returns empty until VSYNC/PLL locks
for i in range(6):
    out = run("f = camera.capture(); print('try', %d, 'len', len(f) if f else 0)" % i, 4.0)
    if "len" in out and "len 0" not in out:
        break
run("f2 = camera.capture(); print('final', len(f2) if f2 else 0, bytes(f2[:3]).hex() if f2 else '')", 5.0)
s.close()
