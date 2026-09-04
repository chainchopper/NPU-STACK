import serial
import time
import sys

port = sys.argv[1] if len(sys.argv) > 1 else "COM10"
s = serial.Serial(port, 115200, timeout=10)
time.sleep(0.4)
s.write(b"\x03")
time.sleep(0.6)
s.read(s.in_waiting or 1)


def run(c, wait):
    s.write(c.encode() + b"\r\n")
    end = time.time() + wait
    buf = b""
    while time.time() < end:
        n = s.in_waiting
        if n:
            buf += s.read(n)
        else:
            time.sleep(0.1)
    return buf.decode(errors="replace")


steps = [
    ("import display,gc,time; lcd=display.get(); gc.collect()", 3),
    ("lcd.fill(0); t=time.ticks_ms(); lcd.show(); d=time.ticks_diff(time.ticks_ms(),t); print('FULLSHOW_MS', d)", 10),
    ("t=time.ticks_ms(); lcd.show_region(80,120); d=time.ticks_diff(time.ticks_ms(),t); print('BAND_MS', d)", 8),
    ("import face; f=face.Face(); gc.collect(); t=time.ticks_ms(); f.draw('happy'); d=time.ticks_diff(time.ticks_ms(),t); print('FACEFULL_MS', d)", 12),
    ("t=time.ticks_ms(); f.draw('happy'); d=time.ticks_diff(time.ticks_ms(),t); print('FACEREDRAW_MS', d)", 8),
    ("print('HEAP', gc.mem_free())", 3),
]
for c, w in steps:
    print(run(c, w))
s.close()
