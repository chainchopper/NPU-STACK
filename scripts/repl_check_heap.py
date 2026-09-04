import serial
import time
import sys

port = sys.argv[1] if len(sys.argv) > 1 else "COM10"
s = serial.Serial(port, 115200, timeout=3)
time.sleep(0.5)
s.write(b"\x03\x03")
time.sleep(0.8)
s.read(s.in_waiting or 1)

script = "\n".join([
    "import gc, esp32",
    "gc.collect()",
    "print('free heap:', gc.mem_free())",
    "print('IDF heaps:')",
    "for h in esp32.idf_heap_info(0): print(h)",
    "",
])

s.write(script.encode() + b"\r\n")
time.sleep(2.5)
out = s.read(s.in_waiting or 1).decode(errors="replace")
print(out)
s.close()
