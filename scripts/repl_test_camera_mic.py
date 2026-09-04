import serial
import time
import sys

port = sys.argv[1] if len(sys.argv) > 1 else "COM10"
s = serial.Serial(port, 115200, timeout=5)
time.sleep(0.3)
s.write(b"\x03")
time.sleep(0.6)
s.read(s.in_waiting or 1)

def run(c, wait=2.0):
    s.write(c.encode() + b"\r\n")
    time.sleep(wait)
    print(">>>", c)
    print(s.read(s.in_waiting or 1).decode(errors="replace"))

# 1. Fresh capability detect with expansion attached
run("import board; c=board.detect(); print('CAPS camera:', c['camera'], c['camera_status'], '| mic:', c['mic'], c['mic_status'], '| sd:', c['sd'])", 3.0)

# 2. Camera init (lazy - first real init)
run("import camera_capture; camera_capture.init(); print('camera init OK')", 4.0)

# 3. Capture a frame to bytes
run("import camera_capture, gc; gc.collect(); f=camera_capture.capture(); print('captured bytes:', len(f), 'starts:', bytes(f[:3]).hex())", 6.0)

# 4. Save to SD
run("import camera_capture, sd; f=camera_capture.capture(); r=sd.save_photo(f); print('saved:', r)", 6.0)

# 5. PDM mic read (machine.I2S PDM_RX)
run("from machine import I2S, Pin; i2s=I2S(0, sck=Pin(42), sd=Pin(41), mode=I2S.PDM_RX, bits=16, format=I2S.MONO, rate=16000, ibuf=2048); print('i2s pdm ok')", 3.0)
run("b=i2s.read(512); print('mic read bytes:', len(b))", 3.0)
run("i2s.deinit(); print('i2s deinit ok')", 2.0)

s.close()
