# Nirvana Fleet Agent v5.2 — CPlay Express
# 5 modes: RAINBOW / LIGHT / TOUCH / SENSORS / PULSE
# Button A: next mode | Button B: toggle speaker | Slide: brightness
import board, time, math, gc, neopixel, analogio, digitalio, touchio

DEVICE = "npu-cpx-001"
FLEET = "NIRVANA FLEET"
VER = "v5.2"
NP = (153, 51, 255)
NG = (0, 255, 136)

pixels = neopixel.NeoPixel(board.NEOPIXEL, 10, brightness=0.3, auto_write=False)
light = analogio.AnalogIn(board.LIGHT)

# Frozen modules (included in CP 10.2.1 for CPlay)
try:
    import adafruit_thermistor
    therm = adafruit_thermistor.Thermistor(board.TEMPERATURE, 10000, 10000, 25, 3950)
    HT = True
except:
    therm = None
    HT = False

try:
    import adafruit_lis3dh
    i2c = board.I2C()
    accel = adafruit_lis3dh.LIS3DH_I2C(i2c, address=0x18)
    HA = True
except:
    accel = None
    HA = False

# Buttons & switch
btn_a = digitalio.DigitalInOut(board.BUTTON_A)
btn_a.switch_to_input(pull=digitalio.Pull.DOWN)
btn_b = digitalio.DigitalInOut(board.BUTTON_B)
btn_b.switch_to_input(pull=digitalio.Pull.DOWN)
slide = digitalio.DigitalInOut(board.SLIDE_SWITCH)
slide.switch_to_input(pull=digitalio.Pull.UP)

# 7 capacitive touch pads
tpins = [board.A1, board.A2, board.A3, board.A4, board.A5, board.A6, board.A7]
touches = []
for p in tpins:
    try:
        touches.append(touchio.TouchIn(p))
    except:
        touches.append(None)

# Speaker (buzzer on A0 DAC via SPEAKER pin)
try:
    import audioio, audiocore, array
    audio = audioio.AudioOut(board.SPEAKER)
    epin = digitalio.DigitalInOut(board.SPEAKER_ENABLE)
    epin.switch_to_output(value=True)
    spk = True
    HAUD = True
except:
    spk = True
    HAUD = False


def beep(f=880, d=0.05):
    if not HAUD or not spk:
        return
    try:
        n = max(int(8000 / f), 2)
        s = array.array("H", [0] * n)
        for i in range(n):
            s[i] = int(32768 + 28000 * math.sin(6.283 * i / n))
        audio.play(audiocore.RawSample(s, sample_rate=8000), loop=True)
        time.sleep(d)
        audio.stop()
    except:
        pass


def hsv(h, s=1, v=1):
    h %= 360
    c = v * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = v - c
    if h < 60:
        r, g, b = c, x, 0
    elif h < 120:
        r, g, b = x, c, 0
    elif h < 180:
        r, g, b = 0, c, x
    elif h < 240:
        r, g, b = 0, x, c
    elif h < 300:
        r, g, b = x, 0, c
    else:
        r, g, b = c, 0, x
    return (int((r + m) * 255), int((g + m) * 255), int((b + m) * 255))


MODES = ["RAINBOW", "LIGHT", "TOUCH", "SENSORS", "PULSE"]
mode = 0
rh = 0
la = False
lb = False

print(">> %s %s | RAM:%d" % (FLEET, VER, gc.mem_free()))
print("   Modes: %s" % " ".join(MODES))
beep(880, 0.05)
beep(1320, 0.08)

while True:
    a = btn_a.value
    b = btn_b.value
    sw = slide.value

    if a and not la:
        mode = (mode + 1) % len(MODES)
        beep(880, 0.03)
        print("%s RAM:%d" % (MODES[mode], gc.mem_free()))
    if b and not lb:
        spk = not spk
        if spk:
            beep(660, 0.05)

    la = a
    lb = b
    pixels.brightness = 0.5 if sw else 0.15

    if mode == 0:  # RAINBOW
        for i in range(10):
            pixels[i] = hsv(rh + i * 36)
        rh = (rh + 2) % 360
        time.sleep(0.04)

    elif mode == 1:  # LIGHT (VU-style meter from light sensor)
        lv = light.value >> 6
        lit = min(lv // 100, 10)
        pixels.fill(0)
        for i in range(lit):
            pixels[i] = (0, 255, 0) if i < 3 else ((255, 255, 0) if i < 7 else (255, 0, 0))
        time.sleep(0.06)

    elif mode == 2:  # TOUCH
        pixels.fill(0)
        for i, t in enumerate(touches):
            if t and t.value:
                pixels[i % 10] = (255, 0, 255)
        time.sleep(0.06)

    elif mode == 3:  # SENSORS (Nirvana purple)
        pixels.fill(NP)
        time.sleep(0.3)

    elif mode == 4:  # PULSE
        t = time.monotonic()
        b2 = int(127 + 127 * math.sin(t * 3))
        pixels.fill((b2, 0, b2 >> 1))
        time.sleep(0.04)

    pixels.show()
    gc.collect()
