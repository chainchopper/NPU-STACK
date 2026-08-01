// NIRVANA AI — Multi-provider LLM + Vision + TTS
// GenAI.h (Ameba SDK): real base64 JPEG → OpenAI Vision / Gemini / Whisper
// Chat: OAI-compatible HTTP POST → DeepSeek/LMStudio/OpenAI/NGC
// Voicebox TTS via tailnet subnet router (NPU-STACK backend proxy)
#ifndef NIRVANA_AI_H
#define NIRVANA_AI_H

#include <WiFi.h>
#include <WiFiSSLClient.h>
#include <ArduinoJson.h>
#include "GenAI.h"
#include "nirvana_config.h"
#include "nirvana_config_storage.h"

#define PROVIDER_OPENAI     0
#define PROVIDER_DEEPSEEK   1
#define PROVIDER_LMSTUDIO   2
#define PROVIDER_NGC        3
#define PROVIDER_GEMINI     4
#define PROVIDER_ELEVENLABS 5
#define PROVIDER_VOICEBOX   6

#define MAX_VOICE_PROFILES   8
struct VP { char name[32]; char id[32]; };
VP voiceProfiles[MAX_VOICE_PROFILES];
int voiceProfileCount = 0;
char aiResponse[512] = "";

// ── Init providers at boot (reads nvCfg keys from SD config) ──
void nirvana_ai_init() {
    Serial.println("[AI] Providers init");
    Serial.print("  Default: ");
    Serial.print((nvCfg.aiProvider==0)?"OpenAI":(nvCfg.aiProvider==1)?"DeepSeek":
                 (nvCfg.aiProvider==2)?"LMStudio":"NGC");
    Serial.print("  Voicebox: "); Serial.println(nvCfg.voiceboxHost);
}

// ── Get active provider key from nvCfg ──
static const char* _key(int p) {
    switch (p) {
    case 0: return nvCfg.openaiKey;
    case 1: return nvCfg.deepseekKey;
    case 2: return nvCfg.lmstudioKey;
    case 3: return nvCfg.ngcKey;
    case 4: return nvCfg.geminiKey;
    case 5: return nvCfg.elevenlabsKey;
    default: return "";
    }
}

bool nirvana_ai_ready(int p) {
    if (p == 6 && nvCfg.voiceboxHost[0]) return true;
    const char* k = _key(p);
    return k && k[0];
}

