import serial
import time
import sys

port = sys.argv[1] if len(sys.argv) > 1 else "COM10"
CHANNEL = "http://192.168.1.232:8010/api/fleet/ota/nirvana-os"

s = serial.Serial(port, 115200, timeout=4)
time.sleep(0.3)
s.write(b"\x03")
time.sleep(0.5)
s.read(s.in_waiting or 1)

# Write with explicit close (LittleFS buffers; json.dump(open(...)) leaks the
# handle so the write isn't flushed before readback). Read back only the key.
cmds = [
    "import json; c=json.load(open('/config.json')); c['update_channel']='%s'; f=open('/config.json','w'); json.dump(c,f); f.close(); print('wrote, in-mem:', repr(c['update_channel']))" % CHANNEL,
    "import json; f=open('/config.json'); d=json.load(f); f.close(); print('readback channel:', repr(d.get('update_channel')))",
]
for c in cmds:
    s.write(c.encode() + b"\r\n")
    time.sleep(2.0)
    print(">>>", c)
    print(s.read(s.in_waiting or 1).decode(errors="replace"))
s.close()
