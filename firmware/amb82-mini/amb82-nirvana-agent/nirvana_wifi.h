// Nirvana Fleet Agent — WiFi + MQTT (xiaozhi-compatible protocol)
// Uses xiaozhi-esp32 MQTT+UDP hybrid protocol for fleet interoperability

#ifndef NIRVANA_WIFI_H
#define NIRVANA_WIFI_H

#include <WiFi.h>
#include <WiFiClient.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include "nirvana_config.h"

// ═══════════════ GLOBALS ═══════════════
WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);
String mqttSessionId = "";
bool mqttConnected = false;
bool udpChannelOpen = false;
unsigned long lastMqttReconnect = 0;

// ═══════════════ WIFI ═══════════════
bool nirvana_wifi_connect() {
    Serial.print("[WIFI] Connecting to ");
    Serial.println(WIFI_SSID);

    WiFi.begin(WIFI_SSID, WIFI_PASS);
    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 40) {
        delay(500);
        Serial.print(".");
        attempts++;
    }

    if (WiFi.status() == WL_CONNECTED) {
        Serial.println("\n[WIFI] Connected!");
        Serial.print("[WIFI] IP: ");
        Serial.println(WiFi.localIP());
        Serial.print("[WIFI] RSSI: ");
        Serial.println(WiFi.RSSI());
        return true;
    }
    Serial.println("\n[WIFI] FAILED!");
    return false;
}

// ═══════════════ MQTT CALLBACK ═══════════════
void nirvana_mqtt_callback(char* topic, byte* payload, unsigned int length) {
    // Build JSON string from payload
    char json[1024] = {0};
    unsigned int copyLen = min(length, (unsigned int)1023);
    memcpy(json, payload, copyLen);

    StaticJsonDocument<512> doc;
    DeserializationError err = deserializeJson(doc, json);
    if (err) {
        Serial.print("[MQTT] JSON parse error: ");
        Serial.println(err.c_str());
        return;
    }

    const char* type = doc["type"] | "";
    Serial.print("[MQTT] Received: ");
    Serial.println(type);

    // === xiaozhi protocol messages ===
    if (strcmp(type, "hello") == 0) {
        // Server hello response — open UDP channel
        const char* sess = doc["session_id"] | "";
        mqttSessionId = String(sess);
        Serial.print("[MQTT] Session: ");
        Serial.println(mqttSessionId);

        // Parse UDP endpoint from hello response
        JsonObject udpObj = doc["udp"];
        if (!udpObj.isNull()) {
            const char* udpServer = udpObj["server"] | "";
            int udpPort = udpObj["port"] | 8888;
            Serial.printf("[UDP] Endpoint: %s:%d\n", udpServer, udpPort);
            // UDP channel opened by main loop
            udpChannelOpen = true;
        }

        // Parse audio params
        JsonObject audioObj = doc["audio_params"];
        if (!audioObj.isNull()) {
            int sampleRate = audioObj["sample_rate"] | 24000;
            Serial.printf("[AUDIO] Server rate: %d Hz\n", sampleRate);
        }
    }
    else if (strcmp(type, "tts") == 0) {
        // TTS audio data — play through speaker
        const char* state = doc["state"] | "";
        Serial.printf("[TTS] State: %s\n", state);
        if (strcmp(state, "start") == 0) {
            // Begin TTS playback
        } else if (strcmp(state, "stop") == 0) {
            // Stop TTS
        }
    }
    else if (strcmp(type, "stt") == 0) {
        // Speech-to-text result from server
        const char* text = doc["text"] | "";
        Serial.printf("[STT] %s\n", text);
    }
    else if (strcmp(type, "llm") == 0) {
        // LLM emotion/status for UI
        const char* emotion = doc["emotion"] | "neutral";
        Serial.printf("[LLM] Emotion: %s\n", emotion);
    }
    else if (strcmp(type, "mcp") == 0) {
        // MCP device control — relay to NPU-STACK
        JsonObject mcpPayload = doc["payload"];
        String mcpStr;
        serializeJson(mcpPayload, mcpStr);
        Serial.printf("[MCP] %s\n", mcpStr.c_str());

        // Publish to NPU-STACK fleet topic
        String fleetTopic = String(NIRVANA_MQTT_TOPIC) + "/mcp";
        mqtt.publish(fleetTopic.c_str(), mcpStr.c_str());
    }
    else if (strcmp(type, "system") == 0) {
        const char* command = doc["command"] | "";
        Serial.printf("[SYSTEM] Command: %s\n", command);
        if (strcmp(command, "reboot") == 0) {
            Serial.println("[SYSTEM] Rebooting...");
            delay(100);
            // ESP.restart() equivalent for Ameba
        }
    }
    else if (strcmp(type, "alert") == 0) {
        const char* status = doc["status"] | "";
        const char* message = doc["message"] | "";
        Serial.printf("[ALERT] %s: %s\n", status, message);
        // Show on display
    }
    else if (strcmp(type, "goodbye") == 0) {
        Serial.println("[MQTT] Server goodbye — closing UDP");
        udpChannelOpen = false;
        mqttSessionId = "";
    }
}

