// NIRVANA CONFIG STORAGE — Atomic JSON config to SD card
// Shadow-write pattern: write .tmp → sync → rename to .json
// Survives power loss — old config never corrupted mid-write
//
// Stored at /config.json on SD card
// Settings: brightness, volume, turbo, api_token
#ifndef NIRVANA_CONFIG_STORAGE_H
#define NIRVANA_CONFIG_STORAGE_H

#include "ff.h"
#include "nirvana_config.h"

#define CFG_PATH        "/config.json"
#define CFG_TMP_PATH    "/config.tmp"
#define CFG_BUF_SIZE    1024

// ── Live settings struct (in RAM, backed by SD) ──
// Keys pre-populated from NPU-STACK env at compile time.
// Override by editing /config.json on SD card.
typedef struct {
    uint8_t brightness;     // 0-100, PWM duty
    uint8_t volume;         // 0-100, speaker gain
    bool    turbo;          // CPU profile
    uint8_t voiceProfile;   // Voicebox voice index
    uint8_t aiProvider;     // Selected AI provider (0=OpenAI,1=DeepSeek,2=LMStudio,3=NGC)
    // ── Multi-provider API keys + URLs ──
    char    openaiKey[128];
    char    deepseekKey[128];
    char    deepseekURL[64];
    char    geminiKey[128];
    char    lmstudioKey[128];
    char    lmstudioURL[64];
    char    ngcKey[128];
    char    hfToken[128];       // HuggingFace for model downloads
    char    elevenlabsKey[128]; // ElevenLabs TTS
    char    voiceboxHost[32];
    uint16_t voiceboxPort;
    bool    wifiAPMode;
} NirvanaSettings;

NirvanaSettings nvCfg = {
    75,             // brightness
    70,             // volume
    false,          // turbo
    0,              // voiceProfile
    1,              // aiProvider: 0=OpenAI, 1=DeepSeek, 2=LMStudio, 3=NGC
    // KEYS LOADED FROM /config.json ON SD CARD — defaults are empty
    "",             // openaiKey
    "",             // deepseekKey
    "https://api.deepseek.com/v1",   // deepseekURL
    "",             // geminiKey
    "",             // lmstudioKey
    "http://100.100.2.93:443/v1",    // lmstudioURL (tailnet)
    "",             // ngcKey
    "",             // hfToken
    "",             // elevenlabsKey
    "192.168.1.227", // voiceboxHost (change to your LAN IP for AMB82)
    7933,           // voiceboxPort
    true,           // wifiAPMode
};

bool cfgLoaded = false;

// ── Write JSON string to file (FatFs) ──
static bool _cfg_write_file(const char* path, const char* json) {
    FIL fp;
    if (f_open(&fp, path, FA_WRITE | FA_CREATE_ALWAYS) != FR_OK) return false;
    UINT bw;
    size_t len = strlen(json);
    f_write(&fp, json, len, &bw);
    f_sync(&fp);
    f_close(&fp);
    return (bw == len);
}

// ── Read entire file into buffer ──
static bool _cfg_read_file(const char* path, char* buf, size_t maxLen) {
    FIL fp;
    if (f_open(&fp, path, FA_READ) != FR_OK) return false;
    UINT br;
    f_read(&fp, buf, maxLen - 1, &br);
    buf[br] = 0;
    f_close(&fp);
    return (br > 0);
}

// ── Serialize settings to JSON string ──
void _cfg_serialize(char* buf, size_t maxLen) {
    snprintf(buf, maxLen,
        "{"
        "\"brightness\":%u,\"volume\":%u,\"turbo\":%s,"
        "\"voice_profile\":%u,\"ai_provider\":%u,"
        "\"openai_key\":\"%s\",\"deepseek_key\":\"%s\","
        "\"deepseek_url\":\"%s\",\"gemini_key\":\"%s\","
        "\"lmstudio_key\":\"%s\",\"lmstudio_url\":\"%s\","
        "\"ngc_key\":\"%s\",\"hf_token\":\"%s\","
        "\"elevenlabs_key\":\"%s\","
        "\"voicebox_host\":\"%s\",\"voicebox_port\":%u,"
        "\"wifi_ap_mode\":%s}",
        nvCfg.brightness, nvCfg.volume, nvCfg.turbo?"true":"false",
        nvCfg.voiceProfile, nvCfg.aiProvider,
        nvCfg.openaiKey, nvCfg.deepseekKey,
        nvCfg.deepseekURL, nvCfg.geminiKey,
        nvCfg.lmstudioKey, nvCfg.lmstudioURL,
        nvCfg.ngcKey, nvCfg.hfToken,
        nvCfg.elevenlabsKey,
        nvCfg.voiceboxHost, nvCfg.voiceboxPort,
        nvCfg.wifiAPMode?"true":"false");
}

// ── Simple JSON int parser: "key": 42  → extracts 42 ──
static int _cfg_parse_int(const char* json, const char* key, int defVal) {
    const char* p = strstr(json, key);
    if (!p) return defVal;
    p = strchr(p, ':');
    if (!p) return defVal;
    p++; while (*p == ' ' || *p == '\t') p++;
    return atoi(p);
}

