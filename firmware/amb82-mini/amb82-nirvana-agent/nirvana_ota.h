// NIRVANA OTA — Firmware Over-The-Air updates via Ameba SDK
// Uses built-in OTA library (HTTP server + remote fetch)
// MQTT is NOT required for OTA — it uses raw HTTP POST to fetch .bin
#ifndef NIRVANA_OTA_H
#define NIRVANA_OTA_H

#include "OTA.h"
#include "nirvana_config.h"

#define OTA_PORT         8080
#define OTA_UPDATE_URL   "http://" MQTT_HOST ":9000/firmware/npu-amb82-latest.bin"

OTA otaEngine;
bool otaInProgress = false;
char otaStatus[48] = "Idle";

// ── Start OTA update check ──
// This starts the Ameba OTA HTTP server + connects to the update server
// The device will reboot after successful update.
// Requires WiFi to be already connected.
bool nirvana_ota_start() {
    if (WiFi.status() != WL_CONNECTED) {
        snprintf(otaStatus, sizeof(otaStatus), "No WiFi");
        Serial.println("[OTA] WiFi not connected");
        return false;
    }

    Serial.println("[OTA] Starting firmware update...");
    snprintf(otaStatus, sizeof(otaStatus), "Checking...");

    // OTA class spawns 2 FreeRTOS threads:
    // Thread 1: HTTP server on device (serves current fw info)
    // Thread 2: Connects to remote server, downloads .bin, flashes
    otaEngine.start_OTA_threads(OTA_PORT, (char*)OTA_UPDATE_URL);

    otaInProgress = true;
    snprintf(otaStatus, sizeof(otaStatus), "Downloading...");
    Serial.print("[OTA] Fetching from: ");
    Serial.println(OTA_UPDATE_URL);
    return true;
}

// ── Check OTA WiFi (called by OTA thread internally) ──
// Returns 0 = disconnected, 1 = connected
uint8_t nirvana_ota_check_wifi() {
    return otaEngine.check_wifi();
}

#endif
