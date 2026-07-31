// ╔══════════════════════════════════════════════════════════╗
// ║   NIRVANA FLEET AGENT — AMB82-Mini + ILI9341 + XiaoZhi  ║
// ║   RTL8735B Cortex-M33 @ 500MHz + NN Engine              ║
// ║   Bit-banged SPI LCD driver — zero peripheral conflicts ║
// ╚══════════════════════════════════════════════════════════╝

#include "nirvana_config.h"
#include "nirvana_ili9341.h"
#include "nirvana_wifi.h"

unsigned long lastStatus=0, lastDisplay=0, lastLed=0;
int page=0;
bool ledState=false;

void setup(){
    Serial.begin(115200); delay(2000);

    Serial.println();
    Serial.println("=========================================");
    Serial.println("  NIRVANA FLEET — AMB82-Mini + ILI9341");
    Serial.println("  Bit-banged SPI | RTL8735B + NN Engine");
    Serial.println("=========================================");
    Serial.print("  Version: "); Serial.println(NIRVANA_VERSION);
    Serial.print("  Device:  "); Serial.println(NIRVANA_DEVICE_ID);

    // ── Onboard LEDs ──
    pinMode(ONBOARD_LED_BLUE, OUTPUT);
    pinMode(ONBOARD_LED_GREEN, OUTPUT);
    digitalWrite(ONBOARD_LED_BLUE, HIGH);
    digitalWrite(ONBOARD_LED_GREEN, LOW);
    Serial.println("[LED] OK");

    // ── Display (bit-banged SPI via GPIO, no SPI library) ──
    Serial.println("--- Display ---");
    if (nirvana_display_init()) {
        nirvana_splash("Connecting...", NIRVANA_VERSION);
        Serial.println("[DISP] Splash shown");
    }

    // ── WiFi ──
    Serial.println("--- Network ---");
    if (nirvana_wifi_connect()) {
        char ip[20];
        snprintf(ip, sizeof(ip), "%d.%d.%d.%d",
            WiFi.localIP()[0], WiFi.localIP()[1],
            WiFi.localIP()[2], WiFi.localIP()[3]);
        nirvana_splash(ip, NIRVANA_VERSION);

        // ── MQTT (xiaozhi hello) ──
        if (nirvana_mqtt_connect()) {
            digitalWrite(ONBOARD_LED_GREEN, HIGH);
            Serial.println("[MQTT] Fleet registered");
        }
    }

    digitalWrite(ONBOARD_LED_BLUE, LOW);
    Serial.println("\n>>> NIRVANA FLEET AGENT READY <<<\n");
}

void loop(){
    nirvana_mqtt_loop();
    unsigned long now = millis();

    // Fleet heartbeat (30s)
    if (now - lastStatus > 30000) { lastStatus = now; nirvana_publish_status(); }

    // Blue LED pulse (1s)
    if (now - lastLed > 1000) {
        lastLed = now; ledState = !ledState;
        digitalWrite(ONBOARD_LED_BLUE, ledState ? HIGH : LOW);
    }

    // Display page cycling (5s)
    if (now - lastDisplay > 5000) {
        lastDisplay = now; page = (page + 1) % 3;
        char ip[20], ssid[40];
        snprintf(ip, sizeof(ip), "%d.%d.%d.%d",
            WiFi.localIP()[0], WiFi.localIP()[1],
            WiFi.localIP()[2], WiFi.localIP()[3]);
        strncpy(ssid, WiFi.SSID(), sizeof(ssid)-1); ssid[sizeof(ssid)-1] = 0;
        int rssi = WiFi.RSSI();
        if (page == 0)      nirvana_page_status(ip, ssid, rssi, mqttConnected, now/1000);
        else if (page == 1) nirvana_page_network(ip, ssid, rssi);
        else                nirvana_page_fleet(mqttConnected, now/1000);
    }

    delay(10);
}
