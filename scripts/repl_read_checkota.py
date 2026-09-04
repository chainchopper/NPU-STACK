import serial
import time
import sys

port = sys.argv[1] if len(sys.argv) > 1 else "COM10"
s = serial.Serial(port, 115200, timeout=4)
time.sleep(0.3)
s.write(b"\x03")
time.sleep(0.5)
s.read(s.in_waiting or 1)

code = "f=open('/main.py'); t=f.read(); f.close(); i=t.find('def check_ota'); print(t[i:i+1000] if i>=0 else 'NO check_ota')"
s.write(code.encode() + b"\r\n")
time.sleep(2.5)
print(s.read(s.in_waiting or 1).decode(errors="replace"))
s.close()
