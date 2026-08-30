"""Copy files to a MicroPython device over the raw REPL (CH343-safe).

Some USB-UART bridges (Waveshare CH343) don't work with mpremote's DTR/RTS
reset handshake, but the raw REPL itself is fine. This script opens the port
without resetting, enters raw REPL manually, and writes each file via a
`ubinascii.unhexlify` (MicroPython has no `base64`) exec command.

Usage:
    python raw_copy.py <port> <local:remote> [<local:remote> ...]
Example:
    python raw_copy.py COM23 firmware/nirvana-os/main.py:/main.py
"""
import sys
import time

import serial


def open_port(port):
    s = serial.Serial(port, 115200, timeout=0.5)
    s.dtr = False
    s.rts = False
    time.sleep(0.3)
    return s


def drain(s):
    try:
        s.read(s.in_waiting or 1)
    except Exception:
        pass


def enter_raw(s):
    s.write(b"\x03")  # Ctrl-C: interrupt / ensure normal REPL
    time.sleep(0.25)
    drain(s)
    s.write(b"\x01")  # Ctrl-A: enter raw REPL
    return read_until(s, b">", timeout=4)


def read_until(s, ending, timeout=5):
    data = b""
    t0 = time.time()
    while time.time() - t0 < timeout:
        if data.endswith(ending) and data:
            return data
        n = s.in_waiting
        if n:
            data += s.read(1)
        else:
            time.sleep(0.005)
    return data


def exec_raw(s, code, timeout=10):
    """Execute `code` with canonical raw-REPL framing (prompt-wait + \\x04)."""
    read_until(s, b">", timeout=2)   # wait for the raw-REPL prompt
    payload = code.encode("utf-8")
    # Write in small pieces with a tiny gap — the CH343 drops bytes when a big
    # burst overruns the ESP32's UART RX buffer (no hardware flow control).
    for i in range(0, len(payload), 32):
        s.write(payload[i:i + 32])
        time.sleep(0.002)
    s.write(b"\x04")                  # Ctrl-D: execute
    data = read_until(s, b"\x04", timeout=timeout)
    if data.endswith(b"\x04"):
        data = data[:-1]
    if s.in_waiting:
        s.read(1)                     # trailing '>'
    return data


def file_checksum(s, remote):
    code = "f=open('%s','rb');d=f.read();f.close();print(len(d), sum(d))" % remote
    out = exec_raw(s, code)
    if out.startswith(b"OK"):
        out = out[2:]  # raw REPL prefixes the stdout with 'OK' (no newline)
    try:
        tail = out.decode("utf-8", "ignore").strip().splitlines()[-1].split()
        return int(tail[0]), int(tail[1])
    except Exception:
        return None, None


def write_file(s, remote, data):
    host_sum = sum(data)
    CHUNK = 128
    for attempt in range(3):
        exec_raw(s, "f=open('%s','wb');f.close()\n" % remote)
        bad = False
        for i in range(0, len(data), CHUNK):
            chunk = data[i:i + CHUNK]
            code = (
                "import ubinascii\n"
                "d=ubinascii.unhexlify('%s')\n"
                "f=open('%s','ab')\n"
                "f.write(d)\n"
                "f.close()\n" % (chunk.hex(), remote)
            )
            out = exec_raw(s, code)
            if b"Traceback" in out or b"Error" in out:
                bad = True
                break
            time.sleep(0.004)
        if bad:
            continue
        length, csum = file_checksum(s, remote)
        if length == len(data) and csum == host_sum:
            return b"wrote"
        # silently corrupted (hex-to-hex) — rewrite
    return b"mismatch"


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    port = sys.argv[1]
    files = sys.argv[2:]

    s = open_port(port)
    if not enter_raw(s):
        print("ERROR: could not enter raw REPL on", port)
        return 1

    # Mount the SD card when any target path lives under /sd — otherwise writes
    # silently land in a same-named directory on the internal flash.
    if any((spec.rsplit(":", 1)[-1] if ":" in spec[1:] else "").startswith("/sd/") for spec in files):
        out = exec_raw(s, "import sd\nprint('mount:', sd.mount())\n")
        if b"True" not in out:
            print("ERROR: SD mount failed; refusing to write /sd paths to flash")
            return 1

    for spec in files:
        if ":" in spec[1:]:
            # rsplit so Windows drive letters (J:\...) survive the split.
            local, remote = spec.rsplit(":", 1)
        else:
            local, remote = spec, "/" + spec.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        # Create parent dirs (os.mkdir has no -p; walk the path).
        if "/" in remote.strip("/"):
            parts = remote.strip("/").split("/")[:-1]
            mkdir = "import os\n"
            acc = ""
            for p in parts:
                acc += "/" + p
                mkdir += (
                    "try: os.mkdir('%s')\n"
                    "except OSError: pass\n" % acc
                )
            exec_raw(s, mkdir)
        with open(local, "rb") as f:
            data = f.read()
        out = write_file(s, remote, data)
        if b"wrote" in out:
            print("ok", remote, len(data), "bytes")
        else:
            print("FAIL", remote, "->", out[-160:])

    # soft reset so the device runs its new boot.py/main.py
    s.write(b"\x02")  # Ctrl-B: exit raw REPL
    time.sleep(0.2)
    s.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
