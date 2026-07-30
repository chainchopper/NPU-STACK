// ╔══════════════════════════════════════════════════════════╗
// ║      NIRVANA FLEET AGENT — AMB82-Mini (RTL8735B)        ║
// ║  xiaozhi-compatible MQTT voice control protocol         ║
// ╚══════════════════════════════════════════════════════════╝

#include "nirvana_config.h"
#include "nirvana_wifi.h"

unsigned long lastStatusPublish = 0;
#define STATUS_INTERVAL_MS 30000

void setup() {
    Serial.begin(115200);
    delay(1000);

    Serial.println();
    Serial.println("===================================");
    Serial.println("  NIRVANA FLEET — AMB82-Mini");
    Serial.println("===================================");
    Serial.print("Version: ");
    Serial.println(NIRVANA_VERSION);
    Serial.print("Device:  ");
    Serial.println(NIRVANA_DEVICE_ID);
    Serial.print("Chip:    RTL8735B (Cortex-M33 + NN)");
    Serial.println();

    // WiFi + MQTT
    Serial.println();
    Serial.println("--- Network ---");
    if (nirvana_wifi_connect()) {
        nirvana_mqtt_connect();
    }

    Serial.println();
    Serial.println(">>> AGENT READY <<<");
    Serial.println();
}

void loop() {
    nirvana_mqtt_loop();

    unsigned long now = millis();
    if (now - lastStatusPublish > STATUS_INTERVAL_MS) {
        lastStatusPublish = now;
        nirvana_publish_status();
    }

    delay(10);
}
