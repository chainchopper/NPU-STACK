// NIRVANA BLE — Bluetooth HID keyboard input
// Uses Ameba SDK BLE Central + GATT Client (properly initialized)
// Scans for HID keyboards (UUID 0x1812), auto-connects, reads reports
#ifndef NIRVANA_BLE_H
#define NIRVANA_BLE_H

#include "BLEDevice.h"
#include "BLEAdvertData.h"
#include "nirvana_config.h"
#include "nirvana_menu.h"

// Key codes
#define HID_KEY_RIGHT   0x4F
#define HID_KEY_LEFT    0x50
#define HID_KEY_DOWN    0x51
#define HID_KEY_UP      0x52
#define HID_KEY_ENTER   0x28
#define HID_KEY_ESC     0x29
#define HID_KEY_SPACE   0x2C
#define HID_KEY_TAB     0x2B
#define HID_KEY_BKSP    0x2A
#define HID_KEY_DEL     0x4C

// ── State ──
bool bleActive = false;
bool bleKbConnected = false;
BLEAdvertData foundDevice;
BLEAdvertData targetDevice;
unsigned long bleLastScan = 0;
unsigned long bleLastAction = 0;
uint8_t  bleLastKey = 0;
unsigned long bleLastKeyTime = 0;

// ── Scan callback — find first HID keyboard ──
void _ble_scan_callback(T_LE_CB_DATA* p_data) {
    foundDevice.parseScanInfo(p_data);

    // Look for devices with HID service (0x1812) in advertisement
    uint8_t svcCount = foundDevice.getServiceCount();
    if (svcCount > 0) {
        BLEUUID* svcs = foundDevice.getServiceList();
        for (uint8_t i = 0; i < svcCount; i++) {
            if (svcs[i] == BLEUUID("1812")) {   // HID service
                if (foundDevice.hasName()) {
                    Serial.print("[BLE] Found HID keyboard: ");
                    Serial.print(foundDevice.getName().c_str());
                    Serial.print(" addr=");
                    Serial.println(foundDevice.getAddr().str().c_str());
                } else {
                    Serial.print("[BLE] Found HID device: ");
                    Serial.println(foundDevice.getAddr().str().c_str());
                }
                targetDevice = foundDevice;
                BLE.configScan()->stopScan();
                return;
            }
        }
    }
}

// ── Notification callback for HID report characteristic ──
void _ble_hid_notify_cb(BLERemoteCharacteristic* chr, uint8_t* data, uint16_t len) {
    // Parse standard 8-byte HID keyboard report
    for (int i = 2; i < (int)len && i < 8; i++) {
        if (data[i] == 0) continue;
        // Debounce
        if (data[i] == bleLastKey && millis() - bleLastKeyTime < 300) continue;
        bleLastKey = data[i];
        bleLastKeyTime = millis();

        uint8_t k = data[i];
        Serial.print("[BLE] Key 0x"); Serial.println(k, HEX);
        snprintf(lastCommand, sizeof(lastCommand), "BLE 0x%02X", k);

        switch (k) {
        case HID_KEY_RIGHT: case HID_KEY_DOWN:
            menuCursor = (menuCursor + 1) % 7; lastMenuActivity = millis(); break;
        case HID_KEY_LEFT: case HID_KEY_UP:
            menuCursor = (menuCursor + 6) % 7; lastMenuActivity = millis(); break;
        case HID_KEY_ENTER:
            if (menuState == MENU_STATE_HOME) { menuState = menuCursor + 1; subCursor = 0; }
            lastMenuActivity = millis(); break;
        case HID_KEY_ESC:
            if (menuState != MENU_STATE_HOME) { menuState = MENU_STATE_HOME; subCursor = 0; }
            lastMenuActivity = millis(); break;
        case HID_KEY_SPACE:
            if (menuState == MENU_STATE_NIRVANA_AI) { extern bool nirvana_vision_send_frame(); nirvana_vision_send_frame(); }
            lastMenuActivity = millis(); break;
        case HID_KEY_TAB:
            if (menuState != MENU_STATE_HOME) { subCursor = (subCursor + 1) % 10; }
            lastMenuActivity = millis(); break;
        case HID_KEY_DEL: case HID_KEY_BKSP:
            menuState = MENU_STATE_HOME; menuCursor = 0; subCursor = 0;
            lastMenuActivity = millis(); break;
        }
    }
}

// ── Init BLE Central + scan ──
bool nirvana_ble_init() {
    Serial.println("[BLE] Init Central + HID scanner...");

    BLE.init();
    BLE.setScanCallback(_ble_scan_callback);
    BLE.beginCentral(1);   // 1 = max concurrent connections

    BLE.configScan()->setScanMode(GAP_SCAN_MODE_ACTIVE);
    BLE.configScan()->setScanInterval(0x40);
    BLE.configScan()->setScanWindow(0x30);
    BLE.configScan()->updateScanParams();

    BLE.configScan()->startScan(0);  // Continuous scan

    bleActive = true;
    Serial.println("[BLE] Scanning for HID keyboards (UUID 0x1812)...");
    return true;
}

// ── Re-scan every 30s if no connection ──
void nirvana_ble_tick() {
    if (!bleActive) return;
    unsigned long now = millis();

    // Re-start scan if no device connected
    if (!bleKbConnected && now - bleLastScan > 30000) {
        bleLastScan = now;
        BLE.configScan()->startScan(5000);
        Serial.println("[BLE] Re-scanning...");
    }
}

#endif
