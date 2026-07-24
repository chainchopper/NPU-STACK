// ╔══════════════════════════════════════════════════════════╗
// ║      NIRVANA FLEET AGENT — AMB82-Mini (RTL8735B)        ║
// ║  Voice + Vision + Display + NPU + SD Card App Store     ║
// ║  xiaozhi-compatible MQTT+UDP protocol                   ║
// ╚══════════════════════════════════════════════════════════╝
//
// Board: Realtek AMB82-Mini (AmebaD Pro2)
// Chip:  RTL8735B — Arm Cortex-M33 @ 330MHz
//        + NN engine (object detection, face recognition)
//        + 512KB SRAM + 4MB PSRAM
// Flash: 16MB SPI NOR
// WiFi:  802.11 a/b/g/n (2.4GHz + 5GHz)
// BLE:   5.1
// Cam:   OV5647 5MP CSI
// Audio: I2S mic + speaker headers
// Disp:  SPI ST7789 240x240
// SD:    SPI microSD slot
//
// Protocol: xiaozhi-esp32 MQTT+UDP hybrid
//   MQTT: control messages, state sync, JSON
//   UDP:  real-time encrypted audio (Opus)
//
// SDK: Arduino IDE + AmebaD Pro2 board package
//   Board URL: https://github.com/Ameba-AIoT/ameba-arduino-pro2

#include "nirvana_config.h"
#include "nirvana_wifi.h"
#include "nirvana_display.h"
#include "nirvana_camera.h"
#include "nirvana_audio.h"
#include "nirvana_sd.h"
#include "nirvana_ble.h"

// ═══════════════ TIMING ═══════════════
unsigned long lastStatusPublish = 0;
unsigned long lastDisplayRefresh = 0;
#define STATUS_INTERVAL_MS   30000  // Fleet status every 30s
#define DISPLAY_INTERVAL_MS  5000   // Display refresh every 5s

// ═══════════════ SETUP ═══════════════
void setup() {
    Serial.begin(115200);
    delay(1000);

    Serial.println();
    Serial.println("╔══════════════════════════════╗");
    Serial.println("║   NIRVANA FLEET — AMB82-Mini ║");
    Serial.println("╚══════════════════════════════╝");
    Serial.printf("Version: %s\n", NIRVANA_VERSION);
    Serial.printf("Device:  %s\n", NIRVANA_DEVICE_ID);
    Serial.printf("Chip:    RTL8735B (Cortex-M33 + NN)\n");

    // Initialize subsystems
    Serial.println("\n--- Hardware Init ---");

#if FEATURE_DISPLAY
    if (nirvana_display_init()) {
        Serial.println("[OK] Display");
    }
#endif

#if FEATURE_SD_CARD
    if (nirvana_sd_init()) {
        Serial.println("[OK] SD Card");
        nirvana_sd_list_apps();
    }
#endif

#if FEATURE_AUDIO
    if (nirvana_audio_init()) {
        Serial.println("[OK] Audio I2S");
    }
#endif

#if FEATURE_CAMERA
    if (nirvana_camera_init()) {
        Serial.println("[OK] Camera OV5647");
    }
#endif

    // Network
    Serial.println("\n--- Network ---");
    if (nirvana_wifi_connect()) {
        Serial.println("[OK] WiFi");
        nirvana_mqtt_connect();

#if FEATURE_BLE
        nirvana_ble_init();
#endif
    } else {
        Serial.println("[FAIL] WiFi — entering BLE provisioning mode");
        // Fall back to BLE for WiFi setup
#if FEATURE_BLE
        nirvana_ble_init();
#endif
    }

    // Show ready on display
#if FEATURE_DISPLAY
    nirvana_display_status();
#endif

    // Boot beep
#if FEATURE_AUDIO
    // nirvana_audio_beep(880, 100);
    // nirvana_audio_beep(1320, 150);
#endif

    nirvana_sd_log("Agent started");

    Serial.println("\n>>> AGENT READY <<<\n");
}