// ── OpenAI-compatible chat (HTTP POST to /v1/chat/completions) ──
// Works with: OpenAI, DeepSeek, LM Studio, NGC, any OAI-compatible endpoint
bool nirvana_ai_chat(int provider, const char* systemPrompt, const char* userMsg) {
    if (!nirvana_ai_ready(provider)) return false;

    // Determine host and path
    const char* base = (provider == 1) ? nvCfg.deepseekURL :
                       (provider == 2) ? nvCfg.lmstudioURL :
                       (provider == 3) ? "https://integrate.api.nvidia.com/v1" :
                       "https://api.openai.com/v1";
    const char* hostOnly = strstr(base, "://") ? strstr(base, "://") + 3 : base;
    // Extract just hostname (before / or :)
    char host[64]; const char* slash = strchr(hostOnly, '/');
    const char* colon = strchr(hostOnly, ':');
    int hostLen = 0;
    if (slash && colon) hostLen = (slash < colon ? slash : colon) - hostOnly;
    else if (slash) hostLen = slash - hostOnly;
    else if (colon) hostLen = colon - hostOnly;
    else hostLen = strlen(hostOnly);
    memcpy(host, hostOnly, hostLen); host[hostLen] = 0;
    uint16_t port = 443;
    if (colon && (!slash || colon < slash)) port = atoi(colon + 1);

    Serial.print("[AI] "); Serial.print(host); Serial.print(":"); Serial.println(port);

    WiFiClient client;
    bool useSSL = (strncmp(base, "https", 5) == 0);
    WiFiSSLClient ssl;

    if (useSSL) { if (!ssl.connect(host, port)) { Serial.println("[AI] SSL fail"); return false; } }
    else        { if (!client.connect(host, port)) { Serial.println("[AI] TCP fail"); return false; } }

    // Determine model name
    const char* model = (provider == 1) ? "deepseek-chat" : "gpt-4o-mini";

    // Build JSON body
    JsonDocument body;
    body["model"] = model;
    body["max_tokens"] = 256;
    body["temperature"] = 0.7;
    JsonArray msgs = body["messages"].to<JsonArray>();
    JsonObject sys = msgs.add<JsonObject>();
    sys["role"] = "system"; sys["content"] = systemPrompt;
    JsonObject usr = msgs.add<JsonObject>();
    usr["role"] = "user"; usr["content"] = userMsg;
    char json[1024]; serializeJson(body, json, sizeof(json));

    // Send HTTP request
    if (useSSL) {
        ssl.print("POST /v1/chat/completions HTTP/1.1\r\n");
        ssl.print("Host: "); ssl.print(host); ssl.print("\r\n");
        ssl.print("Content-Type: application/json\r\n");
        ssl.print("Authorization: Bearer "); ssl.print(_key(provider)); ssl.print("\r\n");
        ssl.print("Content-Length: "); ssl.print(strlen(json));
        ssl.print("\r\nConnection: close\r\n\r\n");
        ssl.print(json); ssl.flush();
    } else {
        client.print("POST /v1/chat/completions HTTP/1.1\r\n");
        client.print("Host: "); client.print(host); client.print("\r\n");
        client.print("Content-Type: application/json\r\n");
        client.print("Authorization: Bearer "); client.print(_key(provider)); client.print("\r\n");
        client.print("Content-Length: "); client.print(strlen(json));
        client.print("\r\nConnection: close\r\n\r\n");
        client.print(json); client.flush();
    }

    // Read response
    unsigned long t = millis(); int bi = 0;
    while (bi < 511) {
        if (useSSL) { if (!ssl.connected() && !ssl.available()) break; if (ssl.available()) aiResponse[bi++] = ssl.read(); }
        else        { if (!client.connected() && !client.available()) break; if (client.available()) aiResponse[bi++] = client.read(); }
        if (millis() - t > 12000) break;
    }
    aiResponse[bi] = 0;
    if (useSSL) ssl.stop(); else client.stop();

    // Extract content from JSON
    const char* c = strstr(aiResponse, "\"content\":\"");
    if (!c) c = strstr(aiResponse, "\"content\": \"");
    if (c) {
        c = strchr(c, ':') + 1;
        while (*c == ' ' || *c == '"') c++;
        char* end = strchr((char*)c, '"');
        if (end) *end = 0;
        snprintf(aiResponse, sizeof(aiResponse), "%s", c);
    }

    Serial.print("[AI] "); Serial.println(aiResponse);
    return true;
}

// ── TTS via Voicebox (through backend proxy for tailnet) ──
bool nirvana_ai_tts(const char* text) {
    if (WiFi.status() != WL_CONNECTED) return false;
    WiFiClient c;

    // Try direct first, then backend proxy
    bool direct = (nvCfg.voiceboxHost[0] != 0);
    if (direct) {
        if (!c.connect(nvCfg.voiceboxHost, nvCfg.voiceboxPort)) direct = false;
    }
    if (!direct) {
        if (!c.connect(MQTT_HOST, 8010)) { Serial.println("[TTS] unreachable"); return false; }
    }

    JsonDocument req;
    req["text"] = text;
    if (voiceProfileCount && nvCfg.voiceProfile < voiceProfileCount)
        req["voice"] = voiceProfiles[nvCfg.voiceProfile].id;
    req["format"] = "wav";
    req["sample_rate"] = 16000;
    char body[512]; serializeJson(req, body, sizeof(body));

    c.print(direct ? "POST /api/tts HTTP/1.1\r\n" : "POST /api/nirvana/tts HTTP/1.1\r\n");
    c.print(direct ? "Host: voicebox\r\n" : "Host: npu-stack\r\n");
    c.print("Content-Type: application/json\r\n");
    c.print("Content-Length: "); c.print(strlen(body));
    c.print("\r\nConnection: close\r\n\r\n");
    c.print(body); c.flush();
    c.stop();
    Serial.print("[TTS] "); Serial.println(text);
    return true;
}

