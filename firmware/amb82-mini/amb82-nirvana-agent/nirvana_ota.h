// NIRVANA OTA — Firmware Over-The-Air updates via Ameba SDK
// Uses built-in OTA library (HTTP server + remote fetch)
// MQTT is NOT required for OTA — it uses raw HTTP POST to fetch .bin
#ifndef NIRVANA_OTA_H
#define NIRVANA_OTA_H

#include "OTA.h"
#include "nirvana_config.h"

// OTA: devices polls NPU-STACK backend for updates at boot + every 60 min.
// Backend serves the compiled .bin at /api/fleet/ota/npu-amb82-latest.bin
#define OTA_PORT         8080
#define OTA_HOST         MQTT_HOST
#define OTA_UPDATE_PATH  "/api/fleet/ota/npu-amb82-latest.bin"

OTA otaEngine;
bool otaInProgress = false;
char otaStatus[48] = "Idle";

// ── Start OTA update check ──
// Polls NPU-STACK backend for firmware update.
// If newer .bin available, downloads, flashes, and reboots.
bool nirvana_ota_start() {
    if (WiFi.status() != WL_CONNECTED) {
        snprintf(otaStatus, sizeof(otaStatus), "No WiFi");
        return false;
    }

    char url[128];
    snprintf(url, sizeof(url), "http://%s:%d%s", OTA_HOST, 8010, OTA_UPDATE_PATH);
    Serial.print("[OTA] Update check: "); Serial.println(url);
    snprintf(otaStatus, sizeof(otaStatus), "Checking...");

    otaEngine.start_OTA_threads(OTA_PORT, url);
    otaInProgress = true;
    snprintf(otaStatus, sizeof(otaStatus), "Download+flash...");
    return true;
}

// ── Background auto-check: call from loop every 60 minutes ──
void nirvana_ota_auto_check() {
    static unsigned long lastCheck = 0;
    unsigned long now = millis();
    if (otaInProgress) return;
    if (WiFi.status() != WL_CONNECTED) return;
    if (now - lastCheck < 3600000UL) return;  // 60 min
    lastCheck = now;
    nirvana_ota_start();
}

// ── Check OTA WiFi (called by OTA thread internally) ──
// Returns 0 = disconnected, 1 = connected
uint8_t nirvana_ota_check_wifi() {
    return otaEngine.check_wifi();
}

#endif
