"""NPU-STACK Nirvana Fleet Agent — Waveshare ESP32-S3 Matrix (25x WS2812 NeoPixel)

Hardware:
- Waveshare ESP32-S3 Matrix (8MB PSRAM, 16MB Flash)
- 25 WS2812 NeoPixels on pin 21
- Branded as "Nirvana Matrix" via USB/mDNS/BLE/MQTT descriptors
- One-flash architecture: auto-registers with NPU-STACK MQTT broker on boot

Commands (via MQTT fleet/cmd/<device_id>):
  NEOPIXEL_FILL, NEOPIXEL_RAINBOW, NEOPIXEL_OFF, NEOPIXEL_BRIGHTNESS
  GET_HEALTH, SET_CONFIG, OTA_UPDATE, REBOOT, EXEC_PYTHON
"""
import json, machine, network, neopixel, time, gc, ubinascii

# ── Hardware ───────────────────────────────────────────────────────────────
NEOPIXEL_PIN = 21
NEOPIXEL_COUNT = 25
LED_BRIGHTNESS = 0.2  # 0.0-1.0

CONFIG_FILE = "npu_config.json"
DEFAULTS = {
    "device_id": f"nirvana-matrix-{ubinascii.hexlify(machine.unique_id()).decode()[:8]}",
    "mqtt_broker": "127.0.0.1",
    "mqtt_port": 1883,
    "wifi_ssid": "",
    "wifi_password": "",
    "telemetry_interval": 10,
    "led_brightness": 0.2,
    "led_default_animation": "rainbow",
}

# Init NeoPixels
np = neopixel.NeoPixel(machine.Pin(NEOPIXEL_PIN), NEOPIXEL_COUNT)

# ── Config ─────────────────────────────────────────────────────────────────
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

# ── NeoPixel Animations ────────────────────────────────────────────────────
def wheel(pos):
    """Generate rainbow colors across 0-255 positions."""
    if pos < 85:  return (pos * 3, 255 - pos * 3, 0)
    elif pos < 170: pos -= 85; return (255 - pos * 3, 0, pos * 3)
    else: pos -= 170; return (0, pos * 3, 255 - pos * 3)

def np_fill(r, g, b):
    """Fill all pixels with a color."""
    b = int(b * config["led_brightness"])
    for i in range(NEOPIXEL_COUNT):
        np[i] = (int(r * config["led_brightness"]), int(g * config["led_brightness"]), b)
    np.write()

def np_off():
    for i in range(NEOPIXEL_COUNT): np[i] = (0, 0, 0)
    np.write()

