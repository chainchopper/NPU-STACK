"""Generate SD-card sprite assets for Nirvana OS menu icons.

Renders the menu icon set as 28x28 RGB565 big-endian .spr files:
    4-byte header (w u16be, h u16be) + w*h*2 bytes of pixel payload.

Output lands in assets/sd/icons/ (tracked canonical source) — copy to the
device with raw_copy.py (mounts /sd in-session first; plain mpremote fs cp can
silently write to the internal flash instead):

    .venv\\Scripts\\python.exe scripts/raw_copy.py COM10 assets/sd/icons/app.spr:/sd/assets/icons/app.spr ...

Usage: .venv\\Scripts\\python.exe scripts/gen_sd_assets.py
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "assets", "sd", "icons")

SIZE = 28
FG = (255, 255, 255)


def _rgb565_be(r, g, b):
    c = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
    return bytes((c >> 8, c & 0xFF))


def _save(name, draw_fn):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (SIZE, SIZE), (0, 0, 0))
    d = ImageDraw.Draw(img)
    draw_fn(d)
    payload = bytearray()
    px = img.load()
    for y in range(SIZE):
        for x in range(SIZE):
            r, g, b = px[x, y]
            payload += _rgb565_be(r, g, b)
    header = bytes((SIZE >> 8, SIZE & 0xFF, SIZE >> 8, SIZE & 0xFF))
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name + ".spr")
    with open(path, "wb") as f:
        f.write(header + payload)
    print("%s.spr  %d bytes" % (name, 4 + len(payload)))


def _c(d, cx, cy, r, fill=False):
    box = [cx - r, cy - r, cx + r, cy + r]
    if fill:
        d.ellipse(box, fill=FG)
    else:
        d.ellipse(box, outline=FG, width=2)


def main():
    if "PIL" not in sys.modules:
        try:
            import PIL  # noqa: F401
        except ImportError:
            print("Pillow required: .venv\\Scripts\\python.exe -m pip install Pillow")
            return 1

    mid = SIZE // 2

    # status: ring + filled core
    _save("status", lambda d: (_c(d, mid, mid, 11), _c(d, mid, mid, 4, True)))

    # settings: gear-ish — ring + cross spokes
    def settings(d):
        _c(d, mid, mid, 8)
        _c(d, mid, mid, 2, True)
        d.line([mid, mid - 13, mid, mid - 8], fill=FG, width=2)
        d.line([mid, mid + 8, mid, mid + 13], fill=FG, width=2)
        d.line([mid - 13, mid, mid - 8, mid], fill=FG, width=2)
        d.line([mid + 8, mid, mid + 13, mid], fill=FG, width=2)
    _save("settings", settings)

    # store: bag outline + handle arc
    def store(d):
        d.rectangle([mid - 11, mid - 6, mid + 11, mid + 11], outline=FG, width=2)
        d.arc([mid - 7, mid - 14, mid + 7, mid], 180, 360, fill=FG, width=2)
    _save("store", store)

    # wifi: dot + two arcs
    def wifi(d):
        _c(d, mid, mid + 8, 3, True)
        d.arc([mid - 9, mid - 2, mid + 9, mid + 16], 200, 340, fill=FG, width=2)
        d.arc([mid - 14, mid - 7, mid + 14, mid + 21], 200, 340, fill=FG, width=2)
    _save("wifi", wifi)

    # reboot: arc + stem
    def reboot(d):
        d.arc([mid - 10, mid - 10, mid + 10, mid + 10], 40, 320, fill=FG, width=2)
        d.line([mid, mid - 13, mid, mid - 5], fill=FG, width=2)
    _save("reboot", reboot)

    # camera: body + bump + lens
    def camera(d):
        d.rectangle([mid - 12, mid - 7, mid + 12, mid + 9], outline=FG, width=2)
        d.rectangle([mid - 5, mid - 12, mid + 3, mid - 7], outline=FG, width=2)
        _c(d, mid, mid + 1, 5, True)
    _save("camera", camera)

    # app: rounded square + dot
    def app(d):
        d.rectangle([mid - 10, mid - 10, mid + 10, mid + 10], outline=FG, width=2)
        _c(d, mid, mid, 4, True)
    _save("app", app)

    print("done ->", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
