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

import builtins
import json
import os
import os.path
import shutil
import sys
import threading
import time as _time
from datetime import datetime, timezone

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

    def line(self, x0, y0, x1, y1, c):
        r, g, b = _unpack_rgb565(c)
        from PIL import ImageDraw
        ImageDraw.Draw(self._img).line([x0, y0, x1, y1], fill=(r, g, b))

    def fill_rect(self, x, y, w, h, c):
        r, g, b = _unpack_rgb565(c)
        from PIL import ImageDraw
        ImageDraw.Draw(self._img).rectangle([x, y, x + w - 1, y + h - 1], fill=(r, g, b))

    def rect(self, x, y, w, h, c):
        r, g, b = _unpack_rgb565(c)
        from PIL import ImageDraw
        ImageDraw.Draw(self._img).rectangle([x, y, x + w - 1, y + h - 1], outline=(r, g, b))

    def fill_circle(self, x, y, r, c):
        rgb = _unpack_rgb565(c)
        from PIL import ImageDraw
        ImageDraw.Draw(self._img).ellipse([x - r, y - r, x + r, y + r], fill=rgb)

    def circle(self, x, y, r, c):
        rgb = _unpack_rgb565(c)
        from PIL import ImageDraw
        ImageDraw.Draw(self._img).ellipse([x - r, y - r, x + r, y + r], outline=rgb)

    def fill_ellipse(self, x, y, rx, ry, c):
        rgb = _unpack_rgb565(c)
        from PIL import ImageDraw
        ImageDraw.Draw(self._img).ellipse([x - rx, y - ry, x + rx, y + ry], fill=rgb)

    def arc(self, x, y, r, a0, a1, c):
        rgb = _unpack_rgb565(c)
        from PIL import ImageDraw
        ImageDraw.Draw(self._img).arc([x - r, y - r, x + r, y + r], start=a0, end=a1, fill=rgb)

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

    def show_region(self, y0, y1):
        """Partial push — the emulator always sends the full frame."""
        self.show()

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


# ── Virtual SD card + sensors ───────────────────────────────────────

# Host directory backing the virtual /sd mount. The emulator router points
# this at backend/data/emulator_sd via NIRVANA_EMULATOR_SD so files persist
# and can be browsed from the playground UI.
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SD_ROOT = os.environ.get("NIRVANA_EMULATOR_SD") or os.path.join(
    _BACKEND_DIR, "data", "emulator_sd")

_sensor_state = {
    "rtc": "",                 # ISO datetime; empty -> use host clock
    "mic": 512,                # 0..65535 PDM mic level
    "battery_mv": 4200,        # mV
    "temp_c": 24.0,            # deg C
    "light": 400,              # lux
    "adc0": 2048, "adc1": 2048, "adc2": 2048, "adc3": 2048,
    # 6-axis IMU (LSM6DS3-style, mG + milli-deg/s)
    "accel_x": 0, "accel_y": 0, "accel_z": 1000,
    "gyro_x": 0, "gyro_y": 0, "gyro_z": 0,
    # camera (OV2640) mock
    "camera": {"present": True, "w": 320, "h": 240, "frames": 0},
}
_sensor_lock = threading.Lock()

