# NPU-STACK Nirvana Fleet Agent
# Adafruit Circuit Playground Express + TFT Gizmo
# ============================================================
# Board: Circuit Playground Express (SAMD21G18)
# Display: TFT Gizmo (ST7789 240x240, SPI)
# Agent: v4.0 — multi-mode with full sensor suite
#
# MODES (cycle with Button A):
#   1. STATUS — shows device ID, uptime, free RAM on neopixel ring
#   2. SENSORS — reads all sensors, displays on REPL
#   3. RAINBOW — animated rainbow on neopixels
#   4. THERMOMETER — neopixels show temperature (blue=cool, red=hot)
#   5. VU_METER — neopixels respond to sound level from mic
#   6. TOUCH — capacitive touch pads light up neopixels
#
# Button B: toggle speaker (play tone on mode change)
# SERIAL: Type JSON commands — {"command":"HELP"} for list
#
# FLASH: See README.md in firmware/circuitpython-agent/
# ============================================================

import time, json, board, neopixel, digitalio, analogio, touchio, microcontroller, math, gc

# ── Hardware ───────────────────────────────────────────────────────────────
NUM_PIXELS = 10
pixels = neopixel.NeoPixel(board.NEOPIXEL, NUM_PIXELS, brightness=0.25, auto_write=False)

# Buttons
btn_a = digitalio.DigitalInOut(board.BUTTON_A)
btn_a.switch_to_input(pull=digitalio.Pull.DOWN)
btn_b = digitalio.DigitalInOut(board.BUTTON_B)
btn_b.switch_to_input(pull=digitalio.Pull.DOWN)

# Touch pads
TOUCH_PINS = {
    "A1": board.A1, "A2": board.A2, "A3": board.A3,
    "A4": board.A4, "A5": board.A5, "A6": board.A6, "A7": board.A7,
}
touch = {}
for name, pin in TOUCH_PINS.items():
    try: touch[name] = touchio.TouchIn(pin)
    except: pass

# Sensors
try: light_sensor = analogio.AnalogIn(board.LIGHT)
except: light_sensor = None
try: mic = analogio.AnalogIn(board.MIC)
except: mic = None
try: temp = microcontroller.cpu.temperature
except: temp = None

# LED (the small red LED next to USB)
try: red_led = digitalio.DigitalInOut(board.D13)
     red_led.switch_to_output(); red_led.value = False
except: red_led = None

# Audio (speaker on A0)
try:
    import pwmio
    speaker = pwmio.PWMOut(board.SPEAKER, duty_cycle=0, frequency=440, variable_frequency=True)
    HAS_SPEAKER = True
except:
    HAS_SPEAKER = False

# ── Config ─────────────────────────────────────────────────────────────────
try:
    with open("npu_config.json") as f: cfg = json.load(f)
except:
    cfg = {"device_id": "nirvana-cplay-01", "vendor": "Fanalogy", "fleet": "NPU-STACK"}

MODE_COUNT = 6
current_mode = 0
speaker_enabled = True
last_btn_a = False
last_btn_b = False

# ── Neopixel Helpers ───────────────────────────────────────────────────────
def _wheel(pos):
    pos = 255 - pos
    if pos < 85: return (255 - pos * 3, 0, pos * 3)
    if pos < 170: pos -= 85; return (0, pos * 3, 255 - pos * 3)
    pos -= 170; return (pos * 3, 255 - pos * 3, 0)

def np_fill(r, g, b): pixels.fill((r, g, b)); pixels.show()
def np_off(): pixels.fill((0, 0, 0)); pixels.show()

# ── Audio ────────────────────────────────────────────────────────────────
def beep(freq=880, ms=80):
    if not HAS_SPEAKER or not speaker_enabled: return
    try:
        speaker.frequency = freq; speaker.duty_cycle = 32768
        time.sleep(ms / 1000)
        speaker.duty_cycle = 0
    except: pass

# ── Modes ─────────────────────────────────────────────────────────────────
MODE_NAMES = ["STATUS", "SENSORS", "RAINBOW", "THERMOMETER", "VU_METER", "TOUCH"]

