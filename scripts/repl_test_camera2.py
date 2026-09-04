import serial
import time
import sys

port = sys.argv[1] if len(sys.argv) > 1 else "COM10"


def open_port():
    for _ in range(5):
        try:
            s = serial.Serial(port, 115200, timeout=5)
            time.sleep(0.3)
            return s
        except Exception:
            time.sleep(1.0)
    raise RuntimeError("cannot open " + port)


def drain(s, wait):
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


s = open_port()
s.write(b"\x03")
time.sleep(0.6)
drain(s, 0.5)


def run(c, wait=2.0):
    s.write(c.encode() + b"\r\n")
    out = drain(s, wait)
    print(">>>", c)
    print(out)
    return out


# Camera init + capture, hardened against log-burst serial churn
run("import camera_capture; camera_capture.init(); print('INIT_OK')", 5.0)
run("import gc; gc.collect(); f=camera_capture.capture(); print('CAPTURED', len(f), bytes(f[:3]).hex())", 8.0)
run("import sd; r=sd.save_photo(f); print('SAVED', r)", 6.0)

s.close()
