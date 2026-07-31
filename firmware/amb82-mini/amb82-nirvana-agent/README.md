# Nirvana Fleet Agent — AMB82-Mini (Realtek RTL8735B)

## What It Does
This is a full Nirvana fleet agent running on the AMB82-Mini. It is NOT just a screen demo — it is an active member of the NPU-STACK fleet.

### Active Features (v2.0-ili9341)
- **ILI9341 240x320 TFT** — Nirvana-branded fleet dashboard with 3 auto-cycling pages (Status, Network, Fleet Comms)
- **WiFi 5GHz** — Connects to your network
- **MQTT (xiaozhi protocol)** — Sends hello/listen/TTS/STT/MCP messages to NPU-STACK backend
- **Fleet heartbeat** — 30-second status reports (device ID, firmware version, IP, RSSI, uptime)
- **Onboard LEDs** — Blue (D23) heartbeat pulse, Green (D24) MQTT online indicator
- **Display splash** — Shows device ID, IP address, version on boot

### Hardware Ready (pins mapped, stubs in code)
- **OV5647 Camera** — CSI pins mapped (PA26/PA27)
- **I2S Audio** — Mic + Speaker pins mapped (PA28-PA31)
- **NN Engine** — RTL8735B built-in, pins mapped
- **microSD** — SPI pins mapped (PA18-PA21)
- **BLE 5.1** — Advertising ready

## Pin Map

### LCD → AMB82-Mini (CRITICAL — follow exactly)
| LCD Pin | AMB82 Pin | Pin # | Chip Pin |
|---------|-----------|-------|----------|
| VCC | 3.3V | — | — |
| GND | GND | — | — |
| DIN (MOSI) | AMB_D13 | 13 | PE_3 |
| CLK (SCLK) | AMB_D15 | 15 | PE_1 |
| CS | AMB_D12 | 12 | PE_4 |
| DC | AMB_D7 | 7 | PF_14 |
| RST | AMB_D8 | 8 | PF_15 |
| **BL** | **AMB_D5** | **5** | **PF_12** |

### Onboard Hardware
| Peripheral | AMB_Dn | Chip |
|------------|--------|------|
| Blue LED | D23 | PF_9 |
| Green LED | D24 | PE_6 |
| Push Button | D29 | PF_10 |

## Flash Instructions
1. Arduino IDE → Board: "AMB82-Mini (RTL8735B)"
2. Set WiFi SSID/PASS and MQTT_HOST in `nirvana_config.h`
3. Upload
4. Open Serial Monitor (115200 baud)
5. Board boots → SPI init → Display splash → WiFi → MQTT hello → Dashboard

## Serial Output (normal boot)
```
=== ILI9341 TEST ===
[SPI] SPI.begin() OK
[LED] Onboard LEDs ready
[DISP] ILI9341 240x320 OK
[DISP] Nirvana splash shown
[WIFI] Connected! IP: 192.168.1.x
[MQTT] Connected!
[MQTT] XiaoZhi hello sent — fleet registered
>>> NIRVANA FLEET AGENT READY <<<
```

## Files
- `amb82-nirvana-agent.ino` — Main sketch: SPI → Display → WiFi → MQTT → Loop
- `nirvana_config.h` — Branding, pins, WiFi/MQTT settings, feature flags
- `nirvana_ili9341.h` — Self-contained ILI9341 SPI driver with 5x7 font + page builders
- `nirvana_wifi.h` — WiFi + MQTT with xiaozhi protocol (hello/TTS/STT/MCP callbacks)