// ── Simple JSON bool parser ──
static bool _cfg_parse_bool(const char* json, const char* key, bool defVal) {
    const char* p = strstr(json, key);
    if (!p) return defVal;
    p = strchr(p, ':');
    if (!p) return defVal;
    p++; while (*p == ' ' || *p == '\t') p++;
    return (strncmp(p, "true", 4) == 0);
}

// ── Simple JSON string parser: "key": "value" ──
static void _cfg_parse_str(const char* json, const char* key,
                           char* out, size_t maxLen, const char* defVal) {
    const char* p = strstr(json, key);
    if (!p) { strncpy(out, defVal, maxLen-1); return; }
    p = strchr(p, ':');
    if (!p) { strncpy(out, defVal, maxLen-1); return; }
    p = strchr(p, '"');
    if (!p) { strncpy(out, defVal, maxLen-1); return; }
    p++; // Skip opening quote
    size_t i = 0;
    while (*p && *p != '"' && i < maxLen-1) { out[i++] = *p++; }
    out[i] = 0;
}

// ── SAVE: atomic shadow-write ──
bool nirvana_cfg_save() {
    if (!sdReady) {
        Serial.println("[CFG] No SD card — save skipped");
        return false;
    }

    char json[CFG_BUF_SIZE];
    _cfg_serialize(json, sizeof(json));

    // 1. Write to .tmp
    if (!_cfg_write_file(CFG_TMP_PATH, json)) {
        Serial.println("[CFG] Write .tmp failed");
        return false;
    }

    // 2. Atomic rename: delete old, rename tmp → json
    f_unlink(CFG_PATH);
    if (f_rename(CFG_TMP_PATH, CFG_PATH) != FR_OK) {
        Serial.println("[CFG] Atomic rename failed");
        f_unlink(CFG_TMP_PATH); // Clean up
        return false;
    }

    Serial.println("[CFG] Saved to /config.json");
    return true;
}

// ── LOAD: read from SD at boot ──
bool nirvana_cfg_load() {
    if (!sdReady) {
        Serial.println("[CFG] No SD — using defaults");
        cfgLoaded = true;
        return false;
    }

    char json[CFG_BUF_SIZE];
    if (!_cfg_read_file(CFG_PATH, json, sizeof(json))) {
        Serial.println("[CFG] No config file — using defaults");
        nirvana_cfg_save(); // Create initial config
        cfgLoaded = true;
        return false;
    }

    nvCfg.brightness = _cfg_parse_int(json, "\"brightness\"", 75);
    nvCfg.volume     = _cfg_parse_int(json, "\"volume\"", 70);
    nvCfg.turbo      = _cfg_parse_bool(json, "\"turbo\"", false);
    nvCfg.voiceProfile = _cfg_parse_int(json, "\"voice_profile\"", 0);
    nvCfg.aiProvider   = _cfg_parse_int(json, "\"ai_provider\"", 1);
    nvCfg.voiceboxPort = _cfg_parse_int(json, "\"voicebox_port\"", 7933);
    nvCfg.wifiAPMode   = _cfg_parse_bool(json, "\"wifi_ap_mode\"", true);
    _cfg_parse_str(json, "\"openai_key\"",     nvCfg.openaiKey, 128, "");
    _cfg_parse_str(json, "\"deepseek_key\"",   nvCfg.deepseekKey, 128, "");
    _cfg_parse_str(json, "\"deepseek_url\"",   nvCfg.deepseekURL, 64, "https://api.deepseek.com/v1");
    _cfg_parse_str(json, "\"gemini_key\"",     nvCfg.geminiKey, 128, "");
    _cfg_parse_str(json, "\"lmstudio_key\"",   nvCfg.lmstudioKey, 128, "");
    _cfg_parse_str(json, "\"lmstudio_url\"",   nvCfg.lmstudioURL, 64, "");
    _cfg_parse_str(json, "\"ngc_key\"",        nvCfg.ngcKey, 128, "");
    _cfg_parse_str(json, "\"hf_token\"",       nvCfg.hfToken, 128, "");
    _cfg_parse_str(json, "\"elevenlabs_key\"", nvCfg.elevenlabsKey, 128, "");
    _cfg_parse_str(json, "\"voicebox_host\"",  nvCfg.voiceboxHost, 32, "192.168.1.227");

    cfgLoaded = true;
    Serial.println("[CFG] Loaded from /config.json");
    Serial.print("  Brightness: "); Serial.print(nvCfg.brightness); Serial.println("%");
    Serial.print("  Volume: ");     Serial.print(nvCfg.volume);     Serial.println("%");
    Serial.print("  Turbo: ");      Serial.println(nvCfg.turbo ? "ON" : "OFF");
    return true;
}

// ── Apply saved brightness to backlight pin ──
void nirvana_cfg_apply_brightness() {
    // TFT_BL is D5 (PF_12). PWM via analogWrite would be ideal
    // but Ameba SDK analogWrite may conflict. Simple ON/OFF works.
    if (nvCfg.brightness > 0) {
        digitalWrite(TFT_BL, HIGH);
    } else {
        digitalWrite(TFT_BL, LOW);
    }
    // TODO: Use analogWrite(TFT_BL, map(nvCfg.brightness, 0, 100, 0, 255))
    // when PWM is confirmed safe on this pin
}

#endif