// ── Fetch voice profiles from Voicebox (direct or via backend) ──
int nirvana_ai_fetch_voices() {
    if (WiFi.status() != WL_CONNECTED) return 0;

    WiFiClient c;
    const char* host = nvCfg.voiceboxHost[0] ? nvCfg.voiceboxHost : MQTT_HOST;
    uint16_t port = nvCfg.voiceboxHost[0] ? nvCfg.voiceboxPort : 8010;
    const char* path = nvCfg.voiceboxHost[0] ? "/api/profiles" : "/api/nirvana/tts/profiles";

    if (!c.connect(host, port)) return 0;

    c.print("GET "); c.print(path);
    c.print(" HTTP/1.1\r\nHost: voicebox\r\nConnection: close\r\n\r\n");

    unsigned long t = millis(); char buf[2048] = ""; int bi = 0;
    while ((c.connected() || c.available()) && bi < 2047 && millis() - t < 4000)
        if (c.available()) buf[bi++] = c.read();
    buf[bi] = 0; c.stop();

    char* js = strstr(buf, "[");
    if (!js) js = strstr(buf, "\"voices\"");
    if (!js) return 0;

    JsonDocument doc;
    if (deserializeJson(doc, js)) return 0;
    JsonArray arr = doc.as<JsonArray>();
    if (arr.isNull() && doc.containsKey("voices")) arr = doc["voices"];

    voiceProfileCount = 0;
    for (JsonObject v : arr) {
        if (voiceProfileCount >= MAX_VOICE_PROFILES) break;
        strncpy(voiceProfiles[voiceProfileCount].name, v["name"] | v["id"] | "v", 31);
        strncpy(voiceProfiles[voiceProfileCount].id,   v["id"] | v["name"] | "0", 31);
        voiceProfileCount++;
    }
    Serial.print("[AI] Voices: "); Serial.println(voiceProfileCount);
    return voiceProfileCount;
}

// ── Quick ask: chat with default provider ──
bool nirvana_ai_ask(const char* prompt) {
    return nirvana_ai_chat(nvCfg.aiProvider,
        "You are Nirvana, a helpful AI. Reply in 1-2 short sentences.", prompt);
}

// ══════════════════════════════════════════
//  GenAI Vision — real base64 JPEG → cloud
// ══════════════════════════════════════════

GenAI _genai;  // Single global instance

// ── Describe camera frame via OpenAI Vision ──
bool nirvana_ai_vision_openai(uint32_t jpgAddr, uint32_t jpgLen, const char* prompt) {
    if (!nvCfg.openaiKey[0]) { Serial.println("[AI-V] No OpenAI key"); return false; }
    WiFiSSLClient ssl;
    String resp = _genai.openaivision(nvCfg.openaiKey, "gpt-4o-mini", prompt, jpgAddr, jpgLen, ssl);
    snprintf(aiResponse, sizeof(aiResponse), "%s", resp.c_str());
    Serial.print("[AI-V] OpenAI: "); Serial.println(aiResponse);
    return true;
}

// ── Describe camera frame via Gemini Vision ──
bool nirvana_ai_vision_gemini(uint32_t jpgAddr, uint32_t jpgLen, const char* prompt) {
    if (!nvCfg.geminiKey[0]) { Serial.println("[AI-V] No Gemini key"); return false; }
    WiFiSSLClient ssl;
    String resp = _genai.geminivision(nvCfg.geminiKey, "gemini-2.0-flash", prompt, jpgAddr, jpgLen, ssl);
    snprintf(aiResponse, sizeof(aiResponse), "%s", resp.c_str());
    Serial.print("[AI-V] Gemini: "); Serial.println(aiResponse);
    return true;
}

// ── Transcribe WAV file via Whisper ──
// filepath: path on SD card (e.g., "/recordings/memo_12345.wav")
bool nirvana_ai_transcribe(const char* filepath) {
    if (!nvCfg.openaiKey[0]) { Serial.println("[AI-W] No OpenAI key"); return false; }
    WiFiSSLClient ssl;
    String resp = _genai.whisperaudio(nvCfg.openaiKey, "api.openai.com",
                                       "/v1/audio/transcriptions", "whisper-1",
                                       (char*)filepath, ssl);
    snprintf(aiResponse, sizeof(aiResponse), "%s", resp.c_str());
    Serial.print("[AI-W] "); Serial.println(aiResponse);
    return true;
}

// ── TTS via Google Cloud TTS (saves MP3 to SD) ──
bool nirvana_ai_tts_google(const char* text, const char* lang) {
    _genai.googletts("/tts_output.mp3", (char*)text, (char*)lang);
    Serial.println("[AI-TTS-Google] Saved to /tts_output.mp3");
    return true;
}

#endif