// ═══════════════ MQTT CONNECT ═══════════════
bool nirvana_mqtt_connect() {
    if (mqtt.connected()) return true;

    Serial.print("[MQTT] Connecting to ");
    Serial.print(MQTT_HOST);
    Serial.print(":");
    Serial.println(MQTT_PORT);

    mqtt.setServer(MQTT_HOST, MQTT_PORT);
    mqtt.setCallback(nirvana_mqtt_callback);
    mqtt.setKeepAlive(MQTT_KEEPALIVE);

    String clientId = String(NIRVANA_DEVICE_ID) + "-" + String(random(1000, 9999));
    if (mqtt.connect(clientId.c_str())) {
        Serial.println("[MQTT] Connected!");

        // Subscribe to device-specific topic
        String topic = String(NIRVANA_MQTT_TOPIC) + "/" + NIRVANA_DEVICE_ID;
        mqtt.subscribe(topic.c_str());
        Serial.printf("[MQTT] Subscribed: %s\n", topic.c_str());

        // Send xiaozhi-compatible hello
        StaticJsonDocument<384> hello;
        hello["type"] = "hello";
        hello["version"] = 3;
        hello["transport"] = "udp";
        JsonObject features = hello.createNestedObject("features");
        features["mcp"] = true;
        features["aec"] = false;
        features["glyph_push"] = true;
        JsonObject textFont = hello.createNestedObject("text_font");
        textFont["bundle"] = "noto-v1";
        textFont["charset"] = "common";
        textFont["size"] = 20;
        textFont["bpp"] = 4;
        JsonObject audioParams = hello.createNestedObject("audio_params");
        audioParams["format"] = "opus";
        audioParams["sample_rate"] = AUDIO_SAMPLE_RATE;
        audioParams["channels"] = 1;
        audioParams["frame_duration"] = AUDIO_FRAME_MS;

        char buffer[512];
        serializeJson(hello, buffer);
        mqtt.publish(topic.c_str(), buffer);
        Serial.printf("[MQTT] Hello sent: %s\n", buffer);

        mqttConnected = true;
        return true;
    }

    Serial.print("[MQTT] Failed, rc=");
    Serial.println(mqtt.state());
    return false;
}

// ═══════════════ FLEET STATUS PUBLISH ═══════════════
void nirvana_publish_status() {
    if (!mqtt.connected()) return;

    String topic = String(NIRVANA_MQTT_TOPIC) + "/status";
    StaticJsonDocument<256> doc;
    doc["device"] = NIRVANA_DEVICE_ID;
    doc["fleet"] = NIRVANA_FLEET_NAME;
    doc["version"] = NIRVANA_VERSION;
    doc["uptime"] = millis() / 1000;
    doc["wifi_rssi"] = WiFi.RSSI();
    doc["free_heap"] = ESP.getFreeHeap(); // Ameba equivalent
    doc["display"] = FEATURE_DISPLAY;
    doc["camera"] = FEATURE_CAMERA;
    doc["sd_card"] = FEATURE_SD_CARD;

    char buffer[256];
    serializeJson(doc, buffer);
    mqtt.publish(topic.c_str(), buffer);
}

// ═══════════════ MAINTAIN CONNECTION ═══════════════
void nirvana_mqtt_loop() {
    if (!mqtt.connected()) {
        unsigned long now = millis();
        if (now - lastMqttReconnect > 5000) {
            lastMqttReconnect = now;
            if (nirvana_wifi_connect()) {
                nirvana_mqtt_connect();
            }
        }
    }
    mqtt.loop();
}

#endif // NIRVANA_WIFI_H
