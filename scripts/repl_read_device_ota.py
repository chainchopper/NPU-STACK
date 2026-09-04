import serial
import time
import sys

port = sys.argv[1] if len(sys.argv) > 1 else "COM10"
s = serial.Serial(port, 115200, timeout=4)
time.sleep(0.3)
s.write(b"\x03")
time.sleep(0.5)
s.read(s.in_waiting or 1)


def run(c, wait=2.5):
    s.write(c.encode() + b"\r\n")
    end = time.time() + wait
    buf = b""
    while time.time() < end:
        n = s.in_waiting
        if n:
            buf += s.read(n)
        else:
            time.sleep(0.05)
    print(">>>", c)
    print(buf.decode(errors="replace"))
    return buf.decode(errors="replace")


# Read the device's actual check_ota to see if it pulls multiple files
run("import main; src=main.check_ota; print('check_ota found')", 2.0)
# Print the relevant lines of the on-device main.py OTA function
run("f=open('/main.py'); t=f.read(); f.close(); i=t.find('def check_ota'); print(t[i:i+900])", 3.0)
s.close()
