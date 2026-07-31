// Nirvana Fleet Agent — AMB82-Mini Configuration
// Board: Realtek RTL8735B (AmebaD Pro2 SDK)
// Display: Waveshare 2.4" ILI9341 240x320 SPI
//
// ═══ ONBOARD HARDWARE (DO NOT REPURPOSE) ═══
// LED_B      = AMB_D23 (PF_9)  — Blue LED / LED_BUILTIN
// LED_G      = AMB_D24 (PE_6)  — Green LED
// PUSH_BTN   = AMB_D29 (PF_10) — Push button
// LOG_TX     = AMB_D25 (PF_4)  — Debug UART TX
// LOG_RX     = AMB_D26 (PF_3)  — Debug UART RX (also ADC CH3, disabled)
//
// ═══ LCD PIN ASSIGNMENTS (Waveshare 2.4" ILI9341) ═══
// LCD pin  →  AMB82 pin  →  Chip pin  →  Notes
// DIN/MOSI →  AMB_D13    →  PE_3       →  Default HW SPI MOSI
// CLK/SCLK →  AMB_D15    →  PE_1       →  Default HW SPI SCLK
// CS       →  AMB_D12    →  PE_4       →  Default HW SPI SS (shares I2C_SDA)
// DC       →  AMB_D7     →  PF_14      →  GPIO, PWM-capable
// RST      →  AMB_D8     →  PF_15      →  GPIO, PWM-capable
// BL       →  AMB_D5     →  PF_12      →  GPIO, PWM-capable (backlight)
// VCC      →  3.3V
// GND      →  GND
//
// ═══ CONFIRMED SAFE — no conflicts with onboard LEDs/button/LOG ═══

#ifndef NIRVANA_CONFIG_H
#define NIRVANA_CONFIG_H

// ═══ FLEET BRANDING ═══
#define NIRVANA_DEVICE_ID    "npu-amb82-001"
#define NIRVANA_FLEET_NAME   "NIRVANA FLEET"
#define NIRVANA_VERSION      "v3.1-nirvana-os"

// ═══ WIFI ═══
#ifndef WIFI_SSID
#define WIFI_SSID           "DaMatrix-5G"
#endif
#ifndef WIFI_PASS
#define WIFI_PASS           "N0b0ss434343#"
#endif

// ═══ MQTT ═══
#ifndef MQTT_HOST
#define MQTT_HOST           "192.168.1.100"
#endif
#define MQTT_PORT           1883
#define MQTT_KEEPALIVE      240
#define MQTT_TOPIC_PREFIX   "npu-fleet/amb82"

// ═══ ONBOARD PERIPHERALS (reference — use in agent code) ═══
#define ONBOARD_LED_BLUE     AMB_D23   // PF_9  — Blue LED, also LED_BUILTIN
#define ONBOARD_LED_GREEN    AMB_D24   // PE_6  — Green LED
#define ONBOARD_BUTTON       AMB_D29   // PF_10 — Push button (active low)
#define LOG_TX_PIN           AMB_D25   // PF_4  — Debug UART TX (DO NOT USE)
#define LOG_RX_PIN           AMB_D26   // PF_3  — Debug UART RX (DO NOT USE)

// ═══ DISPLAY: Waveshare 2.4inch ILI9341 ═══
#define TFT_CS              AMB_D12   // PE_4  — SPI SS (default)
#define TFT_DC              AMB_D7    // PF_14 — Data/Command
#define TFT_RST             AMB_D8    // PF_15 — Reset
#define TFT_BL              AMB_D5    // PF_12 — Backlight PWM (NOT D4 — conflicts with SPI1/I2S)
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
