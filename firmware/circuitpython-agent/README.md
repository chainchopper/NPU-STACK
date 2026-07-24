# Nirvana Fleet Agent — CircuitPython

Agents for CircuitPython-compatible fleet devices.

## Boards

### Adafruit Circuit Playground Express + TFT Gizmo
- **Agent**: v5.0 (`code.py`) — full TFT display + audio + sensors
- **CP Version**: CircuitPython 10.2.1 (UF2 included)
- **Display**: ST7789 240x240 IPS (TFT Gizmo bolt-on)
- **Audio**: Class D amp on A0 DAC (`audioio.AudioOut`)
- **Flash Guide**: [FLASH_GUIDE_v5.md](FLASH_GUIDE_v5.md)

### Other Compatible Boards
- Waveshare S3 Matrix (ESP32-S3) — `s3-matrix-agent/`
- Generic ESP32-S3 — `micropython-esp32/`

## Quick Flash (CPX + TFT Gizmo)
1. Double-tap reset → CPLAYBOOT appears
2. Drag `adafruit-circuitpython-cpx-10.2.1.uf2` onto CPLAYBOOT
3. Board reboots → CIRCUITPY appears
4. Copy `code.py` + `lib/` to CIRCUITPY
5. Agent starts — 6 modes on TFT screen

## Modes (Button A cycles)
| # | Mode | Display | NeoPixels |
|---|------|---------|-----------|
| 0 | STATUS | Device info + free RAM | Off |
| 1 | SENSORS | Temp/light/mic/accel/touch | Off |
| 2 | RAINBOW | Color label | Rainbow cycle |
| 3 | VU | Volume bars | Green→Red meter |
| 4 | TOUCH | 7 pad states | Pink per touch |
| 5 | EYE | Animated eye | Off |

## Reference UF2s
- `CPX_Eye_Human.UF2` — Pre-built animated eye (Adafruit Arduino binary)
- `CPX_Eye_No_Sclera.UF2` — No-sclera variant
- `CP-9.2.4-cplay-express.uf2` — Older CP 9.2.4 (backup)
- `TFT_GIZMO_PINOUT.txt` — Full pin mapping
