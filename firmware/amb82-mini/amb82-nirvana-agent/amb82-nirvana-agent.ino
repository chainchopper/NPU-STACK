// ╔══════════════════════════════════════════════════════════╗
// ║   NIRVANA FLEET AGENT — AMB82-Mini FULL STACK          ║
// ║   RTL8735B Cortex-M33 @ 500MHz + VIPLite NN Engine     ║
// ║   ILI9341 + CSI Camera + I2S Audio + XiaoZhi MQTT      ║
// ║   Bit-banged SPI LCD driver — zero peripheral conflicts║
// ╚══════════════════════════════════════════════════════════╝

#include "nirvana_config.h"
#include "nirvana_ili9341.h"
#include "nirvana_wifi.h"
#include "nirvana_camera.h"
#include "nirvana_audio.h"
#include "nirvana_nn.h"

unsigned long lastStatus=0, lastDisplay=0, lastLed=0;
int page=0;
bool ledState=false;
char agentIP[20]="";
char agentSSID[40]="";

void setup(){
    Serial.begin(115200); delay(2000);

    Serial.println();
    Serial.println("╔═══════════════════════════════════════╗");
    Serial.println("║  NIRVANA FLEET — AMB82-Mini FULL     ║");
    Serial.println("║  ILI9341 + CSI + I2S + NN + MQTT     ║");
    Serial.println("╚═══════════════════════════════════════╝");
    Serial.print("  Version: "); Serial.println(NIRVANA_VERSION);
    Serial.print("  Device:  "); Serial.println(NIRVANA_DEVICE_ID);

    // ── Onboard LEDs ──
    pinMode(ONBOARD_LED_BLUE, OUTPUT);
    pinMode(ONBOARD_LED_GREEN, OUTPUT);
    digitalWrite(ONBOARD_LED_BLUE, HIGH);
    digitalWrite(ONBOARD_LED_GREEN, LOW);
    Serial.println("[LED] OK");

    // ── Display (bit-banged SPI via GPIO) ──
    Serial.println("--- Display ---");
    nirvana_display_init();
    nirvana_splash("Booting...", NIRVANA_VERSION);

    // ── WiFi ──
    Serial.println("--- Network ---");
    if (nirvana_wifi_connect()) {
        snprintf(agentIP,sizeof(agentIP),"%d.%d.%d.%d",
            WiFi.localIP()[0],WiFi.localIP()[1],WiFi.localIP()[2],WiFi.localIP()[3]);
        strncpy(agentSSID,WiFi.SSID(),sizeof(agentSSID)-1);agentSSID[sizeof(agentSSID)-1]=0;
        nirvana_splash(agentIP, NIRVANA_VERSION);

        // ── MQTT ──
        if (nirvana_mqtt_connect()) {
            digitalWrite(ONBOARD_LED_GREEN, HIGH);
            Serial.println("[MQTT] Fleet registered");
        }
    }

    // ── Camera (CSI MIPI) ──
    Serial.println("--- Camera ---");
    nirvana_camera_init();

    // ── Audio (I2S codec) ──
    Serial.println("--- Audio ---");
    nirvana_audio_init();

    // ── NN Object Detection (YOLOv4 Tiny) ──
    Serial.println("--- NN Engine ---");
    nirvana_nn_od_init(camConfigNN);

    // ── StreamIO pipeline: Camera CH3 → YOLOv4 ──
    Serial.println("--- Pipeline ---");
    nirvana_camera_pipe_to(CAM_CH_NN, nnOD);
    nirvana_camera_start(CAM_CH_NN);

    digitalWrite(ONBOARD_LED_BLUE, LOW);
    Serial.println("\n>>> NIRVANA FLEET FULL STACK READY <<<\n");
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

    // Display page cycling (5s) — 4 pages
    if (now - lastDisplay > 5000) {
        lastDisplay = now; page = (page + 1) % 4;
        int rssi = WiFi.RSSI();

        if (page == 0)
            nirvana_page_status(agentIP, agentSSID, rssi, mqttConnected, now/1000);
        else if (page == 1)
            nirvana_page_network(agentIP, agentSSID, rssi);
        else if (page == 2)
            nirvana_page_fleet(mqttConnected, now/1000);
        else
            nirvana_page_nn(odCount, (const char*)odTopLabel, odTopScore,
                           faceCount, camReady, audioReady);
    }

    delay(10);
}
