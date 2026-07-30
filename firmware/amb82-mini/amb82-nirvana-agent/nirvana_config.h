// Nirvana Fleet Agent — AMB82-Mini Configuration
// Board: Realtek RTL8735B (AmebaD Pro2 SDK)
// Display: Waveshare 2.4" ILI9341 240x320 SPI

#ifndef NIRVANA_CONFIG_H
#define NIRVANA_CONFIG_H

// ═══ FLEET BRANDING ═══
#define NIRVANA_DEVICE_ID    "npu-amb82-001"
#define NIRVANA_FLEET_NAME   "NIRVANA FLEET"
#define NIRVANA_VERSION      "v2.0-ili9341"

// ═══ WIFI ═══
#ifndef WIFI_SSID
#define WIFI_SSID           "YOUR_SSID"
#endif
#ifndef WIFI_PASS
#define WIFI_PASS           "YOUR_PASSWORD"
#endif

// ═══ MQTT ═══
#ifndef MQTT_HOST
#define MQTT_HOST           "192.168.1.100"
#endif
#define MQTT_PORT           1883
#define MQTT_KEEPALIVE      240
#define MQTT_TOPIC_PREFIX   "npu-fleet/amb82"

// ═══ DISPLAY: Waveshare 2.4inch ILI9341 ═══
// LCD pin  →  AMB82 pin  →  Chip pin
// DIN/MOSI →  AMB_D13    →  PE_3  (default SPI MOSI)
// CLK/SCLK →  AMB_D15    →  PE_1  (default SPI SCLK)
// CS       →  AMB_D12    →  PE_4  (default SPI SS)
// DC       →  AMB_D7     →  PF_14 (GPIO)
// RST      →  AMB_D8     →  PF_15 (GPIO)
// BL       →  AMB_D4     →  PF_11 (PWM)
#define TFT_CS              AMB_D12
#define TFT_DC              AMB_D7
#define TFT_RST             AMB_D8
#define TFT_BL              AMB_D4
#define TFT_WIDTH           240
#define TFT_HEIGHT          320

// ═══ COLORS (RGB565) ═══
#define NIRVANA_PURPLE      0x8010
#define NIRVANA_GREEN       0x07E0
#define NIRVANA_BLACK       0x0000
#define NIRVANA_WHITE       0xFFFF
#define NIRVANA_CYAN        0x07FF
#define NIRVANA_RED         0xF800
#define NIRVANA_GRAY        0x8410

#endif
