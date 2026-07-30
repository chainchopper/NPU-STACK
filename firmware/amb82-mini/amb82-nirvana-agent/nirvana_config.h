// Nirvana Fleet Agent — AMB82-Mini Configuration
// Board: Realtek RTL8735B (AmebaD Pro2 SDK)

#ifndef NIRVANA_CONFIG_H
#define NIRVANA_CONFIG_H

// ═══ FLEET BRANDING ═══
#define NIRVANA_DEVICE_ID    "npu-amb82-001"
#define NIRVANA_FLEET_NAME   "NIRVANA FLEET"
#define NIRVANA_VERSION      "v1.0"

// ═══ WIFI ═══
#ifndef WIFI_SSID
#define WIFI_SSID           "YOUR_SSID"
#endif
#ifndef WIFI_PASS
#define WIFI_PASS           "YOUR_PASSWORD"
#endif

// ═══ MQTT ═══
#ifndef MQTT_HOST
#define MQTT_HOST           "192.168.1.100"
#endif
#define MQTT_PORT           1883
#define MQTT_KEEPALIVE      240
#define MQTT_TOPIC_PREFIX   "npu-fleet/amb82"

// ═══ FEATURES ═══
#define FEATURE_DISPLAY     0
#define FEATURE_CAMERA      0
#define FEATURE_AUDIO       0
#define FEATURE_SD          0

#endif
