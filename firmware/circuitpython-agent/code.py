# Nirvana Fleet Agent v5 — CPlay Express + TFT Gizmo
# Full ST7789 display + audio speaker + all sensors + 6 modes
# Flash: drop CP 10.2.1 UF2 to CPLAYBOOT, then copy code.py + lib/ to CIRCUITPY

import board
import busio
import displayio
import terminalio
import time
import math
import json
import gc
import array
import analogio
import digitalio
import touchio
import audioio
import audiocore
from fourwire import FourWire
from adafruit_st7789 import ST7789
from adafruit_display_text import label
import neopixel
import adafruit_lis3dh
import adafruit_thermistor

# ═══════════════════════════════════════════
# NIRVANA FLEET BRANDING
# ═══════════════════════════════════════════
DEVICE_ID = "npu-cpx-001"
FLEET_NAME = "NIRVANA FLEET"
VERSION = "v5.0-gizmo"
NIRVANA_PURPLE = 0x9933FF
NIRVANA_GREEN = 0x00FF88

# ═══════════════════════════════════════════
# HARDWARE INIT
# ═══════════════════════════════════════════

# --- TFT Gizmo Display (ST7789 240x240 IPS) ---
displayio.release_displays()
spi = busio.SPI(board.SCL, MOSI=board.SDA)  # Gizmo: SPI on A4(SCK) A5(MOSI)
tft_cs = board.RX      # A7
tft_dc = board.TX      # A6
tft_bl = board.A3      # Backlight PWM
display_bus = FourWire(spi, command=tft_dc, chip_select=tft_cs)
display = ST7789(
    display_bus,
    width=240, height=240,
    rowstart=80,
    backlight_pin=tft_bl,
    rotation=180
)

# --- NeoPixels ---
pixels = neopixel.NeoPixel(board.NEOPIXEL, 10, brightness=0.3, auto_write=False)

# --- Sensors ---
light_sensor = analogio.AnalogIn(board.LIGHT)
mic_sensor = analogio.AnalogIn(board.MIC)
thermistor = adafruit_thermistor.Thermistor(
    board.TEMPERATURE, 10000, 10000, 25, 3950
)
i2c = board.I2C()
lis3dh = adafruit_lis3dh.LIS3DH_I2C(i2c, address=0x18)

# --- Buttons & Switch ---
btn_a = digitalio.DigitalInOut(board.BUTTON_A)
btn_a.switch_to_input(pull=digitalio.Pull.DOWN)
btn_b = digitalio.DigitalInOut(board.BUTTON_B)
btn_b.switch_to_input(pull=digitalio.Pull.DOWN)
slide = digitalio.DigitalInOut(board.SLIDE_SWITCH)
slide.switch_to_input(pull=digitalio.Pull.UP)

# --- Touch Pads ---
touch_names = ["A1", "A2", "A3", "A4", "A5", "A6", "A7"]
touch_pins = [board.A1, board.A2, board.A3, board.A4, board.A5, board.A6, board.A7]
touches = []
for p in touch_pins:
    try:
        touches.append(touchio.TouchIn(p))
    except:
        touches.append(None)

# --- Audio (Gizmo Class D amp on A0 DAC) ---
audio = audioio.AudioOut(board.A0)
speaker_on = True

# ═══════════════════════════════════════════
# DISPLAY HELPERS
# ═══════════════════════════════════════════
root = displayio.Group()
display.root_group = root

def cls():
    """Clear screen"""
    while len(root) > 0:
        root.pop()

def header(title):
    """Draw Nirvana header bar"""
    bar = displayio.Bitmap(240, 22, 1)
    pal = displayio.Palette(1)
    pal[0] = NIRVANA_PURPLE
    root.append(displayio.TileGrid(bar, pixel_shader=pal, y=0))
    root.append(label.Label(
        terminalio.FONT, text=f"  {FLEET_NAME} // {title}",
        color=0xFFFFFF, scale=1, x=4, y=5
    ))

def text(msg, x, y, color=0xFFFFFF, scale=1):
    """Draw text label"""
    t = label.Label(terminalio.FONT, text=msg, color=color, scale=scale)
    t.x = x
    t.y = y
    root.append(t)
    return t

def rect(x, y, w, h, color):
    """Draw filled rectangle"""
    bmp = displayio.Bitmap(w, h, 1)
    pal = displayio.Palette(1)
    pal[0] = color
    root.append(displayio.TileGrid(bmp, pixel_shader=pal, x=x, y=y))

def center_text(msg, y, color=0xFFFFFF, scale=2):
    """Draw centered text"""
    t = label.Label(terminalio.FONT, text=msg, color=color, scale=scale)
    tw = t.bounding_box[2] * scale
    t.x = (240 - tw) // 2
    t.y = y
    root.append(t)

def footer():
    """Draw mode footer"""
    text("A:mode  B:speaker", 5, 222, 0x444444, 1)

