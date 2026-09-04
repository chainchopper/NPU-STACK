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


# Can we allocate a full 240x240x2 framebuffer now that PSRAM is live?
print(run("import gc; gc.collect(); fb=bytearray(240*240*2); print('FB_ALLOC_OK', len(fb), 'heap', gc.mem_free())", 5))
# And is it in PSRAM (not internal SRAM)? check address region
print(run("import gc; gc.collect(); fb=bytearray(115200); import uctypes; print('FB_ADDR', hex(uctypes.addressof(fb)))", 5))
s.close()
