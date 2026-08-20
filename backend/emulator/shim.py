"""Host-side MicroPython shim for the Nirvana OS emulator.

Makes Nirvana OS app code (written for the ESP32-S3) run unchanged in a
plain CPython process: a virtual 240x240 RGB565 framebuffer stands in for the
GC9A01 display, a stub touch panel accepts injected coordinates, and the
machine/network modules degrade gracefully.

The runner calls :func:`install` first, then execs the app source and calls
``run()``. Each ``display.show()`` pushes the framebuffer through the frame
sink the runner registered.
"""
from __future__ import annotations

import os
import sys
import threading
import time as _time

WIDTH = 240
HEIGHT = 240

# RGB565 palette names used by the device drivers.
GREEN = 0x07E0
WHITE = 0xFFFF
BLUE = 0x001F
YELLOW = 0xFFE0
RED = 0xF800
PURPLE = 0x8010
CYAN = 0x07FF
BLACK = 0x0000
GRAY = 0x8410


# ── RGB565 helpers ──────────────────────────────────────────────────

def _rgb565(r, g, b):
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


def _unpack_rgb565(c):
    r = (c >> 11) & 0x1F
    g = (c >> 5) & 0x3F
    b = c & 0x1F
    return (r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)


# ── Virtual framebuffer ─────────────────────────────────────────────

