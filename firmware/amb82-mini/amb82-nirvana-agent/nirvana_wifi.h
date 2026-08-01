// Nirvana Fleet Agent — WiFi + MQTT (Ameba SDK compatible)
// Uses AmebaMQTTClient (bundled in AmebaD Pro2 SDK)

#ifndef NIRVANA_WIFI_H
#define NIRVANA_WIFI_H

#include <WiFi.h>
#include <PubSubClient.h>  // AmebaMQTTClient — bundled in realtek:AmebaPro2
#include <ArduinoJson.h>
#include "nirvana_config.h"
#include "nirvana_config_storage.h"

// ═══ GLOBALS ═══
WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);
String mqttSessionId = "";
bool mqttConnected = false;
unsigned long lastMqttReconnect = 0;

// ═══ STRING IP HELPER (Ameba IPAddress has no toString) ═══
String ipToString(IPAddress ip) {
    char buf[20];
    snprintf(buf, sizeof(buf), "%d.%d.%d.%d", ip[0], ip[1], ip[2], ip[3]);
    return String(buf);
}

// ═══ WIFI ═══
bool nirvana_wifi_connect() {
    // Check if AP mode requested + existing WiFi failed
    if (nvCfg.wifiAPMode && WiFi.status() != WL_CONNECTED) {
        // Start Soft AP: "Nirvana-AMB82" — connect phone/PC to 192.168.4.1
        WiFi.mode(WIFI_AP_STA);  // Simultaneous AP + STA
        WiFi.softAP("Nirvana-AMB82", "nirvana123");
        Serial.println("[WIFI] AP mode: Nirvana-AMB82 @ 192.168.4.1");
        Serial.println("[WIFI] Connect your phone/PC to this network");
    }

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
        Serial.println();
        Serial.println("[WIFI] Connected!");
        Serial.print("[WIFI] IP: ");
        Serial.println(ipToString(WiFi.localIP()));
        Serial.print("[WIFI] RSSI: ");
        Serial.println(WiFi.RSSI());
        return true;
    }
    Serial.println();
    Serial.println("[WIFI] FAILED!");
    return false;
}

// ═══ MQTT CALLBACK ═══
void nirvana_mqtt_callback(char* topic, byte* payload, unsigned int length) {
    char json[1024] = {0};
    unsigned int copyLen = length < 1023 ? length : 1023;
    memcpy(json, payload, copyLen);

    JsonDocument doc;
    DeserializationError err = deserializeJson(doc, json);
    if (err) {
        Serial.print("[MQTT] JSON error: ");
        Serial.println(err.c_str());
        return;
    }

    const char* type = doc["type"] | "";
    Serial.print("[MQTT] RX: ");
    Serial.println(type);

    if (strcmp(type, "hello") == 0) {
        const char* sess = doc["session_id"] | "";
        mqttSessionId = String(sess);
        Serial.print("[MQTT] Session: ");
        Serial.println(mqttSessionId);

        JsonObject udpObj = doc["udp"];
        if (!udpObj.isNull()) {
            const char* udpServer = udpObj["server"] | "";
            int udpPort = udpObj["port"] | 8888;
            Serial.print("[UDP] Endpoint: ");
            Serial.print(udpServer);
            Serial.print(":");
            Serial.println(udpPort);
        }

        JsonObject audioObj = doc["audio_params"];
        if (!audioObj.isNull()) {
            int sr = audioObj["sample_rate"] | 24000;
            Serial.print("[AUDIO] Server rate: ");
            Serial.print(sr);
            Serial.println(" Hz");
        }
    }
    else if (strcmp(type, "tts") == 0) {
        const char* state = doc["state"] | "";
        Serial.print("[TTS] ");
        Serial.println(state);
    }
    else if (strcmp(type, "stt") == 0) {
        const char* text = doc["text"] | "";
        Serial.print("[STT] ");
        Serial.println(text);
    }
    else if (strcmp(type, "llm") == 0) {
        const char* emotion = doc["emotion"] | "neutral";
        Serial.print("[LLM] Emotion: ");
        Serial.println(emotion);
    }
    else if (strcmp(type, "mcp") == 0) {
        JsonObject mcpPayload = doc["payload"];
        Serial.print("[MCP] RX");
        String fleetTopic = String(MQTT_TOPIC_PREFIX) + "/mcp";
        char mcpBuf[256];
        serializeJson(mcpPayload, mcpBuf, sizeof(mcpBuf));
        mqtt.publish(fleetTopic.c_str(), mcpBuf);
    }
    else if (strcmp(type, "system") == 0) {
        const char* cmd = doc["command"] | "";
        Serial.print("[SYSTEM] ");
        Serial.println(cmd);
    }
    else if (strcmp(type, "alert") == 0) {
        const char* status = doc["status"] | "";
        const char* message = doc["message"] | "";
        Serial.print("[ALERT] ");
        Serial.print(status);
        Serial.print(": ");
        Serial.println(message);
    }
    else if (strcmp(type, "goodbye") == 0) {
        Serial.println("[MQTT] Server goodbye");
        mqttSessionId = "";
    }
    // ── Remote control commands ──
    else if (strcmp(type, "command") == 0) {
        const char* cmd = doc["cmd"] | "";
        if (cmd[0]) {
            extern bool nirvana_control_exec(const char* cmd);
            nirvana_control_exec(cmd);
        }
    }
}

