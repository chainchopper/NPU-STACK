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
    "import camera; print('camera module OK'); print([x for x in dir(camera) if not x.startswith('_')][:20])",
    "import machine; print('I2S PDM_RX mode const:', getattr(machine.I2S, 'PDM_RX', 'MISSING'))",
    "import board; print('camera cap:', board.detect().get('camera'), board.detect().get('camera_status'))",
]
for c in cmds:
    s.write(c.encode() + b"\r\n")
    time.sleep(2.0)
    print(">>>", c)
    print(s.read(s.in_waiting or 1).decode(errors="replace"))
s.close()
