"""Watch COM9 for enumeration flapping (boot-loop detector).

Samples whether COM9 is present/openable over ~10 seconds. If the device is
boot-looping (ROM -> OPI crash -> reset -> ROM), the CDC port will appear and
disappear, or open-but-never-yield-data. If it's a stable download stub, the
port stays present and openable the whole time.
"""
import time
import serial

PORT = "COM9"
SAMPLES = 40
INTERVAL = 0.25

present = 0
openable = 0
results = []
for i in range(SAMPLES):
    try:
        s = serial.Serial(PORT, 115200, timeout=0.2)
        s.close()
        ok = True
    except Exception:
        ok = False
    results.append(ok)
    if ok:
        openable += 1
    time.sleep(INTERVAL)

print("samples:", SAMPLES)
print("openable:", openable, "/", SAMPLES)
print("pattern (1=open 0=fail):")
print("".join("1" if r else "0" for r in results))
