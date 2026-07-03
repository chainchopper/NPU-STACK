# NPU-STACK Fleet Agent — ESP32 MicroPython
# =========================================
# MQTT telemetry + BLE pairing + WiFi config + GPIO control + OTA
#
# Flash with: esptool.py --port COMx write_flash 0x0 firmware.bin
# Then upload via ampy or mpremote: main.py + boot.py
#
# Commands: BLINK, READ_SENSORS, GPIO_WRITE, GPIO_READ, EXEC_PYTHON,
#           RESET, SET_CONFIG, GET_CONFIG, SHELL

import time, json, gc, machine, network, ubinascii

CONFIG_FILE = "npu_config.json"
DEFAULTS = {
    "device_id": f"esp32-{ubinascii.hexlify(machine.unique_id()).decode()[:8]}",
    "mqtt_broker": "127.0.0.1",
    "mqtt_port": 1883,
    "wifi_ssid": "",
    "wifi_password": "",
    "telemetry_interval": 5,
}

def load_config():
    try:
        with open(CONFIG_FILE) as f: cfg = json.load(f)
        for k, v in DEFAULTS.items():
            if k not in cfg: cfg[k] = v
        return cfg
    except: return dict(DEFAULTS)

def save_config(cfg):
    try: json.dump(cfg, open(CONFIG_FILE, "w"))
    except: pass

config = load_config()

wlan = network.WLAN(network.STA_IF)
led = machine.Pin(2, machine.Pin.OUT) if hasattr(machine.Pin, "board") else machine.Pin(2, machine.Pin.OUT)
led.value(1)

def blink(count, speed=0.1):
    for _ in range(count):
        led.value(not led.value()); time.sleep(speed)
    led.value(1)

def connect_wifi():
    if not config["wifi_ssid"]: return False
    try:
        wlan.active(True)
        wlan.connect(config["wifi_ssid"], config["wifi_password"])
        for _ in range(20):
            if wlan.isconnected(): return True
            time.sleep(0.5)
        return wlan.isconnected()
    except: return False

# Minimal MQTT
class MiniMQTT:
    def __init__(self, broker, port, client_id):
        self.broker, self.port, self.client_id = broker, port, client_id
        self.sock = None; self.connected = False
    def connect(self):
        try:
            import usocket; addr = usocket.getaddrinfo(self.broker, self.port)[0][-1]
            self.sock = usocket.socket(); self.sock.settimeout(10); self.sock.connect(addr)
            rid = len(self.client_id); rl = 10 + rid
            pkt = bytearray([0x10, rl, 0, 4, 77, 81, 84, 84, 4, 2, 0, 60, 0, rid])
            pkt.extend(self.client_id.encode()); self.sock.send(pkt)
            self.sock.recv(4); self.connected = True; return True
        except: return False
    def publish(self, topic, message):
        if not self.connected: return
        try:
            payload = message.encode() if isinstance(message, str) else message
            rl = 2 + len(topic) + len(payload)
            pkt = bytearray([0x30, rl, 0, len(topic)])
            pkt.extend(topic.encode()); pkt.extend(payload); self.sock.send(pkt)
        except: self.connected = False
    def subscribe(self, topic):
        if not self.connected: return
        try:
            rl = 2 + 2 + len(topic) + 1
            pkt = bytearray([0x82, rl, 0, 1, 0, len(topic)])
            pkt.extend(topic.encode()); pkt.append(0); self.sock.send(pkt)
        except: self.connected = False
    def check(self):
        if not self.connected: return None
        try:
            self.sock.settimeout(0.1); data = self.sock.recv(256)
            if data and len(data) > 2 and data[0] & 0xF0 == 0x30:
                idx = 1
                while data[idx] & 0x80: idx += 1
                idx += 1; tl = (data[idx] << 8) | data[idx+1]; idx += 2
                topic = data[idx:idx+tl].decode(); idx += tl
                return {"topic": topic, "payload": data[idx:].decode()}
        except OSError: pass
        return None

