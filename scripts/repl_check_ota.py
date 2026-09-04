import serial
import time
import sys

port = sys.argv[1] if len(sys.argv) > 1 else "COM10"
s = serial.Serial(port, 115200, timeout=4)
time.sleep(0.3)
s.write(b"\x03")
time.sleep(0.5)
s.read(s.in_waiting or 1)

cmds = [
    "import json; c=json.load(open('/config.json')); print('ota:', c.get('ota_enabled'), 'chan:', repr(c.get('update_channel')), 'ssid:', repr(c.get('wifi_ssid')))",
    "import network; w=network.WLAN(network.STA_IF); print('wifi connected:', w.isconnected(), w.ifconfig()[0] if w.isconnected() else '')",
]
for c in cmds:
    s.write(c.encode() + b"\r\n")
    time.sleep(1.6)
    print(">>>", c)
    print(s.read(s.in_waiting or 1).decode(errors="replace"))
s.close()
