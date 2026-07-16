# Write NPU config and agent to MicroPython device
import json, os

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

print("Config written:", os.listdir())

# Write a minimal main.py skeleton first
skeleton = '''
# NPU-STACK Agent - micro bootloader
import json, os, machine, time

try:
    with open("npu_config.json") as f:
        cfg = json.load(f)
    print("NPU Agent booting...")
    print(f"  ID: {cfg.get('device_id', 'unknown')}")
    print(f"  MQTT: {cfg['mqtt_broker']}:{cfg['mqtt_port']}")
except Exception as e:
    print("Config load failed:", e)
'''

with open("main.py", "w") as f:
    f.write(skeleton)

print("main.py written")
print("All files:", os.listdir())