# ═══════════════════════════════════════════
# AUDIO
# ═══════════════════════════════════════════
def beep(freq=880, dur=0.05):
    if not speaker_on:
        return
    try:
        n = max(int(8000 / freq), 2)
        samples = array.array('H', [0] * n)
        for i in range(n):
            samples[i] = int(32768 + 28000 * math.sin(2 * math.pi * i / n))
        wave = audiocore.RawSample(samples, sample_rate=8000)
        audio.play(wave, loop=True)
        time.sleep(dur)
        audio.stop()
    except:
        pass

def play_note(freq, dur):
    if not speaker_on:
        return
    try:
        length = max(int(8000 // freq), 2)
        samples = array.array('H', [0] * length)
        for i in range(length):
            samples[i] = int(32768 + 28000 * math.sin(2 * math.pi * i / length))
        wave = audiocore.RawSample(samples, sample_rate=8000)
        audio.play(wave, loop=True)
        time.sleep(dur)
        audio.stop()
    except:
        pass

# ═══════════════════════════════════════════
# HSV to RGB
# ═══════════════════════════════════════════
def hsv2rgb(h, s=1.0, v=1.0):
    h = h % 360
    c = v * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = v - c
    if h < 60:   r, g, b = c, x, 0
    elif h < 120: r, g, b = x, c, 0
    elif h < 180: r, g, b = 0, c, x
    elif h < 240: r, g, b = 0, x, c
    elif h < 300: r, g, b = x, 0, c
    else:         r, g, b = c, 0, x
    return (int((r + m) * 255), int((g + m) * 255), int((b + m) * 255))

# ═══════════════════════════════════════════
# MODE RENDERERS
# ═══════════════════════════════════════════
def draw_status():
    cls()
    header("STATUS")
    text(f"Device:  {DEVICE_ID}", 8, 35, NIRVANA_GREEN)
    text(f"Version: {VERSION}", 8, 55, NIRVANA_GREEN)
    text("Board:   SAMD21G18A", 8, 80, 0x888888)
    text("Display: TFT Gizmo 240x240", 8, 98, 0x888888)
    text("Flash:   2 MB SPI", 8, 116, 0x888888)
    text("Speaker: Gizmo Amp (A0)", 8, 134, 0x888888)
    text("Sensors: Temp/Light/Mic/Accel", 8, 152, 0x888888)
    text(f"Free RAM: {gc.mem_free()} bytes", 8, 175, 0x666666)
    footer()

def draw_sensors():
    cls()
    header("SENSORS")
    t = thermistor.temperature
    l = light_sensor.value
    m = mic_sensor.value
    ax, ay, az = lis3dh.acceleration

    color = 0xFF4444 if t > 30 else (0x44AAFF if t < 20 else NIRVANA_GREEN)
    center_text(f"{t:.1f} C", 40, color, 3)

    light_pct = min(l // 512, 10)
    mic_pct = min(m // 100, 10)
    text(f"Light: {'#' * light_pct}{'.' * (10 - light_pct)}", 10, 80, 0xFFCC00)
    text(f"Mic:   {'#' * mic_pct}{'.' * (10 - mic_pct)}", 10, 100, 0x44CCFF)

    text(f"Accel X:{ax:6.1f}", 10, 130, 0xAAFF44)
    text(f"      Y:{ay:6.1f}", 10, 148, 0xAAFF44)
    text(f"      Z:{az:6.1f}", 10, 166, 0xAAFF44)

    touched = []
    for i, tch in enumerate(touches):
        if tch and tch.value:
            touched.append(touch_names[i])
    if touched:
        text(f"Touch: {', '.join(touched)}", 10, 192, 0xFF88FF)
    else:
        text("Touch: none", 10, 192, 0x444444)
    footer()

def draw_rainbow():
    global _rainbow_hue
    cls()
    header("RAINBOW")
    _rainbow_hue = (_rainbow_hue + 3) % 360
    h = _rainbow_hue
    for i in range(10):
        pixels[i] = hsv2rgb(h + i * 36)
    pixels.show()
    center_text("NEO RAINBOW", 100, hsv2rgb(h))
    footer()

def draw_vu():
    cls()
    header("VU METER")
    m = mic_sensor.value >> 6
    level = min(m // 10, 100)

    pixels.fill(0)
    lit = min(m // 100, 10)
    for i in range(lit):
        if i < 3:   pixels[i] = (0, 255, 0)
        elif i < 7: pixels[i] = (255, 255, 0)
        else:       pixels[i] = (255, 0, 0)
    pixels.show()

    center_text(f"VOL: {m}", 40, NIRVANA_GREEN, 3)

    for row in range(10):
        bar_w = int(level * 1.5)
        if bar_w > 0:
            y = 80 + row * 12
            if row < 4:   c = 0x00FF00
            elif row < 7: c = 0xFFFF00
            else:         c = 0xFF0000
            rect(20, y, bar_w, 10, c)
    footer()

def draw_touch():
    cls()
    header("TOUCH PADS")
    active = False
    for i in range(7):
        tch = touches[i]
        if tch is None:
            continue
        raw = tch.raw_value
        on = tch.value
        y = 30 + i * 22
        c = NIRVANA_GREEN if on else 0x333333
        rect(15, y, 200, 18, c)
        status = "TOUCHED!" if on else ""
        text(f"{touch_names[i]}: {raw:5d} {status}", 20, y + 2,
             0xFFFFFF if on else 0x888888)
        if on:
            active = True
            pixels[i % 10] = (255, 0, 255)
    if not active:
        pixels.fill(0)
    pixels.show()
    footer()

def draw_eye():
    cls()
    header("NIRVANA EYE")
    t = time.monotonic()

    # Sclera
    rect(30, 30, 180, 160, 0xFFFFFF)

    # Iris
    iris_r = 55
    iris_x = int(120 + 20 * math.sin(t * 0.7))
    iris_y = int(110 + 15 * math.cos(t * 0.5))
    rect(iris_x - iris_r, iris_y - iris_r, iris_r * 2, iris_r * 2, NIRVANA_PURPLE)

    # Pupil
    pupil_r = 20
    px = int(iris_x + 8 * math.sin(t * 1.3))
    py = int(iris_y + 5 * math.cos(t * 0.9))
    rect(px - pupil_r, py - pupil_r, pupil_r * 2, pupil_r * 2, 0x000000)

    # Highlight
    rect(px + 5, py - 15, 8, 8, 0xFFFFFF)

    center_text("NIRVANA", 210, NIRVANA_GREEN, 1)
    footer()

# ═══════════════════════════════════════════
# SERIAL COMMAND HANDLER
# ═══════════════════════════════════════════
def handle_serial():
    try:
        import supervisor
        if supervisor.runtime.serial_bytes_available:
            line = input()
            if not line:
                return
            try:
                data = json.loads(line)
            except:
                return
            cmd = data.get("cmd", "")
            global current_mode, speaker_on
            if cmd == "mode":
                current_mode = int(data.get("value", 0)) % len(MODES)
            elif cmd == "pixels":
                c = data.get("color", [0, 0, 0])
                pixels.fill(tuple(c))
                pixels.show()
            elif cmd == "speaker":
                speaker_on = bool(data.get("enable", True))
            elif cmd == "tone":
                play_note(data.get("freq", 440), data.get("dur", 0.2))
            elif cmd == "display_text":
                cls()
                text(data.get("text", "NIRVANA"), 10, 50, NIRVANA_PURPLE, 2)
            elif cmd == "status":
                print(json.dumps({
                    "device": DEVICE_ID,
                    "fleet": FLEET_NAME,
                    "version": VERSION,
                    "mode": MODES[current_mode],
                    "temp": thermistor.temperature,
                    "light": light_sensor.value,
                    "free_ram": gc.mem_free(),
                    "speaker": speaker_on
                }))
            elif cmd == "reboot":
                import microcontroller
                microcontroller.reset()
    except:
        pass

# ═══════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════
MODES = ["STATUS", "SENSORS", "RAINBOW", "VU", "TOUCH", "EYE"]
current_mode = 0
_rainbow_hue = 0

last_a = False
last_b = False

print(f"\n>>> {FLEET_NAME} AGENT {VERSION} <<<")
print(f"    Device: {DEVICE_ID}")
print(f"    Modes: {', '.join(MODES)}")
print(f"    Buttons: A=next mode, B=toggle speaker")
print(f"    Ready.\n")

beep(880, 0.08)
beep(1320, 0.08)

while True:
    a = btn_a.value
    b = btn_b.value
    sw = slide.value

    if a and not last_a:
        current_mode = (current_mode + 1) % len(MODES)
        beep(880, 0.03)
        print(f"MODE: {MODES[current_mode]}")

    if b and not last_b:
        speaker_on = not speaker_on
        if speaker_on:
            beep(660, 0.05)
        print(f"SPEAKER: {'ON' if speaker_on else 'OFF'}")

    last_a = a
    last_b = b

    pixels.brightness = 0.5 if sw else 0.15

    if current_mode == 0:
        draw_status()
        time.sleep(0.5)
    elif current_mode == 1:
        draw_sensors()
        time.sleep(0.3)
    elif current_mode == 2:
        draw_rainbow()
        time.sleep(0.05)
    elif current_mode == 3:
        draw_vu()
        time.sleep(0.08)
    elif current_mode == 4:
        draw_touch()
        time.sleep(0.1)
    elif current_mode == 5:
        draw_eye()
        time.sleep(0.08)

    handle_serial()
    gc.collect()
