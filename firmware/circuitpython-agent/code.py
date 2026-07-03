# NPU-STACK Fleet Agent — CircuitPython
# ==========================================
# MQTT telemetry + BLE pairing + remote command execution + OTA
#
# Flash this as code.py to any CircuitPython-compatible board (RP2040/RP2350/nRF/ESP32-S2/S3)
# Board auto-registers with NPU-STACK command center on boot via MQTT.
#
# Commands supported: BLINK, READ_SENSORS, GPIO_WRITE, GPIO_READ, EXEC_PYTHON, RESET, SET_CONFIG, GET_CONFIG
#
# First-time pairing: connect via REPL serial and set wifi_ssid/wifi_password
# After first pairing, config persists in npu_config.json

import time, json, os, gc, board, microcontroller, wifi, socketpool, digitalio, analogio, supervisor

CONFIG_FILE = "npu_config.json"
DEFAULTS = {
    "device_id": f"cp-{hex(microcontroller.cpu.uid)[2:10]}",
    "mqtt_broker": "127.0.0.1",
    "mqtt_port": 1883,
    "wifi_ssid": "",
    "wifi_password": "",
    "telemetry_interval": 5,
}

def load_config():
    try:
        with open(CONFIG_FILE) as f:
            cfg = json.load(f)
        for k, v in DEFAULTS.items():
            if k not in cfg: cfg[k] = v
        return cfg
    except: return dict(DEFAULTS)

def save_config(cfg):
    try: json.dump(cfg, open(CONFIG_FILE, "w"))
    except: pass

config = load_config()

led = digitalio.DigitalInOut(board.LED)
led.direction = digitalio.Direction.OUTPUT
led.value = True

def blink(count, speed=0.1):
    for _ in range(count):
        led.value = not led.value; time.sleep(speed)
    led.value = True

def connect_wifi():
    if not config["wifi_ssid"]: return False
    try:
        wifi.radio.connect(config["wifi_ssid"], config["wifi_password"])
        return True
    except Exception as e:
        print(f"WiFi error: {e}"); return False

# Minimal MQTT client — no external deps
class MiniMQTT:
    def __init__(self, broker, port, client_id):
        self.broker, self.port, self.client_id = broker, port, client_id
        self.sock = None; self.connected = False
        self.pool = socketpool.SocketPool(wifi.radio)
    def connect(self):
        try:
            addr = self.pool.getaddrinfo(self.broker, self.port)[0][4]
            self.sock = self.pool.socket(); self.sock.settimeout(10); self.sock.connect(addr)
            # Minimal CONNECT packet
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
                payload = data[idx:].decode()
                return {"topic": topic, "payload": payload}
        except OSError: pass
        return None

def read_sensors():
    data = {"device_id": config["device_id"], "uptime": time.monotonic(),
            "free_mem": gc.mem_free(), "cpu_temp": microcontroller.cpu.temperature, "voltage": 0.0}
    try:
        for name in dir(board):
            if name.startswith("A"):
                ain = analogio.AnalogIn(getattr(board, name))
                data["voltage"] = (ain.value * 3.3) / 65536; ain.deinit(); break
    except: pass
    return data

def execute_command(cmd):
    r = {"command": cmd.get("command"), "success": False}
    try:
        c = cmd["command"]
        if c == "BLINK": n = int(cmd.get("count", 3)); s = float(cmd.get("speed", 0.2)); blink(n, s); r["success"] = True; r["output"] = f"LED blinked {n}x"
        elif c == "READ_SENSORS": r["success"] = True; r["output"] = json.dumps(read_sensors())
        elif c == "GPIO_WRITE":
            pin = cmd.get("pin", "LED"); val = int(cmd.get("value", 0))
            p = digitalio.DigitalInOut(getattr(board, pin, board.LED)); p.direction = digitalio.Direction.OUTPUT; p.value = val
            r["success"] = True; r["output"] = f"{pin}={val}"
        elif c == "GPIO_READ":
            pin = cmd.get("pin", "LED")
            p = digitalio.DigitalInOut(getattr(board, pin, board.LED)); p.direction = digitalio.Direction.INPUT
            r["success"] = True; r["output"] = str(p.value)
        elif c == "EXEC_PYTHON":
            exec(cmd.get("code", "")); r["success"] = True; r["output"] = "OK"
        elif c == "RESET": r["success"] = True; r["output"] = "Resetting..."; supervisor.reload()
        elif c == "SET_CONFIG":
            for k, v in cmd.items():
                if k in config and k != "command": config[k] = v
            save_config(config); r["success"] = True; r["output"] = "Config updated"
        elif c == "GET_CONFIG": r["success"] = True; r["output"] = json.dumps(config)
        else: r["output"] = f"Unknown: {c}"
    except Exception as e: r["output"] = str(e)
    return json.dumps(r)

print(f"NPU-STACK Agent | Device: {config['device_id']} | Board: {board.board_id}")
if not connect_wifi():
    print("WiFi not configured — connect via REPL to set npu_config.json")
    while not wifi.radio.connected:
        blink(2, 0.5); time.sleep(2)
        if config["wifi_ssid"]:
            try: connect_wifi()
            except: pass

print(f"Connected: {wifi.radio.ipv4_address}")
mqtt = MiniMQTT(config["mqtt_broker"], config["mqtt_port"], config["device_id"])
TOPIC_STATUS = f"fleet/status/{config['device_id']}"
TOPIC_CMD = f"fleet/cmd/{config['device_id']}"
TOPIC_RESPONSE = f"fleet/response/{config['device_id']}"
last_t = 0; last_wifi = time.monotonic()

while True:
    now = time.monotonic()
    if not mqtt.connected:
        try: mqtt.connect(); mqtt.subscribe(TOPIC_CMD) if mqtt.connected else None
        except: pass
    if now - last_wifi > 30:
        last_wifi = now
        if not wifi.radio.connected: connect_wifi()
    if now - last_t > config["telemetry_interval"] and mqtt.connected:
        last_t = now; ts = read_sensors()
        ts["rssi"] = wifi.radio.ap_info.rssi if wifi.radio.connected else 0
        ts["ip"] = str(wifi.radio.ipv4_address) if wifi.radio.connected else ""
        mqtt.publish(TOPIC_STATUS, json.dumps(ts))
    if mqtt.connected:
        msg = mqtt.check()
        if msg and msg["topic"] == TOPIC_CMD:
            try:
                result = execute_command(json.loads(msg["payload"]))
                mqtt.publish(TOPIC_RESPONSE, result); blink(2, 0.05)
            except: pass
    time.sleep(0.1)
