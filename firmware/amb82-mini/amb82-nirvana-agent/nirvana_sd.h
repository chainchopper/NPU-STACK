#ifndef NIRVANA_SD_H
#define NIRVANA_SD_H

#include <SD.h>
#include "nirvana_config.h"

#if FEATURE_SD_CARD
bool sdReady = false;

// ═══════════════ INIT ═══════════════
bool nirvana_sd_init() {
    if (!SD.begin(SD_CS)) {
        Serial.println("[SD] Card mount FAILED");
        return false;
    }

    uint8_t cardType = SD.cardType();
    if (cardType == CARD_NONE) {
        Serial.println("[SD] No card detected");
        return false;
    }

    Serial.print("[SD] Card type: ");
    if (cardType == CARD_MMC) Serial.println("MMC");
    else if (cardType == CARD_SD) Serial.println("SDSC");
    else if (cardType == CARD_SDHC) Serial.println("SDHC");

    uint64_t cardSize = SD.cardSize() / (1024 * 1024);
    Serial.printf("[SD] Size: %llu MB\n", cardSize);

    // Create directory structure
    nirvana_sd_create_dirs();

    sdReady = true;
    return true;
}

// ═══════════════ CREATE DIRECTORY STRUCTURE ═══════════════
void nirvana_sd_create_dirs() {
    const char* dirs[] = {
        "/apps",      // Arduino sketch apps
        "/models",    // NN model files (.nb)
        "/assets",    // Fonts, images, sounds
        "/logs",      // Agent logs
        "/config",    // Configuration files
        "/cache"      // Temporary data
    };
    for (int i = 0; i < 6; i++) {
        if (!SD.exists(dirs[i])) {
            SD.mkdir(dirs[i]);
            Serial.printf("[SD] Created: %s\n", dirs[i]);
        }
    }
}

// ═══════════════ LIST APPS ═══════════════
void nirvana_sd_list_apps() {
    if (!sdReady) return;
    File root = SD.open("/apps");
    if (!root || !root.isDirectory()) return;

    Serial.println("[SD] Installed apps:");
    File entry = root.openNextFile();
    while (entry) {
        if (entry.isDirectory()) {
            Serial.printf("  %s/\n", entry.name());
        }
        entry = root.openNextFile();
    }
    entry.close();
    root.close();
}

// ═══════════════ WRITE LOG ═══════════════
void nirvana_sd_log(const char* message) {
    if (!sdReady) return;
    File logFile = SD.open("/logs/agent.log", FILE_APPEND);
    if (logFile) {
        logFile.print(millis());
        logFile.print(": ");
        logFile.println(message);
        logFile.close();
    }
}

// ═══════════════ SAVE CONFIG ═══════════════
bool nirvana_sd_save_config(const char* key, const char* value) {
    if (!sdReady) return false;
    String path = "/config/" + String(key) + ".cfg";
    File f = SD.open(path.c_str(), FILE_WRITE);
    if (!f) return false;
    f.print(value);
    f.close();
    return true;
}

// ═══════════════ LOAD CONFIG ═══════════════
String nirvana_sd_load_config(const char* key) {
    if (!sdReady) return "";
    String path = "/config/" + String(key) + ".cfg";
    if (!SD.exists(path.c_str())) return "";
    File f = SD.open(path.c_str(), FILE_READ);
    if (!f) return "";
    String value = f.readString();
    f.close();
    return value;
}

#else
bool nirvana_sd_init() { return false; }
void nirvana_sd_list_apps() {}
void nirvana_sd_log(const char* message) {}
#endif

#endif // NIRVANA_SD_H
