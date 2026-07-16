"""Push NPU agent files to ESP32 via raw REPL (no mpremote needed)."""
import serial, time, sys, os

PORT = sys.argv[1] if len(sys.argv) > 1 else "COM13"
MAIN_PY = os.path.join(os.path.dirname(__file__), "..", "firmware", "esp32-agent", "main.py")

def raw_repl_exec(s, code: str) -> str:
    """Execute Python code via MicroPython raw REPL and return output."""
    # Enter raw REPL
    s.write(b"\r\x03\x03")
    time.sleep(0.3)
    s.read(s.in_waiting or 1)  # Clear buffer
    s.write(b"\r\x01")
    time.sleep(0.3)
    resp = s.read(s.in_waiting or 1)
    if b"raw REPL" not in resp:
        # Try again
        s.write(b"\r\x01")
        time.sleep(0.3)
        s.read(s.in_waiting or 1)

    # Send code with soft-reset escape
    s.write(code.encode() + b"\r\x04")
    time.sleep(2)
    result = s.read(s.in_waiting or 1)
    return result.decode(errors="replace")

def push_file(s, local_path: str, remote_name: str):
    """Push a file to MicroPython filesystem via raw REPL."""
    with open(local_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Escape the content for inline exec
    escaped = content.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n").replace("\r", "")

    code = f"""
try:
    with open('/{remote_name}', 'w') as f:
        f.write('{escaped}')
    print('OK:{remote_name}')
except Exception as e:
    print('FAIL:{remote_name}:', e)
"""
    result = raw_repl_exec(s, code)
    print(f"  {remote_name}: {result.strip()[:200]}")

def main():
    # Read main.py
    if not os.path.exists(MAIN_PY):
        print(f"ERROR: {MAIN_PY} not found")
        sys.exit(1)

    # Read config
    config = (
        '{"device_id":"esp32-s3-npu-01","mqtt_broker":"192.168.1.100",'
        '"mqtt_port":1883,"wifi_ssid":"","wifi_password":"","telemetry_interval":5}'
    )

    print(f"Connecting to {PORT}...")
    s = serial.Serial(PORT, 115200, timeout=3)
    time.sleep(1)

    # Test REPL
    result = raw_repl_exec(s, "print('MicroPython alive')")
    print(f"REPL: {result.strip()[:100]}")

    if "alive" not in result:
        print("REPL not responsive, trying reset...")
        s.dtr = False
        time.sleep(0.2)
        s.dtr = True
        time.sleep(3)
        s.read(s.in_waiting or 1)
        result = raw_repl_exec(s, "print('after reset')")
        print(f"After reset: {result.strip()[:100]}")

    # Push config
    print("Pushing config...")
    raw_repl_exec(s, f"with open('/npu_config.json','w') as f: f.write('''{config}''')")

    # Push main.py via chunked approach (files can be large)
    print(f"Pushing main.py ({os.path.getsize(MAIN_PY)} bytes)...")
    with open(MAIN_PY, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # Write line by line to avoid REPL buffer limits
    raw_repl_exec(s, "f = open('/main.py', 'w')")
    for i in range(0, len(lines), 20):
        chunk = "".join(lines[i:i+20])
        escaped = chunk.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n").replace("\r", "")
        raw_repl_exec(s, f"f.write('{escaped}')")
        print(f"  chunk {i//20 + 1}/{(len(lines)+19)//20}", end="\r")
    raw_repl_exec(s, "f.close()")
    print()

    # Verify
    result = raw_repl_exec(s, "import os; print(os.listdir('/'))")
    print(f"Files: {result.strip()[:200]}")

    # Soft reset to run the agent
    print("Soft-resetting device...")
    s.write(b"\r\x04")  # Soft reset
    time.sleep(3)
    s.read(s.in_waiting or 1)

    s.close()
    print("Done! Device should now run NPU agent on boot.")

if __name__ == "__main__":
    main()