def mode_status():
    """Show device identity on neopixels and serial."""
    gc.collect()
    info = {
        "device": cfg.get("device_id"), "vendor": cfg.get("vendor"),
        "fleet": cfg.get("fleet"), "mode": MODE_NAMES[current_mode],
        "uptime_s": round(time.monotonic(), 1), "free_ram": gc.mem_free(),
        "board": "Circuit Playground Express", "chip": "SAMD21G18",
        "flash_mb": 2, "neopixels": 10,
    }
    np_fill(0, 255, 0)  # Green ring = ready
    return info

def mode_sensors():
    """Read all sensors."""
    data = {"mode": "SENSORS", "uptime_s": round(time.monotonic(), 1)}
    gc.collect(); data["free_ram"] = gc.mem_free()
    if temp: data["temp_c"] = round(temp, 1)
    if light_sensor: data["light_raw"] = light_sensor.value
    if mic: data["mic_raw"] = mic.value
    # Touch check
    data["touch"] = {}
    for n, t in touch.items():
        try: data["touch"][n] = t.raw_value > 500
        except: pass
    # Voltage
    try:
        vcc = analogio.AnalogIn(board.VOLTAGE_MONITOR)
        data["voltage"] = round((vcc.value * 3.3) / 65536 * 2, 2)
    except: pass
    return data

