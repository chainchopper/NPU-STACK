# Flash Guide: Nirvana Fleet Agent v5 (CPX + TFT Gizmo)

## What You Need
- `adafruit-circuitpython-cpx-10.2.1.uf2` — CircuitPython 10.2.1 for CPlay Express
- `code.py` — v5 agent code
- `lib/` folder with:
  - `adafruit_st7789.mpy` — ST7789 display driver
  - `adafruit_display_text/` — text labels on screen
  - `adafruit_bitmap_font/` — fonts
  - `adafruit_bus_device/` — SPI bus helpers

## Flash Steps

### Step 1: Install CircuitPython 10.2.1
1. Double-tap the CPlay Reset button (center of board)
2. Drive `CPLAYBOOT` appears (4MB)
3. Drag `adafruit-circuitpython-cpx-10.2.1.uf2` onto `CPLAYBOOT`
4. Board reboots → drive becomes `CIRCUITPY` (2MB)

### Step 2: Install Nirvana Agent
1. Copy `code.py` to `CIRCUITPY`
2. Copy `lib/` folder to `CIRCUITPY` (merge with existing)
3. Board auto-reboots → agent starts

### Step 3: Verify
- Screen shows "NIRVANA FLEET // STATUS" on TFT Gizmo
- Button A cycles through 6 modes
- Button B toggles speaker
- Slide switch controls brightness

## Modes
| # | Mode | Display | NeoPixels | Speaker |
|---|------|---------|-----------|---------|
| 0 | STATUS | Device info, free RAM | Off | Beep on switch |
| 1 | SENSORS | Temp, light, mic, accel, touch | Off | Off |
| 2 | RAINBOW | Color label | Rainbow cycle | Off |
| 3 | VU | Volume bars | VU meter green→red | Off |
| 4 | TOUCH | 7 pad states | Pink on touch | Off |
| 5 | EYE | Animated Nirvana eye | Off | Off |

## Serial Commands (USB REPL)
Send JSON over serial at 115200 baud:

```json
{"cmd": "mode", "value": 2}
{"cmd": "pixels", "color": [0, 255, 0]}
{"cmd": "speaker", "enable": false}
{"cmd": "tone", "freq": 440, "dur": 0.5}
{"cmd": "display_text", "text": "HELLO"}
{"cmd": "status"}
{"cmd": "reboot"}
```

## Hardware Notes
- **TFT Gizmo** bolts onto CPlay Express via M3 standoffs
- Display: ST7789 240x240 IPS, SPI on A4(SCK)/A5(MOSI), CS=A7, DC=A6, BL=A3
- Speaker: Class D amp on A0 DAC → use `audioio.AudioOut` NOT `pwmio`
- JST Ports: A1 (left), A2 (right) — NeoPixel strips or servos
- CPlay Express: 2MB SPI flash, SAMD21G18A @ 48MHz, 32KB RAM

## Libraries Source
Libraries extracted from Adafruit CircuitPython Bundle 10.x (2026-07-24):
https://github.com/adafruit/Adafruit_CircuitPython_Bundle/releases

## Troubleshooting
- **No display**: Check TFT Gizmo is firmly attached. Verify `code.py` and `lib/` are on `CIRCUITPY`.
- **Safe mode**: If board enters safe mode, press reset button once. Delete `code.py` and retry.
- **Memory error**: SAMD21 has limited RAM. Remove unused .mpy files from `lib/`.
- **Back to CPX Eye**: Drag `CPX_Eye_Human.UF2` to `CPLAYBOOT` to restore animated eye.
