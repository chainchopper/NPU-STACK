# Push NPU agent config and skeleton to MicroPython device
# Run via: mpremote connect COM13 run setup_agent.py
import json, os as uos

config = {
    "device_id": "esp32-s3-npu-01",
    "mqtt_broker": "127.0.0.1",
    "mqtt_port": 1883,
    "wifi_ssid": "",
    "wifi_password": "",
    "telemetry_interval": 5,
}

# Write config
with open("npu_config.json", "w") as f:
    json.dump(config, f)
print("Config written OK")

# Write skeleton main.py
agent = """
# NPU-STACK Fleet Agent - ESP32 MicroPython
import json, uos, machine, network, time, ubinascii

CONFIG_FILE = "npu_config.json"
DEFAULTS = {"device_id": "esp32-unknown", "mqtt_broker": "127.0.0.1",
            "mqtt_port": 1883, "wifi_ssid": "", "wifi_password": "",
            "telemetry_interval": 5}

def load_config():
    try:
        with open(CONFIG_FILE) as f: cfg = json.load(f)
        for k, v in DEFAULTS.items():
            if k not in cfg: cfg[k] = v
        return cfg
    except:
        return dict(DEFAULTS)

def get_health(cfg):
    return {
        "device_id": cfg["device_id"],
        "free_mem": uos.statvfs("/")[0] * uos.statvfs("/")[3],
        "cpu_temp": "N/A",
        "uptime": time.ticks_ms() // 1000,
    }

def connect_wifi(cfg):
    if not cfg["wifi_ssid"]:
        print("WiFi not configured - USB/serial only")
        return None
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(cfg["wifi_ssid"], cfg["wifi_password"])
    for _ in range(20):
        if wlan.isconnected():
            print("WiFi:", wlan.ifconfig()[0])
            return wlan
        time.sleep(1)
    print("WiFi failed")
    return None

def main():
    print("=== NPU-STACK Agent v1.0 ===")
    cfg = load_config()
    print("Device:", cfg["device_id"])
    print("MQTT:", cfg["mqtt_broker"], ":", cfg["mqtt_port"])
    wlan = connect_wifi(cfg)
    health = get_health(cfg)
    print("Health:", json.dumps(health))
    print("Agent ready - listening on USB REPL")

main()
"""

with open("main.py", "w") as f:
    f.write(agent)
print("main.py written OK:", len(agent), "bytes")
print("Files:", uos.listdir())
