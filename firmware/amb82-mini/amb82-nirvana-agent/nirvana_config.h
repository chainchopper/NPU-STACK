// Nirvana Fleet Agent — AMB82-Mini Configuration
// Board: Realtek RTL8735B (AmebaD Pro2)
// Flash: 16MB SPI, RAM: 512KB SRAM + 4MB PSRAM

#ifndef NIRVANA_CONFIG_H
#define NIRVANA_CONFIG_H

// ═══════════════ FLEET BRANDING ═══════════════
#define NIRVANA_DEVICE_ID    "npu-amb82-001"
#define NIRVANA_FLEET_NAME   "NIRVANA FLEET"
#define NIRVANA_VERSION      "v1.0-amb82"
#define NIRVANA_MQTT_TOPIC   "npu-fleet/amb82"

// ═══════════════ WIFI ═══════════════
// Override in secrets.h or via BLE provisioning
#ifndef WIFI_SSID
#define WIFI_SSID           "YOUR_SSID"
#endif
#ifndef WIFI_PASS
#define WIFI_PASS           "YOUR_PASSWORD"
#endif

// ═══════════════ MQTT BROKER ═══════════════
// NPU-STACK backend (mosquitto on :1883)
#ifndef MQTT_HOST
#define MQTT_HOST           "192.168.1.100"
#endif
#define MQTT_PORT           1883
#define MQTT_KEEPALIVE      240

// ═══════════════ AUDIO ═══════════════
// I2S pins for mic + speaker
#define I2S_BCLK            PA30
#define I2S_LRCLK           PA31
#define I2S_MIC_DIN         PA28
#define I2S_SPKR_DOUT       PA29
#define AUDIO_SAMPLE_RATE   16000
#define AUDIO_FRAME_MS      60

// ═══════════════ DISPLAY ═══════════════
// ST7789 240x240 SPI LCD (pinout per AMB82-Mini carrier board)
#define TFT_MOSI            PA12
#define TFT_SCLK            PA13
#define TFT_CS              PA14
#define TFT_DC              PA15
#define TFT_RST             PA16
#define TFT_BL              PA17
#define TFT_WIDTH           240
#define TFT_HEIGHT          240

// ═══════════════ CAMERA ═══════════════
// OV5647 CSI
#define CAM_I2C_SDA         PA26
#define CAM_I2C_SCL         PA27

// ═══════════════ SD CARD ═══════════════
#define SD_CS               PA18
#define SD_MOSI             PA19
#define SD_MISO             PA20
#define SD_SCLK             PA21

// ═══════════════ NPU (Neural Network) ═══════════════
// RTL8735B built-in NN engine
// Use Ameba NN API for face detection, object recognition
// Model files stored on SD card: /models/*.nb

// ═══════════════ FEATURE FLAGS ═══════════════
#define FEATURE_DISPLAY     1
#define FEATURE_CAMERA      1
#define FEATURE_AUDIO       1
#define FEATURE_SD_CARD     1
#define FEATURE_BLE         1
#define FEATURE_NPU         1

#endif // NIRVANA_CONFIG_H