SENSOR_SCHEMA = [
    {"name": "rtc", "label": "RTC (ISO datetime)", "type": "text", "default": ""},
    {"name": "mic", "label": "Mic level", "type": "range", "min": 0, "max": 65535, "step": 1},
    {"name": "battery_mv", "label": "Battery (mV)", "type": "range", "min": 0, "max": 5000, "step": 10},
    {"name": "temp_c", "label": "Temp (°C)", "type": "range", "min": -40, "max": 125, "step": 1},
    {"name": "light", "label": "Light (lux)", "type": "range", "min": 0, "max": 100000, "step": 10},
    {"name": "adc0", "label": "ADC 0", "type": "range", "min": 0, "max": 4095, "step": 1},
    {"name": "adc1", "label": "ADC 1", "type": "range", "min": 0, "max": 4095, "step": 1},
    {"name": "adc2", "label": "ADC 2", "type": "range", "min": 0, "max": 4095, "step": 1},
    {"name": "adc3", "label": "ADC 3", "type": "range", "min": 0, "max": 4095, "step": 1},
    {"name": "accel_x", "label": "Accel X (mG)", "type": "range", "min": -4000, "max": 4000, "step": 10},
    {"name": "accel_y", "label": "Accel Y (mG)", "type": "range", "min": -4000, "max": 4000, "step": 10},
    {"name": "accel_z", "label": "Accel Z (mG)", "type": "range", "min": -4000, "max": 4000, "step": 10},
    {"name": "gyro_x", "label": "Gyro X (mdps)", "type": "range", "min": -2000, "max": 2000, "step": 10},
    {"name": "gyro_y", "label": "Gyro Y (mdps)", "type": "range", "min": -2000, "max": 2000, "step": 10},
    {"name": "gyro_z", "label": "Gyro Z (mdps)", "type": "range", "min": -2000, "max": 2000, "step": 10},
]


def get_sensor_schema():
    return list(SENSOR_SCHEMA)


def set_sensor(name, value):
    with _sensor_lock:
        _sensor_state[name] = value


def get_sensors():
    with _sensor_lock:
        return dict(_sensor_state)


def _map_path(path):
    """Map a device /sd/... path onto the host SD directory."""
    if path == "/sd":
        return SD_ROOT
    if path.startswith("/sd/"):
        return os.path.join(SD_ROOT, path[4:].lstrip("/"))
    return path


def _parse_rtc(iso):
    if iso:
        try:
            return datetime.fromisoformat(iso)
        except Exception:
            pass
    return datetime.now(timezone.utc)


