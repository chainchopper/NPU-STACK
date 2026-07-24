# Flash Guide: Nirvana Fleet Agent for AMB82-Mini

## Prerequisites
- AMB82-Mini board (Realtek RTL8735B)
- USB-C cable
- Arduino IDE 2.x
- microSD card (optional, for app storage)
- ST7789 SPI LCD (optional)
- OV5647 camera (optional)

## Step 1: Install Arduino IDE + Ameba SDK

1. Download Arduino IDE from https://www.arduino.cc/en/software
2. Open Arduino IDE → File → Preferences
3. Add board URL:
   ```
   https://github.com/Ameba-AIoT/ameba-arduino-pro2/raw/main/Arduino_package/package_realtek_amebapro2_early_index.json
   ```
4. Tools → Board → Boards Manager → Search "Realtek"
5. Install "Realtek Ameba Boards (AmebaD Pro2)"
6. Select board: Tools → Board → "AMB82-Mini (RTL8735B)"

## Step 2: Install Libraries

In Arduino IDE Library Manager (Tools → Manage Libraries), install:
- PubSubClient (by Nick O'Leary)
- ArduinoJson (by Benoit Blanchon)
- TFT_eSPI (by Bodmer)

## Step 3: Configure

Edit `nirvana_config.h`:
```cpp
#define WIFI_SSID     "YOUR_WIFI_NAME"
#define WIFI_PASS     "YOUR_WIFI_PASSWORD"
#define MQTT_HOST     "192.168.1.100"  // NPU-STACK server IP
```

For TFT_eSPI, configure `User_Setup.h` in the library:
```cpp
#define ST7789_DRIVER
#define TFT_WIDTH  240
#define TFT_HEIGHT 240
#define TFT_MOSI PA12
#define TFT_SCLK PA13
#define TFT_CS   PA14
#define TFT_DC   PA15
#define TFT_RST  PA16
#define TFT_BL   PA17
```

## Step 4: Flash

1. Connect AMB82-Mini via USB-C
2. Select the correct COM port
3. Click Upload (→)
4. Open Serial Monitor (115200 baud) to see agent output

## Step 5: Verify

Serial output should show:
```
╔══════════════════════════════╗
║   NIRVANA FLEET — AMB82-Mini ║
╚══════════════════════════════╝
[WIFI] Connecting to YOUR_SSID
[WIFI] Connected! IP: 192.168.x.x
[MQTT] Connected!
>>> AGENT READY <<<
```

Display shows "NIRVANA FLEET // STATUS" with device info.

## SD Card Setup (App Store)

Format microSD as FAT32. Create directory structure:
```
/apps/     # Arduino sketch apps
/models/   # NN model files (.nb)
/assets/   # Fonts, images, sounds
/logs/     # Agent logs
/config/   # Configuration
/cache/    # Temp data
```

## MQTT Topics

| Topic | Direction | Purpose |
|-------|-----------|---------|
| `npu-fleet/amb82/{device_id}` | Device→Server | Hello, listen, MCP |
| `npu-fleet/amb82/{device_id}` | Server→Device | TTS, STT, alerts |
| `npu-fleet/amb82/status` | Device→Server | Periodic fleet heartbeat |
| `npu-fleet/amb82/mcp` | Device↔Server | IoT device control |

## Protocol Compatibility

This agent implements the xiaozhi-esp32 MQTT+UDP hybrid protocol:
- MQTT for control messages (JSON)
- UDP for real-time encrypted audio (Opus/AES-CTR)
- Compatible with xiaozhi-esp32-server and NPU-STACK backend
