// NIRVANA BLE — Bluetooth HID keyboard via GATT Client
// Scans for HID service (0x1812), connects, reads HID reports (0x2A4D)
// Keys → menu navigation. Works offline — no WiFi needed.
#ifndef NIRVANA_BLE_H
#define NIRVANA_BLE_H

#include "BLEDevice.h"
#include "BLEAdvertData.h"
#include "BLEClient.h"
#include "BLERemoteService.h"
#include "BLERemoteCharacteristic.h"
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
bool  bleActive = false;
bool  bleConnecting = false;
BLEClient* bleClient = nullptr;
BLERemoteService*      bleHidSvc = nullptr;
BLERemoteCharacteristic* bleHidReport = nullptr;
BLEAdvertData targetDevice;
unsigned long bleLastAction = 0;
uint8_t  bleLastKey = 0;
unsigned long bleLastKeyTime = 0;

// ── HID report notification → key handler ──
void _ble_hid_notify(BLERemoteCharacteristic* chr, uint8_t* data, uint16_t len) {
    for (int i = 2; i < (int)len && i < 8; i++) {
        if (data[i] == 0) continue;
        if (data[i] == bleLastKey && millis() - bleLastKeyTime < 300) continue;
        bleLastKey = data[i]; bleLastKeyTime = millis();
        uint8_t k = data[i];
        Serial.print("[BLE] Key 0x"); Serial.println(k, HEX);
        snprintf(lastCommand, sizeof(lastCommand), "BLE 0x%02X", k);

        switch (k) {
        case HID_KEY_RIGHT: case HID_KEY_DOWN:
            menuCursor = (menuCursor + 1) % 7; lastMenuActivity = millis(); break;
        case HID_KEY_LEFT: case HID_KEY_UP:
            menuCursor = (menuCursor + 6) % 7; lastMenuActivity = millis(); break;
        case HID_KEY_ENTER:
            if (menuState == MENU_STATE_HOME) { menuState = menuCursor+1; subCursor=0; }
            lastMenuActivity = millis(); break;
        case HID_KEY_ESC:
            if (menuState != MENU_STATE_HOME) { menuState=MENU_STATE_HOME; subCursor=0; }
            lastMenuActivity = millis(); break;
        case HID_KEY_TAB:
            if (menuState != MENU_STATE_HOME) subCursor = (subCursor+1)%10;
            lastMenuActivity = millis(); break;
        case HID_KEY_DEL: case HID_KEY_BKSP:
            menuState = MENU_STATE_HOME; menuCursor=0; subCursor=0;
            lastMenuActivity = millis(); break;
        }
    }
}

// ── Scan callback: find HID device, stop scan, trigger connect ──
void _ble_scan_cb(T_LE_CB_DATA* p_data) {
    BLEAdvertData dev; dev.parseScanInfo(p_data);
    uint8_t n = dev.getServiceCount();
    if (n == 0) return;
    BLEUUID* svcs = dev.getServiceList();
    for (uint8_t i = 0; i < n; i++) {
        if (svcs[i] == BLEUUID("1812")) {
            Serial.print("[BLE] Found HID: ");
            Serial.println(dev.hasName() ? dev.getName().c_str() : dev.getAddr().str());
            targetDevice = dev;
            BLE.configScan()->stopScan();
            bleConnecting = true;
            return;
        }
    }
}

// ── Init BLE Central + start scan ──
bool nirvana_ble_init() {
    Serial.println("[BLE] Init Central...");
    BLE.init();
    BLE.setScanCallback(_ble_scan_cb);
    BLE.beginCentral(1);
    BLE.configScan()->setScanMode(GAP_SCAN_MODE_ACTIVE);
    BLE.configScan()->setScanInterval(0x50);
    BLE.configScan()->setScanWindow(0x40);
    BLE.configScan()->updateScanParams();
    BLE.configScan()->startScan(0);
    bleActive = true;
    Serial.println("[BLE] Scanning for HID keyboards (UUID 0x1812)");
    return true;
}

// ── Tick: connect to found device, discover HID service, subscribe ──
void nirvana_ble_tick() {
    if (!bleActive) return;

    // Phase 1: Connect to target
    if (bleConnecting && !bleClient) {
        BLE.configConnection()->connect(targetDevice, 3000);
        delay(2000);
        int8_t cid = BLE.configConnection()->getConnId(targetDevice);
        if (!BLE.connected(cid)) {
            Serial.println("[BLE] Connect failed — re-scanning");
            bleConnecting = false;
            BLE.configScan()->startScan(0);
            return;
        }
        BLE.configClient();
        bleClient = BLE.addClient(cid);
        bleClient->discoverServices();
        Serial.println("[BLE] Connected — discovering services...");
        return;
    }

    // Phase 2: Discover services + find HID
    if (bleClient && !bleHidSvc) {
        if (!bleClient->discoveryDone()) {
            delay(500); return;
        }
        bleHidSvc = bleClient->getService("1812");
        if (!bleHidSvc) {
            Serial.println("[BLE] HID service not found");
            bleClient = nullptr; bleConnecting = false;
            BLE.configScan()->startScan(0);
            return;
        }
        bleHidReport = bleHidSvc->getCharacteristic("2A4D");
        if (!bleHidReport) {
            Serial.println("[BLE] HID report char not found");
            bleClient = nullptr; bleHidSvc = nullptr; bleConnecting = false;
            BLE.configScan()->startScan(0);
            return;
        }
        bleHidReport->setNotifyCallback(_ble_hid_notify);
        bleHidReport->enableNotifyIndicate();
        Serial.println("[BLE] HID keyboard ready! Use arrow keys to navigate");
        bleConnecting = false;
    }

    // Phase 3: Re-scan if disconnected
    if (!bleClient || !BLE.connected(bleClient->getConnId())) {
        static unsigned long lastRescan = 0;
        if (millis() - lastRescan > 15000) {
            lastRescan = millis();
            bleClient = nullptr; bleHidSvc = nullptr; bleHidReport = nullptr;
            bleConnecting = false;
            Serial.println("[BLE] Re-scanning...");
            BLE.configScan()->startScan(0);
        }
    }
}

#endif
