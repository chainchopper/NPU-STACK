"""Run a Nirvana OS app inside the host MicroPython shim.

stdin/stdout framed protocol (used by the /ws/emulator WebSocket endpoint):

  stdout:  FRAME:<len>\n<len raw RGB565 bytes>  — one frame per display.show()
           LOG:<text>\n                        — app print() output
  stdin:   TOUCH:x,y                           — inject a touch point
           STOP                                — end the session
"""
import json
import os
import sys
import threading

from backend.emulator import shim


def main():
    if len(sys.argv) < 2:
        sys.stderr.write("usage: runner.py <app_source.py>\n")
        return

    # Make real device modules (face, apps, etc.) importable in the emulator so
    # app code can `import face` unchanged.
    _repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    _fw = os.path.join(_repo, "firmware", "nirvana-os")
    if os.path.isdir(_fw) and _fw not in sys.path:
        sys.path.insert(0, _fw)

    src_path = sys.argv[1]
    out = sys.__stdout__.buffer  # binary stdout (length-prefixed protocol)

    def emit_log(text):
        out.write(b"LOG:" + text.encode("utf-8", "replace") + b"\n")
        out.flush()

    def frame_sink(rgb565):
        out.write(b"FRAME:%d\n" % len(rgb565))
        out.write(rgb565)
        out.flush()

    class _LogWriter:
        def write(self, s):
            if s:
                emit_log(s)

        def flush(self):
            pass

    sys.stdout = _LogWriter()
    shim.install(frame_sink)

    # stdin thread — inject touch + sensor updates from the browser.
    def stdin_reader():
        try:
            for line in sys.stdin:
                line = line.strip()
                if not line:
                    continue
                if line == "STOP":
                    break
                if line.startswith("TOUCH:"):
                    _, _, xy = line.partition(":")
                    x, _, y = xy.partition(",")
                    try:
                        shim.push_touch(int(x), int(y))
                    except Exception:
                        pass
                elif line.startswith("SENSOR:"):
                    _, _, payload = line.partition(":")
                    try:
                        data = json.loads(payload)
                        if isinstance(data, dict):
                            for k, v in data.items():
                                shim.set_sensor(k, v)
                    except Exception:
                        pass
                elif line.startswith("BLE:"):
                    # Inject an IMPROV RPC command (hex-encoded bytes) into the
                    # running app's BLE stub — simulates a phone writing GATT.
                    _, _, hexdata = line.partition(":")
                    try:
                        shim.inject_ble_rpc(bytes.fromhex(hexdata))
                    except Exception:
                        pass
                elif line.startswith("ESPNOW:"):
                    # Inject an ESP-NOW frame: ESPNOW:<mac-hex>,<utf8-msg>
                    _, _, payload = line.partition(":")
                    mac, _, msg = payload.partition(",")
                    try:
                        shim.inject_espnow(bytes.fromhex(mac), msg.encode("utf-8"))
                    except Exception:
                        pass
        except Exception:
            pass

    threading.Thread(target=stdin_reader, daemon=True).start()

    try:
        with open(src_path, encoding="utf-8") as f:
            src = f.read()
    except Exception as e:
        emit_log("cannot read app: %s" % e)
        return

    ns = {"__name__": "app"}
    try:
        exec(compile(src, src_path, "exec"), ns)
    except SystemExit:
        return
    except Exception as e:
        emit_log("app error: %s" % e)
        return

    run = ns.get("run")
    if callable(run):
        try:
            run()
        except SystemExit:
            return
        except Exception as e:
            emit_log("app error: %s" % e)


if __name__ == "__main__":
    main()