// ═══════════════ LOOP ═══════════════
void loop() {
    unsigned long now = millis();

    // Maintain MQTT connection
    nirvana_mqtt_loop();

    // Periodic fleet status
    if (now - lastStatusPublish > STATUS_INTERVAL_MS) {
        lastStatusPublish = now;
        nirvana_publish_status();
    }

    // Display refresh (cycle info screens)
    if (now - lastDisplayRefresh > DISPLAY_INTERVAL_MS) {
        lastDisplayRefresh = now;
#if FEATURE_DISPLAY
        if (displayReady) {
            static int displayPage = 0;
            displayPage = (displayPage + 1) % 3;
            switch (displayPage) {
                case 0: nirvana_display_status(); break;
                case 1:
                    // Show WiFi info
                    tft.fillScreen(TFT_BLACK);
                    nirvana_display_header("NETWORK");
                    tft.setCursor(8, 32);
                    tft.setTextColor(TFT_CYAN);
                    tft.printf("WiFi: %s", WiFi.SSID().c_str());
                    tft.setCursor(8, 50);
                    tft.printf("IP: %s", WiFi.localIP().toString().c_str());
                    tft.setCursor(8, 68);
                    tft.printf("RSSI: %d dBm", WiFi.RSSI());
                    tft.setCursor(8, 90);
                    tft.printf("MQTT: %s", mqttConnected ? "ONLINE" : "OFFLINE");
                    break;
                case 2:
                    // Fleet info
                    tft.fillScreen(TFT_BLACK);
                    nirvana_display_header("FLEET");
                    tft.setCursor(8, 32);
                    tft.setTextColor(TFT_GREEN);
                    tft.printf("Device: %s", NIRVANA_DEVICE_ID);
                    tft.setCursor(8, 55);
                    tft.printf("Protocol: MQTT+UDP");
                    tft.setCursor(8, 78);
                    tft.printf("Camera: %s", cameraReady ? "READY" : "OFF");
                    tft.setCursor(8, 101);
                    tft.printf("SD: %s", sdReady ? "READY" : "NONE");
                    tft.setCursor(8, 124);
                    tft.printf("NPU: RTL8735B");
                    tft.setCursor(8, 150);
                    tft.printf("Uptime: %lu s", now / 1000);
                    break;
            }
        }
#endif
    }

    // Audio wake word check
#if FEATURE_AUDIO
    if (audioReady && nirvana_audio_wake_word_detected()) {
        Serial.println("[AUDIO] Wake word detected!");

        // Send listen start to server
        if (mqttConnected) {
            String topic = String(NIRVANA_MQTT_TOPIC) + "/" + NIRVANA_DEVICE_ID;
            StaticJsonDocument<128> doc;
            doc["session_id"] = mqttSessionId;
            doc["type"] = "listen";
            doc["state"] = "start";
            doc["mode"] = "auto";
            char buf[128];
            serializeJson(doc, buf);
            mqtt.publish(topic.c_str(), buf);
        }

        nirvana_audio_listen_start();
    }
#endif

    // Camera capture for fleet dashboard
#if FEATURE_CAMERA
    if (cameraReady && (now - lastCapture > CAPTURE_INTERVAL_MS)) {
        lastCapture = now;

        // Run NN detection
        nirvana_camera_detect();

        // Capture and publish to fleet
        uint8_t* imgBuffer = nullptr;
        size_t imgLength = 0;
        if (nirvana_camera_capture(&imgBuffer, &imgLength)) {
            // Publish image to MQTT (or upload to fleet server)
            // mqtt.publish("npu-fleet/camera", imgBuffer, imgLength);
        }
    }
#endif

    // BLE provisioning
#if FEATURE_BLE
    nirvana_ble_provision_loop();
#endif

    // Yield to system
    delay(10);
}
