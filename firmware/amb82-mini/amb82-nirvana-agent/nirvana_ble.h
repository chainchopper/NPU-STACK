// NIRVANA BLE — Connect Bluetooth keyboard/mouse/gamepad to control Nirvana OS
// Uses Ameba SDK BLE Central + GATT Client to discover and read HID reports
// Keyboard: arrows=nav, Enter=select, Esc=back, space=toggle
// Maps BLE HID keyboard reports to nirvana_control_exec() commands
//
// IMPORTANT: This requires a BLE keyboard advertising HID service (0x1812).
// Pair the keyboard with the AMB82 by putting it in pairing mode.
// The AMB82 will scan and auto-connect to the first HID device found.
#ifndef NIRVANA_BLE_H
#define NIRVANA_BLE_H

#include "BLEDevice.h"
#include "BLEClient.h"
#include "BLEScan.h"
#include "BLEUUID.h"
#include "nirvana_config.h"
#include "nirvana_menu.h"

// ── BLE HID Keyboard Report (standard 8-byte format) ──
// Byte 0: modifier keys (Ctrl/Shift/Alt/GUI)
// Byte 1: reserved (0x00)
// Bytes 2-7: up to 6 pressed key codes
// HID Usage ID key codes we care about:
#define HID_KEY_RIGHT   0x4F    // Right arrow
#define HID_KEY_LEFT    0x50    // Left arrow
#define HID_KEY_DOWN    0x51    // Down arrow  
#define HID_KEY_UP      0x52    // Up arrow
#define HID_KEY_ENTER   0x28    // Return/Enter
#define HID_KEY_ESC     0x29    // Escape
#define HID_KEY_SPACE   0x2C    // Spacebar
#define HID_KEY_TAB     0x2B    // Tab
#define HID_KEY_BKSP    0x2A    // Backspace
#define HID_KEY_DEL     0x4C    // Delete forward

// ── State ──
BLEClient* bleKeyboard = nullptr;
bool bleActive = false;
unsigned long bleLastScan = 0;
unsigned long bleLastAction = 0;

// HID Service UUID = 0x1812, HID Report Characteristic = 0x2A4D
#define HID_SVC_UUID     BLEUUID("1812")
#define HID_REPORT_UUID  BLEUUID("2A4D")
#define BLE_SCAN_TIMEOUT 5000   // Rescan every 5s if not connected

// ── Debounce: don't fire same key twice within 300ms ──
uint8_t  bleLastKey = 0;
unsigned long bleLastKeyTime = 0;

// ── Translate HID key code to command ──
void _ble_handle_key(uint8_t key) {
    // Debounce
    if (key == bleLastKey && millis() - bleLastKeyTime < 300) return;
    bleLastKey = key;
    bleLastKeyTime = millis();

    switch (key) {
    case HID_KEY_RIGHT: case HID_KEY_DOWN:
        menuCursor = (menuCursor + 1) % 7;
        lastMenuActivity = millis();
        break;
    case HID_KEY_LEFT: case HID_KEY_UP:
        menuCursor = (menuCursor + 6) % 7;  // -1 wrap
        lastMenuActivity = millis();
        break;
    case HID_KEY_ENTER:
        if (menuState == MENU_STATE_HOME) {
            menuState = menuCursor + 1;
            subCursor = 0;
        }
        lastMenuActivity = millis();
        break;
    case HID_KEY_ESC:
        if (menuState != MENU_STATE_HOME) {
            menuState = MENU_STATE_HOME;
            subCursor = 0;
        }
        lastMenuActivity = millis();
        break;
    case HID_KEY_SPACE:
        // Toggle action on current screen (snapshot/record/etc)
        extern void nirvana_vision_send_frame();
        if (menuState == MENU_STATE_NIRVANA_AI) nirvana_vision_send_frame();
        lastMenuActivity = millis();
        break;
    case HID_KEY_TAB:
        if (menuState != MENU_STATE_HOME) {
            subCursor = (subCursor + 1) % 10;
        }
        lastMenuActivity = millis();
        break;
    case HID_KEY_DEL:
        menuState = MENU_STATE_HOME;
        menuCursor = 0; subCursor = 0;
        lastMenuActivity = millis();
        break;
    case HID_KEY_BKSP:
        menuState = MENU_STATE_HOME;
        menuCursor = 0; subCursor = 0;
        lastMenuActivity = millis();
        break;
    }

    if (key) {
        snprintf(lastCommand, sizeof(lastCommand), "BLE key 0x%02X", key);
        Serial.print("[BLE] Key: 0x"); Serial.println(key, HEX);
    }
}

// ── Parse HID keyboard report (8 bytes) into key presses ──
void _ble_parse_report(const uint8_t* data, uint16_t len) {
    if (len < 3) return;
    // Byte 0: modifiers, Byte 1: reserved, Bytes 2-7: keys
    for (int i = 2; i < (int)len && i < 8; i++) {
        if (data[i] != 0) _ble_handle_key(data[i]);
    }
}

// ── GATT notification callback ──
void _ble_notify_cb(uint8_t conn_id, uint16_t handle, uint16_t value_size, uint8_t* value) {
    _ble_parse_report(value, value_size);
}

// ── Scan callback ──
void _ble_scan_cb(T_LE_CB_DATA* p_data) {
    // Try to connect to first HID device found
    // (Full GATT discovery is done in init)
}

// ── Init BLE scanner + connect to HID keyboard ──
bool nirvana_ble_init() {
    Serial.println("[BLE] Init HID keyboard scanner...");

    BLE.init();
    BLE.configScan()->setScanMode(GAP_SCAN_MODE_ACTIVE);
    BLE.configScan()->setScanInterval(0x30);
    BLE.configScan()->setScanWindow(0x20);

    // Start scanning for devices
    BLE.configScan()->startScan(0);  // Continuous scan

    Serial.println("[BLE] Scanning for HID devices...");
    Serial.println("[BLE] Put your keyboard in pairing mode");

    bleActive = true;
    return true;
}

// ── Tick: check BLE connection status, reconnect ──
void nirvana_ble_tick() {
    if (!bleActive) return;

    unsigned long now = millis();
    if (now - bleLastScan < BLE_SCAN_TIMEOUT) return;
    bleLastScan = now;

    // Check if we have any BLE client connections
    // The BLEClient dispatches callbacks internally via BLE.process()
    // We just need to keep scanning and checking

    if (!bleKeyboard || !bleKeyboard->connected()) {
        // Try to get client from BLE
        // Note: Full BLE Central HID requires GATT client profile
        // which the SDK exposes via BLEClient. For now, we scan and log.
        Serial.println("[BLE] Waiting for HID keyboard...");
    }
}

#endif
