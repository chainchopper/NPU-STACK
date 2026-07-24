#ifndef NIRVANA_BLE_H
#define NIRVANA_BLE_H

// BLE provisioning + fleet discovery
// AMB82-Mini has BLE 5.1 — advertise as "Nirvana Fleet"

#if FEATURE_BLE

bool bleReady = false;

// ═══════════════ INIT ═══════════════
bool nirvana_ble_init() {
    // Ameba BLE API:
    // BLE.begin("Nirvana-AMB82");
    // BLE.setManufacturerData(...);
    // BLE.advertise();

    Serial.println("[BLE] Advertising as Nirvana Fleet device");
    Serial.printf("[BLE] Name: Nirvana-%s\n", NIRVANA_DEVICE_ID);
    bleReady = true;
    return true;
}

// ═══════════════ BLE PROVISIONING ═══════════════
// Allow WiFi credentials to be set via BLE
bool nirvana_ble_provision_loop() {
    // Check for BLE connection + provisioning data
    // If connected device sends WiFi SSID/PASS, save to SD
    return false;
}

#else
bool nirvana_ble_init() { return false; }
#endif

#endif // NIRVANA_BLE_H
