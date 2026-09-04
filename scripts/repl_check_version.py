import serial
import time
import sys

port = sys.argv[1] if len(sys.argv) > 1 else "COM10"


def open_port():
    for _ in range(8):
        try:
            s = serial.Serial(port, 115200, timeout=5)
            time.sleep(0.4)
            return s
        except Exception:
            time.sleep(1.0)
    raise RuntimeError("cannot open " + port)


# The device may be mid-OTA (downloading + resetting). Wait, then probe version.
time.sleep(20)
s = open_port()
s.write(b"\x03")
time.sleep(0.6)
s.read(s.in_waiting or 1)
s.write(b"import main; print('RUNNING VERSION:', main.VERSION)\r\n")
end = time.time() + 4
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
print(buf.decode(errors="replace"))
s.close()