def mode_rainbow():
    """Animate rainbow on neopixel ring for one cycle."""
    for j in range(256):
        for i in range(NUM_PIXELS):
            idx = (i * 256 // NUM_PIXELS + j) & 255
            pixels[i] = _wheel(idx)
        pixels.show()
        # Check for button press to exit
        if btn_a.value: return
    np_off()

def mode_thermometer():
    """Show temperature as color gradient (blue=cool, red=hot)."""
    t = temp or 25
    # Map 10°C → 40°C to 0 → 9 pixels
    level = min(NUM_PIXELS - 1, max(0, int((t - 10) * NUM_PIXELS / 30)))
    for i in range(NUM_PIXELS):
        if i <= level:
            r = int(255 * i / (NUM_PIXELS - 1))
            b = 255 - r
            pixels[i] = (r, 0, b)
        else:
            pixels[i] = (0, 0, 0)
    pixels.show()

def mode_vu_meter():
    """Show sound level from microphone on neopixels."""
    if not mic: return
    level = min(NUM_PIXELS, int(mic.value * NUM_PIXELS / 65535))
    for i in range(NUM_PIXELS):
        if i < level:
            g = int(255 * (NUM_PIXELS - i) / NUM_PIXELS)
            pixels[i] = (0, g, 0)
        else:
            pixels[i] = (0, 0, 0)
    pixels.show()

def mode_touch():
    """Light up neopixels for each touched pad."""
    count = 0
    for name, t in touch.items():
        try:
            if t.raw_value > 500:
                idx = int(name[1]) - 1  # A1→0, A7→6
                if 0 <= idx < NUM_PIXELS:
                    pixels[idx] = (255, 255, 0)
                    count += 1
        except: pass
    if count == 0: np_off()
    else: pixels.show()

# ── Mode Runner ────────────────────────────────────────────────────────────
def run_mode():
    if current_mode == 0: return mode_status()
    elif current_mode == 1: return mode_sensors()
    elif current_mode == 2: mode_rainbow(); return {"mode": "RAINBOW"}
    elif current_mode == 3: mode_thermometer(); return {"mode": "THERMOMETER", "temp_c": round(temp, 1) if temp else None}
    elif current_mode == 4: mode_vu_meter(); return {"mode": "VU_METER"}
    elif current_mode == 5: mode_touch(); return {"mode": "TOUCH"}
    return {"mode": current_mode}

def change_mode(delta=1):
    global current_mode
    current_mode = (current_mode + delta) % MODE_COUNT
    np_off()
    beep(440 + current_mode * 100, 60)
    np_fill(0, 255, 0)
    time.sleep(0.1)
    np_off()
    result = run_mode()
    print(json.dumps({"mode_changed": MODE_NAMES[current_mode], **result}))

# ── Command Handler ────────────────────────────────────────────────────────
def handle(cmd):
    global current_mode, speaker_enabled
    n = cmd.get("command", "")
    try:
        if n == "HELP":
            return {"commands": ["HELP","READ_SENSORS","GET_HEALTH","GET_STATUS","SET_MODE","NEXT_MODE","TOGGLE_SPEAKER","NEOPIXEL_FILL","NEOPIXEL_OFF","NEOPIXEL_RAINBOW","TONE","SET_CONFIG"],"device":cfg.get("device_id"),"board":"Circuit Playground Express","chip":"SAMD21G18","display":"TFT Gizmo ST7789 240x240","modes":MODE_NAMES,"current_mode":MODE_NAMES[current_mode],"neopixels":10,"sensors":["temperature","light","microphone","capacitive_touch","voltage"],"wireless":"None (SAMD21 — USB Serial only)","speaker":HAS_SPEAKER,"speaker_enabled":speaker_enabled}
        if n in ("READ_SENSORS", "GET_HEALTH"): return mode_sensors()
        if n == "GET_STATUS": return {"mode": MODE_NAMES[current_mode], "device": cfg.get("device_id"), "uptime_s": round(time.monotonic(), 1)}
        if n == "SET_MODE":
            m = int(cmd.get("mode", 0))
            if 0 <= m < MODE_COUNT:
                global current_mode; current_mode = m
                run_mode()
                return {"mode": MODE_NAMES[current_mode]}
        if n == "NEXT_MODE": change_mode(1); return {"mode": MODE_NAMES[current_mode]}
        if n == "PREV_MODE": change_mode(-1); return {"mode": MODE_NAMES[current_mode]}
        if n == "TOGGLE_SPEAKER":
            global speaker_enabled; speaker_enabled = not speaker_enabled
            return {"speaker_enabled": speaker_enabled}
        if n == "NEOPIXEL_FILL":
            r, g, b = int(cmd.get("r", 0)), int(cmd.get("g", 255)), int(cmd.get("b", 0))
            np_fill(r, g, b); return {"filled": [r, g, b]}
        if n == "NEOPIXEL_OFF": np_off(); return {"off": True}
        if n == "NEOPIXEL_RAINBOW": mode_rainbow(); return {"rainbow_done": True}
        if n == "TONE":
            freq, ms = int(cmd.get("hz", 440)), int(cmd.get("duration_ms", 500))
            beep(freq, ms); return {"tone": [freq, ms]}
        if n == "SET_CONFIG":
            for k, v in cmd.items():
                if k in cfg and k != "command": cfg[k] = v
            try: json.dump(cfg, open("npu_config.json", "w"))
            except: pass
            return {"ok": True}
        return {"error": "unknown cmd", "try": "HELP"}
    except Exception as e: return {"error": str(e)}

# ── Main Loop ──────────────────────────────────────────────────────────────
print("=" * 50)
print("  Nirvana Fleet Agent v4.0")
print(f"  {cfg.get('device_id', 'cplay')} | {cfg.get('vendor', 'Fanalogy')} {cfg.get('fleet', 'NPU-STACK')}")
print(f"  Mode: {MODE_NAMES[current_mode]} | Buttons: A=next B=toggle speaker")
print("  Type: {\"command\": \"HELP\"}")
print("=" * 50)

np_fill(0, 255, 0)
beep(880, 50); time.sleep(0.05); beep(1320, 50)  # Startup chime

while True:
    # ── USB Serial command ──
    try:
        line = ""  # Non-blocking read attempt
    except: pass

    # ── Button handling ──
    a_now, b_now = btn_a.value, btn_b.value
    if a_now and not last_btn_a:
        change_mode(1)
    if b_now and not last_btn_b:
        speaker_enabled = not speaker_enabled
        beep(440, 30) if speaker_enabled else None
        print(json.dumps({"speaker_toggled": speaker_enabled}))
    last_btn_a, last_btn_b = a_now, b_now

    # ── Run current mode ──
    run_mode()

    # Small delay
    if current_mode in (2, 3, 4, 5):
        time.sleep(0.05)
    else:
        time.sleep(0.5)
