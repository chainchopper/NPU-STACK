// Nirvana Fleet Agent — Display Driver (ST7789 SPI LCD)
// For AMB82-Mini carrier board

#ifndef NIRVANA_DISPLAY_H
#define NIRVANA_DISPLAY_H

#include <TFT_eSPI.h>  // Bodmer's TFT library (configure User_Setup.h)
#include "nirvana_config.h"

TFT_eSPI tft = TFT_eSPI();
bool displayReady = false;

// ═══════════════ INIT ═══════════════
bool nirvana_display_init() {
    pinMode(TFT_BL, OUTPUT);
    digitalWrite(TFT_BL, HIGH);  // Backlight on

    tft.init();
    tft.setRotation(2);  // Landscape
    tft.fillScreen(TFT_BLACK);
    tft.setTextColor(TFT_WHITE);

    // Boot splash
    tft.setTextSize(2);
    tft.setCursor(20, 80);
    tft.print(NIRVANA_FLEET_NAME);

    tft.setTextSize(1);
    tft.setCursor(20, 120);
    tft.print("AMB82-Mini Agent ");
    tft.print(NIRVANA_VERSION);

    displayReady = true;
    Serial.println("[DISP] ST7789 initialized");
    return true;
}

// ═══════════════ DRAW HEADER ═══════════════
void nirvana_display_header(const char* title) {
    if (!displayReady) return;
    tft.fillRect(0, 0, TFT_WIDTH, 24, TFT_PURPLE);
    tft.setTextColor(TFT_WHITE);
    tft.setTextSize(1);
    tft.setCursor(4, 6);
    tft.printf("%s // %s", NIRVANA_FLEET_NAME, title);
}

// ═══════════════ DRAW STATUS ═══════════════
void nirvana_display_status() {
    if (!displayReady) return;
    tft.fillScreen(TFT_BLACK);
    nirvana_display_header("STATUS");

    tft.setTextColor(0x07E0);  // Green
    tft.setCursor(8, 32);
    tft.printf("Device: %s", NIRVANA_DEVICE_ID);
    tft.setCursor(8, 50);
    tft.printf("Version: %s", NIRVANA_VERSION);
    tft.setCursor(8, 72);
    tft.printf("Chip: RTL8735B (M33+NN)");
    tft.setCursor(8, 90);
    tft.printf("WiFi: %s", WiFi.SSID().c_str());
    tft.setCursor(8, 108);
    tft.printf("IP: %s", WiFi.localIP().toString().c_str());
    tft.setCursor(8, 130);
    tft.printf("Free Heap: %d", ESP.getFreeHeap());
}

// ═══════════════ DRAW ALERT ═══════════════
void nirvana_display_alert(const char* title, const char* message, uint16_t color) {
    if (!displayReady) return;
    tft.fillScreen(TFT_BLACK);

    // Alert banner
    tft.fillRect(0, 0, TFT_WIDTH, 40, color);
    tft.setTextColor(TFT_WHITE);
    tft.setTextSize(2);
    tft.setCursor(10, 10);
    tft.print(title);

    // Message
    tft.setTextColor(TFT_WHITE);
    tft.setTextSize(1);
    tft.setCursor(10, 60);
    tft.print(message);
}

// ═══════════════ DRAW EMOTION ═══════════════
void nirvana_display_emotion(const char* emotion) {
    if (!displayReady) return;
    tft.fillScreen(TFT_BLACK);
    nirvana_display_header("NIRVANA");

    tft.setTextSize(4);
    tft.setTextColor(TFT_WHITE);

    // Map emotion to emoji
    const char* emoji = "\x01";  // Default
    if (strcmp(emotion, "happy") == 0) emoji = "\x02";
    else if (strcmp(emotion, "sad") == 0) emoji = "\x03";
    else if (strcmp(emotion, "angry") == 0) emoji = "\x04";
    else if (strcmp(emotion, "surprised") == 0) emoji = "\x05";

    // Center the emoji
    int16_t x = (TFT_WIDTH - 100) / 2;
    int16_t y = (TFT_HEIGHT - 48) / 2;
    tft.setCursor(x, y);
    tft.print(emoji);
}

#endif // NIRVANA_DISPLAY_H
