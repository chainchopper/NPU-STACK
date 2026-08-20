"""Run a Nirvana OS app inside the host MicroPython shim.

stdin/stdout framed protocol (used by the /ws/emulator WebSocket endpoint):

  stdout:  FRAME:<base64 RGB565>   — a virtual display frame after each show()
           LOG:<text>              — app print() output
  stdin:   TOUCH:x,y               — inject a touch point into the touch shim
           STOP                    — end the session
"""
import base64
import sys
import threading

from backend.emulator import shim


class _LogWriter:
    def __init__(self, real):
        self.real = real

    def write(self, s):
        if s:
            for line in s.splitlines():
                if line:
                    self.real.write("LOG:" + line + "\n")
            self.real.flush()

    def flush(self):
        self.real.flush()


def main():
    if len(sys.argv) < 2:
        sys.stderr.write("usage: runner.py <app_source.py>\n")
        return

    src_path = sys.argv[1]
    real_stdout = sys.__stdout__

    def frame_sink(rgb565):
        real_stdout.write("FRAME:" + base64.b64encode(rgb565).decode() + "\n")
        real_stdout.flush()

    sys.stdout = _LogWriter(real_stdout)
    shim.install(frame_sink)

    # stdin thread — inject touch coordinates from the browser.
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
        except Exception:
            pass

    threading.Thread(target=stdin_reader, daemon=True).start()

    try:
        with open(src_path, encoding="utf-8") as f:
            src = f.read()
    except Exception as e:
        real_stdout.write("LOG:cannot read app: %s\n" % e)
        return

    ns = {"__name__": "app"}
    try:
        exec(compile(src, src_path, "exec"), ns)
    except SystemExit:
        return
    except Exception as e:
        real_stdout.write("LOG:app error: %s\n" % e)
        return

    run = ns.get("run")
    if callable(run):
        try:
            run()
        except SystemExit:
            return
        except Exception as e:
            real_stdout.write("LOG:app error: %s\n" % e)


if __name__ == "__main__":
    main()
