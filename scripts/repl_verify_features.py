import serial
import time
import sys

port = sys.argv[1] if len(sys.argv) > 1 else "COM10"
s = serial.Serial(port, 115200, timeout=3)
time.sleep(0.3)
s.write(b"\x03")
time.sleep(0.5)
s.read(s.in_waiting or 1)

cmds = [
    "import gc; gc.collect(); print('heap free:', gc.mem_free())",
    "import camera; print('camera OK', [x for x in dir(camera) if not x.startswith('_')])",
    "import machine; print('I2S PDM:', hasattr(machine, 'I2S'))",
    "import board; print('camera attr:', getattr(board, 'CAMERA', 'n/a'))",
]
for c in cmds:
    s.write(c.encode() + b"\r\n")
    time.sleep(1.6)
    print(">>>", c)
    print(s.read(s.in_waiting or 1).decode(errors="replace"))
s.close()
