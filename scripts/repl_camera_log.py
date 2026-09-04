import serial
import time
import sys

port = sys.argv[1] if len(sys.argv) > 1 else "COM10"
s = serial.Serial(port, 115200, timeout=5)
s.setDTR(False)
s.setRTS(False)
time.sleep(0.3)


def drain(wait):
    end = time.time() + wait
    buf = b""
    while time.time() < end:
        try:
            n = s.in_waiting
        except Exception:
            break
        if n:
            buf += s.read(n)
        else:
            time.sleep(0.05)
    return buf.decode(errors="replace")


# Interrupt to REPL, then enable verbose camera logging and capture
s.write(b"\x03")
time.sleep(0.5)
drain(0.5)

s.write(b"import esp32, camera\r\n")
drain(1.0)
# Raise log level for the camera/sccb tags via esp32 log control if available
s.write(b"camera.init(0, format=camera.JPEG, framesize=camera.FRAME_QVGA, fb_location=camera.PSRAM)\r\n")
print("=== init output ===")
print(drain(5.0))
s.write(b"f=camera.capture()\r\n")
print("=== capture output (look for cam_hal/sccb/gdma log lines) ===")
print(drain(6.0))
s.close()