class FrameBuffer:
    """Minimal RGB565 framebuffer with the MicroPython framebuf API surface."""

    def __init__(self, width=WIDTH, height=HEIGHT):
        self.width = width
        self.height = height
        self.buffer = bytearray(width * height * 2)
        from PIL import Image
        self._img = Image.new("RGB", (width, height), (0, 0, 0))

    # framebuf constants
    RGB565 = 1
    MONO_HLSB = 3

    def _blit_img(self):
        raw = self._img.tobytes()
        buf = self.buffer
        idx = 0
        for i in range(0, len(raw), 3):
            r, g, b = raw[i], raw[i + 1], raw[i + 2]
            c = _rgb565(r, g, b)
            buf[idx] = c >> 8
            buf[idx + 1] = c & 0xFF
            idx += 2

    def fill(self, c):
        r, g, b = _unpack_rgb565(c)
        from PIL import ImageDraw
        ImageDraw.Draw(self._img).rectangle([0, 0, self.width, self.height], fill=(r, g, b))

    def pixel(self, x, y, c=None):
        if c is None:
            r, g, b = self._img.getpixel((x, y))
            return _rgb565(r, g, b)
        r, g, b = _unpack_rgb565(c)
        if 0 <= x < self.width and 0 <= y < self.height:
            self._img.putpixel((x, y), (r, g, b))

    def hline(self, x, y, w, c):
        r, g, b = _unpack_rgb565(c)
        from PIL import ImageDraw
        ImageDraw.Draw(self._img).line([x, y, x + w - 1, y], fill=(r, g, b))

    def vline(self, x, y, h, c):
        r, g, b = _unpack_rgb565(c)
        from PIL import ImageDraw
        ImageDraw.Draw(self._img).line([x, y, x, y + h - 1], fill=(r, g, b))

    def fill_rect(self, x, y, w, h, c):
        r, g, b = _unpack_rgb565(c)
        from PIL import ImageDraw
        ImageDraw.Draw(self._img).rectangle([x, y, x + w - 1, y + h - 1], fill=(r, g, b))

    def rect(self, x, y, w, h, c):
        r, g, b = _unpack_rgb565(c)
        from PIL import ImageDraw
        ImageDraw.Draw(self._img).rectangle([x, y, x + w - 1, y + h - 1], outline=(r, g, b))

    def text(self, s, x, y, c=WHITE):
        r, g, b = _unpack_rgb565(c)
        from PIL import ImageDraw, ImageFont
        try:
            font = ImageFont.load_default()
        except Exception:
            font = None
        ImageDraw.Draw(self._img).text((x, y), s, fill=(r, g, b), font=font)

    def center_text(self, s, y, c=WHITE):
        from PIL import ImageDraw, ImageFont
        try:
            font = ImageFont.load_default()
        except Exception:
            font = None
        draw = ImageDraw.Draw(self._img)
        w = draw.textlength(s, font=font) if hasattr(draw, "textlength") else len(s) * 6
        x = max(0, (self.width - int(w)) // 2)
        draw.text((x, y), s, fill=_unpack_rgb565(c), font=font)

    def show(self):
        """Flush the virtual framebuffer to the emulator (no-op SPI write)."""
        _emit_frame()

    def backlight(self, on=True):
        return None


# ── Global state ────────────────────────────────────────────────────

_frame_sink = None
_touch_queue = []
_touch_lock = threading.Lock()
_display = None


def _emit_frame():
    if _frame_sink is not None:
        _display._blit_img()
        _frame_sink(bytes(_display.buffer))


class _DisplayModule:
    def __init__(self):
        global _display
        _display = FrameBuffer(WIDTH, HEIGHT)
        self.GREEN = GREEN
        self.WHITE = WHITE
        self.BLUE = BLUE
        self.YELLOW = YELLOW
        self.RED = RED
        self.PURPLE = PURPLE
        self.CYAN = CYAN

    def init(self):
        return _display

    def get(self):
        return _display

    def splash(self, version):
        _display.fill(BLACK)
        _display.center_text("NIRVANA", 70, GREEN)
        _display.center_text("OS v" + version, 86, WHITE)
        _emit_frame()

    def status(self, msg, color=WHITE):
        _display.fill_rect(0, 220, _display.width, 20, BLACK)
        _display.center_text(msg[:14], 220, color)
        _emit_frame()

    def brightness(self, level=75):
        return None


class _TouchModule:
    def read(self):
        with _touch_lock:
            if _touch_queue:
                return _touch_queue.pop(0)
        return None


def push_touch(x, y):
    with _touch_lock:
        _touch_queue.append((int(x), int(y)))


# ── machine / network / misc stubs ──────────────────────────────────

class _Pin:
    IN = 0
    OUT = 1

    def __init__(self, num, mode=-1, value=None, pull=None):
        self.num = num
        self._value = 0 if value is None else value

    def value(self, v=None):
        if v is None:
            return self._value
        self._value = 1 if v else 0

    def on(self):
        self._value = 1

    def off(self):
        self._value = 0

    def __call__(self, v=None):
        return self.value(v)


class _SPI:
    def __init__(self, bus, **kwargs):
        self.bus = bus

    def write(self, data):
        return len(data)

    def read(self, n):
        return b"\x00" * n

    def readinto(self, buf):
        return len(buf)


class _I2C:
    def __init__(self, bus, **kwargs):
        self.bus = bus

    def scan(self):
        return []

    def readfrom(self, addr, n):
        return b"\x00" * n

    def readfrom_mem(self, addr, reg, n):
        return b"\x00" * n

    def writeto(self, addr, buf):
        return len(buf)


class _PWM:
    def __init__(self, pin, **kwargs):
        self.pin = pin

    def duty(self, v=None):
        return 0


class _ADC:
    def __init__(self, pin):
        self.pin = pin

    def read(self):
        return 0

    def read_uv(self):
        return 0


class _Machine:
    def __init__(self):
        self.Pin = _Pin
        self.SPI = _SPI
        self.I2C = _I2C
        self.PWM = _PWM
        self.ADC = _ADC
        self.freq = lambda f=None: 240_000_000
        self.unique_id = lambda: b"\xd8\x3b\xda\x89\x31\xe4"

    def soft_reset(self):
        raise SystemExit(0)

    def reset(self):
        raise SystemExit(0)

    def __getattr__(self, name):
        raise AttributeError(name)


class _WLAN:
    def __init__(self, iface):
        self.iface = iface

    def active(self, v=None):
        return True

    def connect(self, ssid="", pwd=""):
        return None

    def disconnect(self):
        return None

    def isconnected(self):
        return True

    def ifconfig(self):
        return ("192.168.1.94", "255.255.255.0", "192.168.1.1", "8.8.8.8")


class _Network:
    STA_IF = 0
    AP_IF = 1

    def WLAN(self, iface):
        return _WLAN(iface)


class _Gc:
    def collect(self):
        return 0

    def mem_free(self):
        return 4_000_000


class _TimeShim:
    """stdlib time + MicroPython aliases."""
    def __init__(self):
        self.sleep = _time.sleep
        self.time = _time.time
        self.monotonic = _time.monotonic

    def sleep_ms(self, ms):
        _time.sleep(ms / 1000.0)

    def sleep_us(self, us):
        _time.sleep(us / 1_000_000.0)

    def ticks_ms(self):
        return int(_time.monotonic() * 1000)

    def ticks_us(self):
        return int(_time.monotonic() * 1_000_000)

    def ticks_diff(self, a, b):
        return a - b


# ── board / sd / settings stubs ─────────────────────────────────────

class _Board:
    def get_device_id(self):
        return "d83bda8931e4"

    def detect(self):
        return {"display": True, "touch": True, "sd": False, "rtc": False,
                "camera": True, "mic": True, "wifi": True, "bt": True,
                "board_profile": "xiao-sense", "i2c_addrs": []}

    def summary(self, caps):
        return ("display=%s touch=%s sd=%s rtc=%s camera=%s mic=%s wifi=%s bt=%s" % (
            caps["display"], caps["touch"], caps["sd"], caps["rtc"],
            caps["camera"], caps["mic"], caps["wifi"], caps["bt"]))


class _Sd:
    def is_mounted(self):
        return False

    def mount(self):
        return False

    def list_apps(self):
        return []


# ── Install ─────────────────────────────────────────────────────────

def install(frame_sink=None):
    """Install all shim modules into sys.modules."""
    global _frame_sink
    _frame_sink = frame_sink

    display = _DisplayModule()

    shims = {
        "machine": _Machine(),
        "network": _Network(),
        "gc": _Gc(),
        "time": _TimeShim(),
        "display": display,
        "touch": _TouchModule(),
        "board": _Board(),
        "sd": _Sd(),
        "framebuf": FrameBuffer,
    }
    for name, mod in shims.items():
        sys.modules[name] = mod

    # os: stdlib os, patched with the MicroPython surface apps rely on.
    import types
    if not hasattr(os, "uname"):
        def uname():
            return types.SimpleNamespace(
                machine="Generic ESP32S3 module with ESP32S3",
                release="1.28.0",
                version="v1.28.0 on 2026-04-06",
                sysname="esp32")
        os.uname = uname
    if not hasattr(os, "mount"):
        os.mount = lambda *a, **k: None
    if not hasattr(os, "umount"):
        os.umount = lambda *a, **k: None
    if not hasattr(os, "statvfs"):
        os.statvfs = lambda path: (4096, 4096, 65536, 65536, 65536, 0, 0, 0, 0, 4096)

    return display