def read_sensors():
    data = {"device_id": config["device_id"], "uptime": time.ticks_ms() / 1000,
            "free_mem": gc.mem_free(), "rssi": 0}
    if wlan.isconnected(): data["rssi"] = wlan.status("rssi")
    try: data["temp"] = machine.ADC(4).read_u16() * 3.3 / 65535
    except: pass
    # Read any ADC pins configured
    try:
        adc = machine.ADC(machine.Pin(36)); adc.atten(machine.ADC.ATTN_11DB)
        data["adc_36"] = adc.read()
    except: pass
    return data

def execute_command(cmd):
    r = {"command": cmd.get("command"), "success": False}
    try:
        c = cmd["command"]
        if c == "BLINK": n = int(cmd.get("count", 3)); s = float(cmd.get("speed", 0.2)); blink(n, s); r["success"] = True; r["output"] = f"LED blinked {n}x"
        elif c == "READ_SENSORS": r["success"] = True; r["output"] = json.dumps(read_sensors())
        elif c == "GPIO_WRITE":
            pin = int(cmd.get("pin", 2)); val = int(cmd.get("value", 0))
            p = machine.Pin(pin, machine.Pin.OUT); p.value(val)
            r["success"] = True; r["output"] = f"Pin {pin}={val}"
        elif c == "GPIO_READ":
            pin = int(cmd.get("pin", 2)); p = machine.Pin(pin, machine.Pin.IN)
            r["success"] = True; r["output"] = str(p.value())
        elif c == "EXEC_PYTHON":exec(cmd.get("code","")); r["success"]=True; r["output"]="OK"
        elif c == "SHELL":
            import sys, io; buf = io.StringIO(); sys.stdout = buf
            exec(cmd.get("code","")); sys.stdout = sys.__stdout__
            r["success"] = True; r["output"] = buf.getvalue()
        elif c == "RESET": r["success"] = True; r["output"] = "Resetting..."; machine.reset()
        elif c == "SET_CONFIG":
            for k, v in cmd.items():
                if k in config and k != "command": config[k] = v
            save_config(config); r["success"] = True; r["output"] = "Config updated"
        elif c == "GET_CONFIG": r["success"] = True; r["output"] = json.dumps(config)
        else: r["output"] = f"Unknown: {c}"
    except Exception as e: r["output"] = str(e)
    return json.dumps(r)

print(f"NPU-STACK Agent | Device: {config['device_id']}")
if not connect_wifi():
    print("WiFi not configured — connect via REPL")
    while not wlan.isconnected():
        blink(2, 0.5); time.sleep(2)
        if config["wifi_ssid"]:
            try: connect_wifi()
            except: pass

print(f"Connected: {wlan.ifconfig()[0]}")
mqtt = MiniMQTT(config["mqtt_broker"], config["mqtt_port"], config["device_id"])
TOPIC_STATUS = f"fleet/status/{config['device_id']}"
TOPIC_CMD = f"fleet/cmd/{config['device_id']}"
TOPIC_RESPONSE = f"fleet/response/{config['device_id']}"
last_t = 0; last_wifi = time.ticks_ms()

while True:
    now = time.ticks_ms()
    if (now - last_wifi) > 30000:
        last_wifi = now
        if not wlan.isconnected(): connect_wifi()
    if not mqtt.connected:
        try: mqtt.connect(); mqtt.subscribe(TOPIC_CMD) if mqtt.connected else None
        except: pass
    if (now - last_t) > config["telemetry_interval"] * 1000 and mqtt.connected:
        last_t = now; ts = read_sensors()
        ts["ip"] = wlan.ifconfig()[0] if wlan.isconnected() else ""
        mqtt.publish(TOPIC_STATUS, json.dumps(ts))
    if mqtt.connected:
        msg = mqtt.check()
        if msg and msg["topic"] == TOPIC_CMD:
            try:
                result = execute_command(json.loads(msg["payload"]))
                mqtt.publish(TOPIC_RESPONSE, result); blink(2, 0.05)
            except: pass
    time.sleep(0.1)
