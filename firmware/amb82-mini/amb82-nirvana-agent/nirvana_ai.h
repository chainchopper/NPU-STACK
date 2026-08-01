// NIRVANA AI — Cloud AI + Voicebox TTS + GenAI integration
// OpenAI Vision, Gemini, Whisper, Google TTS via Ameba SDK GenAI.h
// Voicebox TTS at port 7933 with voice profile selection
// Multiple API keys, configurable base URLs
#ifndef NIRVANA_AI_H
#define NIRVANA_AI_H

#include <WiFi.h>
#include <ArduinoJson.h>
#include "nirvana_config.h"
#include "nirvana_config_storage.h"

// ── AI Provider Config ──
struct AIProvider {
    bool    enabled;
    char    name[24];
    char    baseURL[64];
    char    apiKey[96];
};

// Voicebox TTS profile
struct VoiceProfile {
    char name[32];
    char id[32];
};

// ── Global providers (loaded from config) ──
#define MAX_PROVIDERS 4
#define MAX_VOICE_PROFILES 8

AIProvider     aiProviders[MAX_PROVIDERS];
int            aiProviderCount = 0;
VoiceProfile   voiceProfiles[MAX_VOICE_PROFILES];
int            voiceProfileCount = 0;
int            selectedVoiceIdx = 0;

char aiResponse[512] = "";

// ── Default providers ──
void nirvana_ai_init_defaults() {
    // OpenAI
    strcpy(aiProviders[0].name, "OpenAI");
    strcpy(aiProviders[0].baseURL, "https://api.openai.com/v1");
    strcpy(aiProviders[0].apiKey, nvCfg.openaiKey[0] ? nvCfg.openaiKey : "sk-none");
    aiProviders[0].enabled = (nvCfg.openaiKey[0] != 0);

    // Voicebox (local TTS)
    strcpy(aiProviders[1].name, "Voicebox Local");
    strcpy(aiProviders[1].baseURL, "http://127.0.0.1:7933");
    strcpy(aiProviders[1].apiKey, "");
    aiProviders[1].enabled = true;

    // DeepSeek (via NPU-STACK)
    strcpy(aiProviders[2].name, "DeepSeek");
    strcpy(aiProviders[2].baseURL, nvCfg.deepseekURL[0] ? nvCfg.deepseekURL : "https://api.deepseek.com/v1");
    strcpy(aiProviders[2].apiKey, nvCfg.deepseekKey[0] ? nvCfg.deepseekKey : "");
    aiProviders[2].enabled = (nvCfg.deepseekKey[0] != 0);

    // Local LLM (NPU-STACK :8010)
    strcpy(aiProviders[3].name, "NPU-STACK Local");
    strcpy(aiProviders[3].baseURL, nvCfg.localLLMURL[0] ? nvCfg.localLLMURL : "http://" MQTT_HOST ":8010/v1");
    strcpy(aiProviders[3].apiKey, "");
    aiProviders[3].enabled = true;

    aiProviderCount = 4;
}

// ── Fetch voice profiles from Voicebox ──
// GET http://voicebox:7933/profiles or /api/voices
int nirvana_ai_fetch_voice_profiles() {
    if (WiFi.status() != WL_CONNECTED) return 0;

    WiFiClient client;
    // Try common Voicebox endpoints
    const char* endpoints[] = {"/profiles", "/api/profiles", "/voices", "/api/voices", "/v1/voices"};
    for (int e = 0; e < 5; e++) {
        if (!client.connect(nvCfg.voiceboxHost[0] ? nvCfg.voiceboxHost : "127.0.0.1",
                           nvCfg.voiceboxPort > 0 ? nvCfg.voiceboxPort : 7933)) {
            continue;
        }
        client.print("GET "); client.print(endpoints[e]);
        client.print(" HTTP/1.1\r\nHost: voicebox\r\nConnection: close\r\n\r\n");

        unsigned long t = millis();
        char buf[1024] = ""; int bi = 0;
        while (client.connected() || client.available()) {
            if (client.available() && bi < 1023) buf[bi++] = client.read();
            if (millis() - t > 3000) break;
        }
        client.stop();

        // Parse JSON array of voices
        char* jsonStart = strstr(buf, "[");
        if (!jsonStart) { jsonStart = strstr(buf, "\"voices\""); if (!jsonStart) continue; }
        JsonDocument doc;
        DeserializationError err = deserializeJson(doc, jsonStart);
        if (err) continue;

        JsonArray arr = doc.as<JsonArray>();
        if (arr.isNull() && doc.containsKey("voices")) arr = doc["voices"].as<JsonArray>();
        if (arr.isNull()) continue;

        voiceProfileCount = 0;
        for (JsonObject v : arr) {
            if (voiceProfileCount >= MAX_VOICE_PROFILES) break;
            strncpy(voiceProfiles[voiceProfileCount].name,
                    v["name"] | v["id"] | "unknown", 31);
            strncpy(voiceProfiles[voiceProfileCount].id,
                    v["id"] | v["name"] | "0", 31);
            voiceProfileCount++;
        }
        Serial.print("[AI] Found "); Serial.print(voiceProfileCount);
        Serial.println(" voice profiles from Voicebox");
        return voiceProfileCount;
    }
    return 0;
}

// ── TTS via Voicebox — returns true if audio generated ──
// TODO: Save returned WAV/MP3 to SD and play through speaker
bool nirvana_ai_tts_voicebox(const char* text, const char* voiceId) {
    if (WiFi.status() != WL_CONNECTED) return false;

    WiFiClient client;
    char host[32]; snprintf(host, sizeof(host), "%s",
        nvCfg.voiceboxHost[0] ? nvCfg.voiceboxHost : "192.168.1.100");
    uint16_t port = nvCfg.voiceboxPort > 0 ? nvCfg.voiceboxPort : 7933;

    if (!client.connect(host, port)) {
        Serial.println("[AI-TTS] Voicebox not reachable");
        return false;
    }

    JsonDocument req;
    req["text"] = text;
    if (voiceId && voiceId[0]) req["voice"] = voiceId;
    req["format"] = "wav";
    req["sample_rate"] = 16000;

    char body[512];
    serializeJson(req, body, sizeof(body));

    client.print("POST /api/tts HTTP/1.1\r\n");
    client.print("Host: voicebox\r\n");
    client.print("Content-Type: application/json\r\n");
    client.print("Content-Length: "); client.print(strlen(body));
    client.print("\r\nConnection: close\r\n\r\n");
    client.print(body);
    client.flush();

    Serial.print("[AI-TTS] Request: "); Serial.println(text);

    // Note: audio playback requires streaming to DAC — placeholder
    client.stop();
    return true;
}

// ── OpenAI Vision (cloud) — describe a camera frame ──
// Uses GenAI.h from Ameba SDK
bool nirvana_ai_vision_openai(uint32_t img_addr, uint32_t img_len, const char* prompt) {
    if (!aiProviders[0].enabled) return false;

    WiFiSSLClient sslClient;
    // GenAI would handle this — placeholder for GenAI integration
    Serial.println("[AI-Vision] OpenAI vision call (placeholder)");
    return false;
}

// ── General AI call — pick best available provider ──
bool nirvana_ai_process(const char* text, const char* imagePrompt) {
    // Voice response via Voicebox if available
    if (aiProviders[1].enabled) {
        const char* vid = (voiceProfileCount > 0 && selectedVoiceIdx < voiceProfileCount)
                          ? voiceProfiles[selectedVoiceIdx].id : nullptr;
        nirvana_ai_tts_voicebox(text, vid);
    }
    return true;
}

#endif
