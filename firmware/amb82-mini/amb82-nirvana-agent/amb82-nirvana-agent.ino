// NIRVANA FLEET AGENT — AMB82-Mini + Waveshare 2.4" ILI9341
// Features: ILI9341 240x320 SPI LCD, WiFi, MQTT (xiaozhi protocol), NN engine ready
// Chip: Realtek RTL8735B (Arm Cortex-M33 @ 500MHz + NN)
// Flash: 16MB, RAM: 512KB SRAM + 4MB PSRAM

#include "nirvana_config.h"
#include "nirvana_ili9341.h"
#include "nirvana_wifi.h"

unsigned long lastStatus = 0, lastDisplay = 0;
int page = 0;

void setup() {
    Serial.begin(115200); delay(1000);
    Serial.println("\n=== NIRVANA FLEET — AMB82-Mini + ILI9341 ===");
    Serial.print("Version: "); Serial.println(NIRVANA_VERSION);

    SPI.begin();
    SPI.setDataMode(SPI_MODE0);
    SPI.setBitOrder(MSBFIRST);
    SPI.setClockDivider(SPI_CLOCK_DIV2);

    Serial.println("\n--- Display ---");
    if (nirvana_display_init()) {
        nirvana_center("BOOTING...", 140, 0x07E0, 2);
    }

    Serial.println("\n--- Network ---");
    if (nirvana_wifi_connect()) nirvana_mqtt_connect();

    Serial.println("\n>>> AGENT READY <<<\n");
}

void loop() {
    nirvana_mqtt_loop();
    unsigned long now = millis();

    if (now - lastStatus > 30000) {
        lastStatus = now;
        nirvana_publish_status();
    }

    if (now - lastDisplay > 5000) {
        lastDisplay = now;
        page = (page + 1) % 3;

        char ip[20]; snprintf(ip, sizeof(ip), "%d.%d.%d.%d",
            WiFi.localIP()[0], WiFi.localIP()[1],
            WiFi.localIP()[2], WiFi.localIP()[3]);

        if (page == 0)      nirvana_page_status(ip, WiFi.RSSI(), mqttConnected);
        else if (page == 1) nirvana_page_network(ip, WiFi.RSSI());
        else                nirvana_page_fleet(mqttConnected, now / 1000);
    }

    delay(10);
}
