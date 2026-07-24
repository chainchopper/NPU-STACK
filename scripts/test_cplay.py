import serial, time, json
s = serial.Serial("COM32", 115200, timeout=2)
time.sleep(2)
cmd = json.dumps({"command": "HELP"}).encode() + b"\r\n"
s.write(cmd)
time.sleep(1)
r = s.read(500)
print(r.decode("utf-8", errors="replace")[:300])
s.close()