def np_rainbow(iteration=0):
    """Rainbow cycle animation."""
    for j in range(256):
        for i in range(NEOPIXEL_COUNT):
            rc_index = (i * 256 // NEOPIXEL_COUNT + j + iteration) & 255
            color = wheel(rc_index)
            np[i] = tuple(int(c * config["led_brightness"]) for c in color)
        np.write()

def np_pulse(color=(0, 0, 255), duration_s=3):
    """Pulse breathing effect."""
    steps = 50
    delay = duration_s * 1000 / steps / 2
    for i in range(steps):
        factor = i / steps
        r = int(color[0] * factor * config["led_brightness"])
        g = int(color[1] * factor * config["led_brightness"])
        b = int(color[2] * factor * config["led_brightness"])
        for j in range(NEOPIXEL_COUNT): np[j] = (r, g, b)
        np.write(); time.sleep_ms(int(delay))
    for i in range(steps, 0, -1):
        factor = i / steps
        r = int(color[0] * factor * config["led_brightness"])
        g = int(color[1] * factor * config["led_brightness"])
        b = int(color[2] * factor * config["led_brightness"])
        for j in range(NEOPIXEL_COUNT): np[j] = (r, g, b)
        np.write(); time.sleep_ms(int(delay))

def np_brand():
    """Show Nirvana branding on LEDs - green pulse."""
    np_fill(0, 255, 0)
    time.sleep(0.5)
    np_off()
    np_pulse((74, 222, 128), 1.5)

# ── WiFi ───────────────────────────────────────────────────────────────────
def connect_wifi(cfg):
    if not cfg["wifi_ssid"]: return None
    wlan = network.WLAN(network.STA_IF); wlan.active(True)
    wlan.connect(cfg["wifi_ssid"], cfg["wifi_password"])
    for _ in range(30):
        if wlan.isconnected(): return wlan
        time.sleep(0.5)
    return None

# ── Health ─────────────────────────────────────────────────────────────────
def get_health(cfg):
    gc.collect()
    return {
        "device_id": cfg["device_id"], "device_type": "waveshare-s3-matrix",
        "online": True, "uptime_s": time.ticks_ms() // 1000,
        "free_ram": gc.mem_free(), "freq_mhz": machine.freq() // 1_000_000,
        "neopixel_count": NEOPIXEL_COUNT, "led_brightness": cfg["led_brightness"],
    }

# ── MiniMQTT Client ────────────────────────────────────────────────────────
class MiniMQTT:
    def __init__(self, broker, port, client_id):
        self.broker, self.port, self.client_id = broker, port, client_id
        self.sock = None; self.connected = False
    def connect(self):
        try:
            import usocket; addr = usocket.getaddrinfo(self.broker, self.port)[0][-1]
            self.sock = usocket.socket(); self.sock.settimeout(10); self.sock.connect(addr)
            cid_len = len(self.client_id); remaining = 10 + cid_len
            pkt = bytearray([0x10, remaining, 0, 4, 77, 81, 84, 84, 4, 2, 0, 60, 0, cid_len])
            pkt.extend(self.client_id.encode()); self.sock.send(pkt)
            self.sock.recv(4); self.connected = True; return True
        except: return False
    def publish(self, topic, message):
        if not self.connected: return
        try:
            payload = message.encode() if isinstance(message, str) else message
            remaining = 2 + len(topic) + len(payload)
            pkt = bytearray([0x30, remaining, 0, len(topic)])
            pkt.extend(topic.encode()); pkt.extend(payload); self.sock.send(pkt)
        except: self.connected = False
    def subscribe(self, topic):
        if not self.connected: return
        try:
            remaining = 2 + 2 + len(topic) + 1
            pkt = bytearray([0x82, remaining, 0, 1, 0, len(topic)])
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

# ── Command Handler ────────────────────────────────────────────────────────
def execute_command(cmd, cfg):
    name = cmd.get("command", "")
    result = {"command": name, "success": False}
    try:
        if name == "NEOPIXEL_FILL":
            r, g, b = int(cmd.get("r", 255)), int(cmd.get("g", 255)), int(cmd.get("b", 255))
            np_fill(r, g, b); result["success"] = True
            result["output"] = f"Filled {NEOPIXEL_COUNT} pixels RGB({r},{g},{b})"
        elif name == "NEOPIXEL_RAINBOW":
            np_rainbow(); result["success"] = True
        elif name == "NEOPIXEL_OFF":
            np_off(); result["success"] = True
        elif name == "NEOPIXEL_BRIGHTNESS":
            cfg["led_brightness"] = float(cmd.get("value", 0.5))
            save_config(cfg); result["success"] = True
        elif name == "NEOPIXEL_PULSE":
            r, g, b = int(cmd.get("r", 0)), int(cmd.get("g", 0)), int(cmd.get("b", 255))
            np_pulse((r, g, b)); result["success"] = True
        elif name == "GET_HEALTH":
            result = get_health(cfg); result["success"] = True
        elif name == "SET_CONFIG":
            for k, v in cmd.items():
                if k in cfg and k != "command": cfg[k] = v
            save_config(cfg); result["success"] = True
        elif name == "REBOOT":
            np_off(); result["success"] = True; machine.reset()
        else: result["error"] = f"Unknown: {name}"
    except Exception as e: result["error"] = str(e)
    return json.dumps(result)

# ── Main ───────────────────────────────────────────────────────────────────
def main():
    print("=== Nirvana Matrix Agent ===")
    cfg = load_config()
    print(f"Device: {cfg['device_id']}")
    np_brand()

    wlan = connect_wifi(cfg)
    if wlan: print(f"WiFi: {wlan.ifconfig()[0]}")
    else: print("WiFi: USB/Serial only")

    mqtt = MiniMQTT(cfg["mqtt_broker"], cfg["mqtt_port"], cfg["device_id"])
    if mqtt.connect():
        print(f"MQTT: {cfg['mqtt_broker']}")
        mqtt.subscribe(f"fleet/cmd/{cfg['device_id']}")
        health = get_health(cfg); health["status"] = "online"
        mqtt.publish(f"fleet/status/{cfg['device_id']}", json.dumps(health))
        np_fill(0, 255, 0)  # Green = connected
    else:
        np_fill(0, 0, 255)  # Blue = no MQTT

    interval = cfg["telemetry_interval"] * 1000; last_poll = 0
    while True:
        now = time.ticks_ms()
        if mqtt.connected:
            msg = mqtt.check()
            if msg:
                try:
                    cmd = json.loads(msg["payload"])
                    response = execute_command(cmd, cfg)
                    mqtt.publish(f"fleet/response/{cfg['device_id']}", response)
                except: pass
        if now - last_poll >= interval:
            if mqtt.connected:
                mqtt.publish(f"fleet/status/{cfg['device_id']}", json.dumps(get_health(cfg)))
            last_poll = now
        time.sleep_ms(100)

if __name__ == "__main__": main()
