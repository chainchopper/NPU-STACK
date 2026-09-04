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


def run(c, wait=2.5):
    s.write(c.encode() + b"\r\n")
    out = drain(wait)
    print(">>>", c)
    print(out)
    return out


run("import camera", 2.0)
run("print('attrs:', [a for a in dir(camera) if 'sensor' in a.lower() or 'probe' in a.lower() or 'pid' in a.lower()])", 2.0)
run("camera.init(0, format=camera.JPEG, fb_location=camera.PSRAM, framesize=camera.FRAME_240X240); print('init 240x240 ok')", 6.0)
time.sleep(1.0)
for i in range(8):
    out = run("f=camera.capture(); print('c%d' % i, len(f) if f else 0)", 3.0)
    if ("c%d" % i) in out and " 0" not in out.split(("c%d" % i))[-1][:6]:
        break
run("camera.deinit(); print('deinit ok')", 2.0)
s.close()
