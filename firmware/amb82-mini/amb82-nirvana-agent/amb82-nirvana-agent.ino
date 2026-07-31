// ╔══════════════════════════════════════════════════════════╗
// ║   NIRVANA FLEET AGENT — AMB82-Mini + ILI9341 + XiaoZhi  ║
// ║   RTL8735B Cortex-M33 @ 500MHz + NN Engine              ║
// ║   16MB Flash / 4MB PSRAM / WiFi 5GHz / BLE 5.1          ║
// ╚══════════════════════════════════════════════════════════╝
//
// Capabilities:
//   • ILI9341 240x320 TFT — Nirvana-branded fleet dashboard
//   • WiFi 802.11 a/b/g/n — connects to NPU-STACK backend
//   • MQTT voice protocol — xiaozhi-compatible hello/listen/TTS/STT
//   • Onboard LEDs — Blue (D23) fleet heartbeat, Green (D24) MQTT status
//   • Fleet heartbeat — 30s status publish over MQTT
//   • 3 display pages — Status, Network, Fleet Comms
//   • OV5647 camera + I2S audio + NN engine (pins mapped, stubs ready)

#include "nirvana_config.h"
#include "nirvana_ili9341.h"
#include "nirvana_wifi.h"

unsigned long lastStatus=0,lastDisplay=0,lastLed=0;
int page=0;
bool ledState=false;
bool displayOk=false;

void setup(){
    Serial.begin(115200);delay(2000);

    Serial.println();
    Serial.println("=========================================");
    Serial.println("  NIRVANA FLEET — AMB82-Mini + ILI9341");
    Serial.println("  RTL8735B Cortex-M33 + NN Engine");
    Serial.println("=========================================");
    Serial.print("  Version: ");Serial.println(NIRVANA_VERSION);
    Serial.print("  Device:  ");Serial.println(NIRVANA_DEVICE_ID);
    Serial.println();

    // ── STEP 1: SPI.init() FIRST (critical for Ameba SDK) ──
    SPI.begin();
    Serial.println("[SPI] SPI.begin() OK");
    delay(10);

    // ── STEP 2: Onboard LEDs ──
    pinMode(ONBOARD_LED_BLUE, OUTPUT);
    pinMode(ONBOARD_LED_GREEN, OUTPUT);
    digitalWrite(ONBOARD_LED_BLUE, HIGH);  // Blue on = booting
    digitalWrite(ONBOARD_LED_GREEN, LOW);
    Serial.println("[LED] Onboard LEDs ready");

    // ── STEP 3: Display ──
    Serial.println();
    Serial.println("--- Display ---");
    displayOk=nirvana_display_init();
    if(displayOk){
        nirvana_splash("Connecting...",NIRVANA_VERSION);
        Serial.println("[DISP] Nirvana splash shown");
    }

    // ── STEP 4: WiFi ──
    Serial.println();
    Serial.println("--- Network ---");
    if(nirvana_wifi_connect()){
        char ip[20];
        snprintf(ip,sizeof(ip),"%d.%d.%d.%d",WiFi.localIP()[0],WiFi.localIP()[1],WiFi.localIP()[2],WiFi.localIP()[3]);
        if(displayOk)nirvana_splash(ip,NIRVANA_VERSION);

        // ── STEP 5: MQTT (xiaozhi protocol) ──
        if(nirvana_mqtt_connect()){
            Serial.println("[MQTT] XiaoZhi hello sent — fleet registered");
            digitalWrite(ONBOARD_LED_GREEN, HIGH);  // Green = MQTT online
        }
    }

    digitalWrite(ONBOARD_LED_BLUE, LOW);  // Boot complete

    Serial.println();
    Serial.println(">>> NIRVANA FLEET AGENT READY <<<");
    Serial.println("    Display: ILI9341 240x320 (3 pages)");
    Serial.println("    MQTT:    xiaozhi protocol (hello/TTS/STT/MCP)");
    Serial.println("    Voice:   I2S stubs ready (camera + speaker headers)");
    Serial.println("    NN:      RTL8735B built-in engine");
    Serial.println();
}

void loop(){
    nirvana_mqtt_loop();
    unsigned long now=millis();

    // ── Fleet status heartbeat (every 30s) ──
    if(now-lastStatus>30000){lastStatus=now;nirvana_publish_status();}

    // ── Blue LED heartbeat (every 1s) ──
    if(now-lastLed>1000){
        lastLed=now;ledState=!ledState;
        digitalWrite(ONBOARD_LED_BLUE,ledState?HIGH:LOW);
    }

    // ── Display page cycling (every 5s) ──
    if(displayOk && now-lastDisplay>5000){
        lastDisplay=now;page=(page+1)%3;
        char ip[20],ssid[40];
        snprintf(ip,sizeof(ip),"%d.%d.%d.%d",WiFi.localIP()[0],WiFi.localIP()[1],WiFi.localIP()[2],WiFi.localIP()[3]);
        strncpy(ssid,WiFi.SSID(),sizeof(ssid)-1);ssid[sizeof(ssid)-1]=0;
        int rssi=WiFi.RSSI();
        if(page==0)     nirvana_page_status(ip,ssid,rssi,mqttConnected,now/1000);
        else if(page==1)nirvana_page_network(ip,ssid,rssi);
        else            nirvana_page_fleet(mqttConnected,now/1000);
    }

    delay(10);
}