// ═══ MQTT CONNECT ═══
bool nirvana_mqtt_connect() {
    if (mqtt.connected()) return true;

    Serial.print("[MQTT] Connecting to ");
    Serial.print(MQTT_HOST);
    Serial.print(":");
    Serial.println(MQTT_PORT);

    mqtt.setServer(MQTT_HOST, MQTT_PORT);
    mqtt.setCallback(nirvana_mqtt_callback);
    mqtt.setKeepAlive(MQTT_KEEPALIVE);

    String clientId = String(NIRVANA_DEVICE_ID) + "-" + String(rand() % 9000 + 1000);
    if (mqtt.connect(clientId.c_str())) {
        Serial.println("[MQTT] Connected!");

        String topic = String(MQTT_TOPIC_PREFIX) + "/" + NIRVANA_DEVICE_ID;
        mqtt.subscribe(topic.c_str());
        Serial.print("[MQTT] Subscribed: ");
        Serial.println(topic);

        // Subscribe to fleet command topic for remote control
        String cmdTopic = String(MQTT_TOPIC_PREFIX) + "/amb82/command";
        mqtt.subscribe(cmdTopic.c_str());

        // Xiaozhi hello
        JsonDocument hello;
        hello["type"] = "hello";
        hello["version"] = 3;
        hello["transport"] = "udp";
        JsonObject feat = hello["features"].to<JsonObject>();
        feat["mcp"] = true;
        JsonObject af = hello["audio_params"].to<JsonObject>();
        af["format"] = "opus";
        af["sample_rate"] = 16000;
        af["channels"] = 1;
        af["frame_duration"] = 60;

        char buf[512];
        serializeJson(hello, buf, sizeof(buf));
        mqtt.publish(topic.c_str(), buf);
        Serial.print("[MQTT] Hello sent: ");
        Serial.println(buf);

        mqttConnected = true;
        return true;
    }

    Serial.print("[MQTT] Failed, rc=");
    Serial.println(mqtt.state());
    return false;
}

// ═══ FLEET STATUS ═══
void nirvana_publish_status() {
    if (!mqtt.connected()) return;

    String topic = String(MQTT_TOPIC_PREFIX) + "/status";
    JsonDocument doc;
    doc["device"] = NIRVANA_DEVICE_ID;
    doc["fleet"] = NIRVANA_FLEET_NAME;
    doc["version"] = NIRVANA_VERSION;
    doc["uptime"] = millis() / 1000;
    doc["wifi_rssi"] = WiFi.RSSI();
    doc["ip"] = ipToString(WiFi.localIP());

    char buf[256];
    serializeJson(doc, buf, sizeof(buf));
    mqtt.publish(topic.c_str(), buf);
}

// ═══ LOOP ═══
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

#endif
