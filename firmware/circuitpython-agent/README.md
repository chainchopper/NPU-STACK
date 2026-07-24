# NPU-STACK Nirvana Fleet Agent — Adafruit Circuit Playground Express

## Overview

This agent runs on the Adafruit Circuit Playground Express (SAMD21) and provides JSON-based command control over USB Serial REPL. It exposes ALL onboard sensors (temperature, light, capacitive touch, voltage), the 10-neopixel ring, and the speaker.

## Status Indicators (Neopixel Ring)

| Pattern | Color | Meaning |
|---|---|---|
| Rainbow cycling | — | Agent is booting |
| **Solid green** | 🟢 | **Ready — accepting commands** |
| Blinking green | 🟢 | Command received, processing |
| Solid red | 🔴 | Error occurred |

## How to Connect

```bash
# Windows (pick one):
mpremote connect COM32
screen COM32 115200
# Or any serial terminal at 115200 baud
```

## Commands

Send commands as single-line JSON:

### `READ_SENSORS`
Reads all sensors. Returns temperature, light, voltage, touch state, free RAM.
```json
{"command": "READ_SENSORS"}
```

### `NEOPIXEL_FILL`
Set all 10 neopixels to one color (0-255 RGB).
```json
{"command": "NEOPIXEL_FILL", "r": 255, "g": 0, "b": 0}
```

### `NEOPIXEL_RAINBOW` / `NEOPIXEL_OFF`
Start rainbow animation or turn off all neopixels.
```json
{"command": "NEOPIXEL_RAINBOW"}
{"command": "NEOPIXEL_OFF"}
```

### `TOUCH_READ`
Returns which capacitive touch pads (A1-A7) are currently touched.
```json
{"command": "TOUCH_READ"}
```

### `TONE`
Play a frequency on the speaker. Set hz=0 to stop.
```json
{"command": "TONE", "hz": 440, "duration_ms": 500}
```

### `GET_HEALTH`
Same as READ_SENSORS — returns full device health snapshot.
```json
{"command": "GET_HEALTH"}
```

### `HELP`
Returns command list and board information.
```json
{"command": "HELP"}
```

## Reproducible Flash Process

1. Double-tap the reset button on the CPlay Express
2. `CPLAYBOOT` drive appears at `D:`
3. Copy `CP-9.2.4-cplay-express.uf2` to `D:\`  (use File Explorer or `powershell Copy-Item` — NOT `cmd copy`)
4. Board reboots as `CIRCUITPY` at `D:`
5. Copy `code.py` and `npu_config.json` to `D:\`
6. Press reset — agent auto-starts, neopixels turn green

## Config

`npu_config.json` contains device identity:
```json
{
  "device_id": "nirvana-cplay-01",
  "mqtt_broker": "127.0.0.1",
  "mqtt_port": 1883
}
```

> Note: SAMD21 has no WiFi or NPU. The MQTT config is for fleet identity only.
> This board communicates via USB Serial REPL.

## Hardware

- Board: Adafruit Circuit Playground Express
- Chip: SAMD21G18 (ARM Cortex-M0+, 48MHz)
- Flash: 2MB
- RAM: 32KB
- NPU: No
- Firmware: CircuitPython 9.2.4