def _rtc_bcd_regs(iso):
    """PCF8563 register dump (0x00..0x0F) as a bytearray, BCD encoded."""
    t = _parse_rtc(iso)
    regs = bytearray(16)

    def bcd(v):
        return ((v // 10) << 4) | (v % 10)

    regs[0x02] = bcd(t.second) & 0x7F        # seconds
    regs[0x03] = bcd(t.minute) & 0x7F        # minutes
    regs[0x04] = bcd(t.hour) & 0x3F          # hours (24h)
    regs[0x05] = bcd(t.day) & 0x3F           # day of month
    regs[0x06] = bcd(t.isoweekday()) & 0x07  # weekday
    regs[0x07] = bcd(t.month) & 0x1F         # month (bit7 = century, clear)
    regs[0x08] = bcd(t.year % 100)           # year
    return regs


class _Sd:
    """Virtual SD card backed by SD_ROOT on the host filesystem."""

    def __init__(self):
        self._mounted = False

    def mount(self):
        try:
            os.makedirs(SD_ROOT, exist_ok=True)
            _seed_sd()
            self._mounted = True
            return True
        except Exception as e:
            print("[EMU] SD mount failed: %s" % e)
            return False

    def is_mounted(self):
        return self._mounted

    def list_dir(self, path="/sd"):
        p = _map_path(path)
        try:
            return sorted(os.listdir(p))
        except Exception:
            return []

    def read_text(self, path):
        try:
            with builtins.open(_map_path(path), "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return None

    def write_text(self, path, text):
        try:
            p = _map_path(path)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with builtins.open(p, "w", encoding="utf-8") as f:
                f.write(text)
            return True
        except Exception:
            return False

    def list_apps(self):
        """Discover installed apps: flat .py files and manifest dirs."""
        apps = []
        if not self._mounted:
            return apps
        for entry in self.list_dir("/sd/apps"):
            p = "/sd/apps/" + entry
            if entry.endswith(".py"):
                mod = entry[:-3]
                name = mod
                txt = self.read_text(p)
                if txt:
                    for line in txt.splitlines():
                        line = line.strip()
                        if line.startswith("NAME") and "=" in line:
                            try:
                                name = line.split("=", 1)[1].strip().strip('"').strip("'")
                            except Exception:
                                pass
                            break
                apps.append((mod, name))
            else:
                name = entry
                appjson = self.read_text(p + "/app.json")
                if appjson:
                    try:
                        name = json.loads(appjson).get("name", entry)
                    except Exception:
                        pass
                apps.append((entry, name))
        return apps


def _seed_sd():
    """Copy marketplace apps into /sd/apps on first use (idempotent)."""
    apps_dir = os.path.join(SD_ROOT, "apps")
    src = os.path.join(_BACKEND_DIR, "marketplace", "apps")
    try:
        os.makedirs(apps_dir, exist_ok=True)
        if os.path.isdir(src):
            for app_id in os.listdir(src):
                src_app = os.path.join(src, app_id)
                if not os.path.isdir(src_app):
                    continue
                dst_app = os.path.join(apps_dir, app_id)
                if os.path.isdir(dst_app):
                    continue  # user may have edited; don't clobber
                shutil.copytree(src_app, dst_app)
    except Exception as e:
        print("[EMU] seed SD failed: %s" % e)


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
        # RTC (PCF8563), touch (CHSC6X), camera (OV2640 SCCB) on the carrier.
        return [0x51, 0x2E, 0x30]

    def readfrom(self, addr, n):
        return b"\x00" * n

    def readfrom_mem(self, addr, reg, n):
        if addr == 0x51:  # PCF8563 RTC
            regs = _rtc_bcd_regs(_sensor_value("rtc", ""))
            return bytes(regs[reg:reg + n])
        return b"\x00" * n

    def writeto(self, addr, buf):
        return len(buf)


def _sensor_value(name, default=None):
    with _sensor_lock:
        return _sensor_state.get(name, default)


class _PWM:
    def __init__(self, pin, **kwargs):
        self.pin = pin

    def duty(self, v=None):
        return 0


class _ADC:
    def __init__(self, pin):
        self.pin = pin

    def read(self):
        # Map the pin to a settable adcN sensor value (12-bit).
        return int(_sensor_value("adc%d" % (self.pin % 4), 2048))

    def read_uv(self):
        return self.read() * 805  # ~3.3V full-scale in microvolts


class _I2S:
    """Host stub of machine.I2S — captures writes so audio can be tested."""

    TX = 0
    RX = 1
    MONO = 0
    STEREO = 1

    def __init__(self, bus, **kwargs):
        self.bus = bus
        self.writes = []

    def write(self, data):
        self.writes.append(bytes(data))
        return len(data)

    def readinto(self, buf):
        return 0

    def deinit(self):
        pass

    def init(self, *a, **k):
        pass

    def irq(self, *a, **k):
        pass

    def shift(self, *a, **k):
        pass


class _Machine:
    def __init__(self):
        self.Pin = _Pin
        self.SPI = _SPI
        self.I2C = _I2C
        self.PWM = _PWM
        self.ADC = _ADC
        self.I2S = _I2S
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
        return {"display": True, "touch": True, "sd": True, "rtc": True,
                "camera": True, "mic": True, "wifi": True, "bt": True,
                "board_profile": "xiao-sense", "i2c_addrs": [0x51, 0x2E, 0x30]}

    def summary(self, caps):
        return ("display=%s touch=%s sd=%s rtc=%s camera=%s mic=%s wifi=%s bt=%s" % (
            caps["display"], caps["touch"], caps["sd"], caps["rtc"],
            caps["camera"], caps["mic"], caps["wifi"], caps["bt"]))


class _SensorsModule:
    """``import sensors`` — read/write the emulated sensor values."""

    def get(self, name, default=None):
        return _sensor_value(name, default)

    def set(self, name, value):
        set_sensor(name, value)

    def state(self):
        return get_sensors()

    def rtc(self):
        return _parse_rtc(_sensor_value("rtc", "")).isoformat()

    def mic(self):
        return int(_sensor_value("mic", 0))

    def battery_mv(self):
        return int(_sensor_value("battery_mv", 4200))

    def temp_c(self):
        return float(_sensor_value("temp_c", 24.0))

    def light(self):
        return int(_sensor_value("light", 0))

    def imu(self):
        """6-axis IMU reading: (ax, ay, az) mG + (gx, gy, gz) milli-deg/s."""
        return {
            "accel": (int(_sensor_value("accel_x", 0)), int(_sensor_value("accel_y", 0)),
                      int(_sensor_value("accel_z", 1000))),
            "gyro": (int(_sensor_value("gyro_x", 0)), int(_sensor_value("gyro_y", 0)),
                     int(_sensor_value("gyro_z", 0))),
        }

    def camera(self):
        """Mock OV2640 camera state."""
        return dict(_sensor_value("camera", {}))


# ── bluetooth / espnow stubs (IMPROV BLE + ESP-NOW pairing) ──────────
_FLAG_READ = 0x0002
_FLAG_WRITE = 0x0008
_FLAG_NOTIFY = 0x0010
_FLAG_INDICATE = 0x0020
_FLAG_WRITE_NO_RESPONSE = 0x0004

_last_ble = None
_last_espnow = None


class _UUID:
    def __init__(self, v):
        self.value = v

    def __repr__(self):
        return str(self.value)

    def __hash__(self):
        return hash(self.value)

    def __eq__(self, other):
        return isinstance(other, _UUID) and self.value == other.value


class _BLE:
    """Host stub of ubluetooth.BLE — enough for improv_ble.ImprovBLE to run."""

    _IRQ_CENTRAL_CONNECT = 1
    _IRQ_CENTRAL_DISCONNECT = 2
    _IRQ_GATTS_WRITE = 3
    _IRQ_GATTS_READ = 4

    def __init__(self):
        global _last_ble
        self._active = False
        self._gap_name = ""
        self._adv = None
        self._values = {}
        self._char_uuid = {}
        self._irq = None
        self._n = 1
        _last_ble = self

    def active(self, v=None):
        if v is None:
            return self._active
        self._active = bool(v)
        return self._active

    def config(self, *args, **kw):
        if kw:
            for k, v in kw.items():
                setattr(self, "_" + k, v)
            return None
        if args:
            return getattr(self, "_" + args[0], None)
        return None

    def gap_advertise(self, interval_us=None, adv_data=None, **kw):
        self._adv = adv_data
        return None

    def gatts_register_services(self, services):
        handles = []
        for svc in services:
            for char in svc[1]:
                h = self._n
                self._n += 1
                self._values[h] = b""
                if hasattr(char[0], "value"):
                    self._char_uuid[h] = str(char[0].value)
                handles.append(h)
        return (tuple(handles),)

    def gatts_write(self, handle, data):
        self._values[handle] = bytes(data)
        return len(data)

    def gatts_read(self, handle):
        return self._values.get(handle, b"")

    def gatts_notify(self, conn, handle, data):
        self._values[handle] = bytes(data)
        return True

    def gatts_indicate(self, conn, handle, data):
        return self.gatts_notify(conn, handle, data)

    def gatts_set_buffer(self, *a, **k):
        return None

    def irq(self, handler):
        self._irq = handler

    def _handle_with_suffix(self, suffix):
        for h, u in self._char_uuid.items():
            if u.endswith(suffix):
                return h
        return None

    def inject_rpc(self, data):
        """Simulate a BLE central writing to the RPC command characteristic.

        Writes the value, then fires the GATTS_WRITE IRQ (conn=1) so the app's
        handler parses it exactly as it would on-device.
        """
        h = self._handle_with_suffix("003")
        if h is None:
            return False
        self._values[h] = bytes(data)
        if self._irq:
            self._irq(3, (1, h))
        return True


class _BluetoothModule:
    FLAG_READ = _FLAG_READ
    FLAG_WRITE = _FLAG_WRITE
    FLAG_NOTIFY = _FLAG_NOTIFY
    FLAG_INDICATE = _FLAG_INDICATE
    FLAG_WRITE_NO_RESPONSE = _FLAG_WRITE_NO_RESPONSE

    def UUID(self, v):
        return _UUID(v)

    def BLE(self):
        return _BLE()


class _ESPNow:
    """Host stub of the espnow module — enough for espnow_pair to run."""

    def __init__(self):
        global _last_espnow
        self._active = False
        self._peers = set()
        self._inbox = []
        self._pmk = b""
        self._irq = None
        _last_espnow = self

    def active(self, v=None):
        if v is None:
            return self._active
        self._active = bool(v)
        return self._active

    def add_peer(self, mac):
        self._peers.add(bytes(mac))
        return None

    def del_peer(self, mac):
        self._peers.discard(bytes(mac))
        return None

    def peer_count(self):
        return (len(self._peers), len(self._peers))

    def get_peers(self):
        return tuple(self._peers)

    def get_peer(self, mac):
        return bytes(mac)

    def mod_peer(self, mac, *a, **k):
        return None

    def set_pmk(self, pmk):
        self._pmk = bytes(pmk)
        return None

    def config(self, *a, **k):
        return None

    def stats(self):
        return (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

    def send(self, mac, msg, sync=True):
        return True

    def any(self):
        return len(self._inbox)

    def recv(self, timeout=None):
        return self._inbox.pop(0) if self._inbox else None

    def recvinto(self, buf, timeout=None):
        if not self._inbox:
            return 0
        _mac, msg = self._inbox.pop(0)
        n = min(len(buf), len(msg))
        buf[:n] = msg[:n]
        return n

    def irq(self, handler):
        self._irq = handler

    def irecv(self):
        while self._inbox:
            yield self._inbox.pop(0)

    def inject(self, mac, msg):
        self._inbox.append((bytes(mac), bytes(msg)))
        if self._irq:
            self._irq()
        return True


class _EspNowModule:
    def ESPNow(self):
        return _ESPNow()


def inject_ble_rpc(data):
    """Inject an IMPROV RPC command into the most recently created BLE stub."""
    if _last_ble is not None:
        return _last_ble.inject_rpc(data)
    return False


def inject_espnow(mac, msg):
    """Inject an ESP-NOW frame into the most recently created ESPNow stub."""
    if _last_espnow is not None:
        return _last_espnow.inject(mac, msg)
    return False


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
        "sensors": _SensorsModule(),
        "framebuf": FrameBuffer,
        "bluetooth": _BluetoothModule(),
        "espnow": _EspNowModule(),
    }
    for name, mod in shims.items():
        sys.modules[name] = mod

    # os: stdlib os, patched with the MicroPython surface apps rely on, plus
    # /sd path mapping so the virtual SD card behaves like a real VFS mount.
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

    _orig_listdir = os.listdir
    _orig_stat = os.stat
    _orig_remove = os.remove
    _orig_rmdir = os.rmdir
    _orig_mkdir = os.mkdir
    _orig_rename = os.rename

    def listdir(path="."):
        return _orig_listdir(_map_path(path))

    def stat(path, *a, **k):
        return _orig_stat(_map_path(path), *a, **k)

    def remove(path):
        return _orig_remove(_map_path(path))

    def rmdir(path):
        return _orig_rmdir(_map_path(path))

    def mkdir(path, *a, **k):
        return _orig_mkdir(_map_path(path), *a, **k)

    def rename(a, b):
        return _orig_rename(_map_path(a), _map_path(b))

    def ilistdir(path="."):
        # MicroPython-style (name, type, inode, size) iterator.
        p = _map_path(path)
        for name in _orig_listdir(p):
            st = _orig_stat(os.path.join(p, name))
            typ = 0x4000 if (st.st_mode & 0xF000) == 0x4000 else 0x8000
            yield name, typ, st.st_ino, st.st_size

    def statvfs(path="/"):
        return (4096, 4096, 65536, 65536, 65536, 65536, 0, 0, 0, 4096)

    os.listdir = listdir
    os.stat = stat
    os.remove = remove
    os.rmdir = rmdir
    os.mkdir = mkdir
    os.rename = rename
    os.ilistdir = ilistdir
    os.statvfs = statvfs

    # Map open('/sd/...') onto the virtual SD card too.
    _orig_open = builtins.open

    def open(file, *a, **k):
        return _orig_open(_map_path(file), *a, **k)

    builtins.open = open
    _SD_OPEN = _orig_open  # keep the real open for internal host-file use

    return display
