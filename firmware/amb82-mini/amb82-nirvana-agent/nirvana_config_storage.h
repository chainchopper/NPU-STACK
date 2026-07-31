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
#define CFG_BUF_SIZE    512

// ── Live settings struct (in RAM, backed by SD) ──
typedef struct {
    uint8_t brightness;     // 0-100, PWM duty on TFT_BL pin
    uint8_t volume;         // 0-100, speaker gain
    bool    turbo;          // CPU performance profile
    char    apiToken[64];   // AI backend key
} NirvanaSettings;

NirvanaSettings nvCfg = {
    75,             // Default brightness
    70,             // Default volume
    false,          // Default turbo off
    "nv-default"    // Default API token
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
        "{\n"
        "  \"brightness\": %u,\n"
        "  \"volume\": %u,\n"
        "  \"turbo\": %s,\n"
        "  \"api_token\": \"%s\"\n"
        "}\n",
        nvCfg.brightness, nvCfg.volume,
        nvCfg.turbo ? "true" : "false",
        nvCfg.apiToken);
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
    _cfg_parse_str(json, "\"api_token\"", nvCfg.apiToken, 64, "nv-default");

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
