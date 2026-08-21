"""Nirvana Face — animated agent face demo (marketplace app).

Cycles the full emotion gamut with periodic blinking. Run directly on the
board (menu → Nirvana Face) or in the Device Playground emulator.
"""
import math
import time

import face


def run():
    f = face.Face()
    names = list(face.EMOTIONS.keys())
    t0 = time.time()
    # ~12s showcase: one emotion per second, blink every ~3s, mouth moves when
    # talking/listening.
    while time.time() - t0 < 12.0:
        t = time.time() - t0
        blink = 1.0 if (t % 3.0) < 0.12 else 0.0
        name = names[int(t) % len(names)]
        mouth = (0.5 + 0.5 * math.sin(t * 8)) if name in ("talking", "listening") else 0.0
        f.draw(name, blink=blink, mouth=mouth)  # draw() pushes the frame itself
        time.sleep(0.06)
    # settle on a happy face
    f.draw("happy")
