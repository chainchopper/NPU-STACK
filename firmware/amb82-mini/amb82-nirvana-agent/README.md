# Nirvana Fleet Agent — AMB82-Mini (Realtek RTL8735B)

## Architecture
```
amb82-nirvana-agent/
├── amb82-nirvana-agent.ino     # Main sketch
├── nirvana_config.h            # Fleet branding + pinout
├── nirvana_wifi.h              # WiFi + MQTT (xiaozhi protocol)
├── nirvana_display.h           # SPI LCD driver
├── nirvana_camera.h            # OV5647 NN camera
├── nirvana_audio.h             # I2S mic/speaker
├── nirvana_sd.h                # SD card app storage
├── nirvana_ble.h               # BLE provisioning
└── FLASH_GUIDE.md              # How to flash
```

## Features
- **Voice**: I2S mic + speaker, Opus codec, wake word detection
- **Vision**: OV5647 camera with RTL8735B NN engine
- **Display**: SPI LCD 240x240
- **Network**: WiFi 5GHz + BLE 5.1
- **Protocol**: xiaozhi-compatible MQTT + UDP hybrid
- **Storage**: SD card for apps/assets/logs
- **Fleet**: Auto-registers with NPU-STACK backend via MQTT

## SDK Requirements
- Arduino IDE 2.x
- AmebaD Pro2 board package (https://github.com/Ameba-AIoT/ameba-arduino-pro2)
- Board: "Ameba ARDUINO with AMB82-mini (RTL8735B)"

## Flash
1. Install Arduino IDE
2. Add board URL: https://github.com/Ameba-AIoT/ameba-arduino-pro2/raw/main/Arduino_package/package_realtek_amebapro2_early_index.json
3. Install "Realtek Ameba Boards" package
4. Select board: "AMB82-Mini"
5. Open `amb82-nirvana-agent.ino`
6. Set WiFi credentials in `nirvana_config.h`
7. Upload

## Pin Map (AMB82-Mini)
| Function | Pin |
|----------|-----|
| LCD MOSI | PA12 |
| LCD SCK  | PA13 |
| LCD CS   | PA14 |
| LCD DC   | PA15 |
| LCD RST  | PA16 |
| LCD BL   | PA17 |
| Camera SDA | PA26 |
| Camera SCL | PA27 |
| I2S Mic DIN | PA28 |
| I2S Spkr DOUT | PA29 |
| I2S BCLK | PA30 |
| I2S LRCLK | PA31 |
| SD CS    | PA18 |
| SD MOSI  | PA19 |
| SD MISO  | PA20 |
| SD SCK   | PA21 |
