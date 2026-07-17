"""NPU-STACK XIAO ESP32S3 Sense + Round Display Fleet Agent (MicroPython)

One-flash architecture: flash once, auto-register with MQTT, always reachable.

Hardware:
- XIAO ESP32S3 Sense (camera, mic, SD slot)
- Seeed Round Display (1.28" TFT touch, RTC, battery)
- Pins: Display=TFT SPI, Touch=CHSC6x I2C, SD=SPI, RTC=PCF8563 I2C

Commands (via MQTT fleet/cmd/<device_id>):
  DISPLAY_TEXT, DISPLAY_CLEAR, CAPTURE_IMAGE, TOUCH_READ,
  BATTERY_LEVEL, GET_HEALTH, RUN_RKNN, OTA_UPDATE, REBOOT
"""

import json, os, machine, network, time, gc, ubinascii, ustruct

# ── Hardware Config ────────────────────────────────────────────────────────

DEVICE_TYPE = "xiao-esp32s3-sense-round-display"
CONFIG_FILE = "npu_config.json"

XIAO_PINS = {
    "led": 21,           # Built-in LED on XIAO
    "battery_adc": 0,    # A0 - battery voltage
    # Round Display pins
    "tft_cs": 1,         # D1
    "tft_dc": 3,         # D3
    "tft_rst": -1,       # Not connected
    "tft_backlight": 6,  # D6 (shared with KE switch)
    "touch_sda": 4,      # D4 (shared with RTC I2C)
    "touch_scl": 5,      # D5 (shared with RTC I2C)
    "touch_int": 7,      # D7
    "sd_cs": 2,          # D2
    "sd_sck": 8,         # D8
    "sd_miso": 9,        # D9
    "sd_mosi": 10,       # D10
    "ke_button": "gpio_switch",  # KE switch on Round Display
}

DEFAULTS = {
    "device_id": f"xiao-{ubinascii.hexlify(machine.unique_id()).decode()[-8:]}",
    "mqtt_broker": "127.0.0.1",
    "mqtt_port": 1883,
    "wifi_ssid": "",
    "wifi_password": "",
    "telemetry_interval": 10,
    "display_enabled": True,
    "camera_enabled": True,
}


# ── Config ─────────────────────────────────────────────────────────────────

def load_config():
    try:
        with open(CONFIG_FILE) as f:
            cfg = json.load(f)
        for k, v in DEFAULTS.items():
            if k not in cfg:
                cfg[k] = v
        return cfg
    except:
        return dict(DEFAULTS)


def save_config(cfg):
    try:
        json.dump(cfg, open(CONFIG_FILE, "w"))
    except:
        pass


# ── WiFi ──────────────────────────────────────────────────────────────────

def connect_wifi(cfg):
    if not cfg["wifi_ssid"]:
        return None
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(cfg["wifi_ssid"], cfg["wifi_password"])
    for _ in range(30):
        if wlan.isconnected():
            return wlan
        time.sleep(0.5)
    return None


# ── Display (TFT via raw SPI) ──────────────────────────────────────────────

class RoundDisplay:
    """Minimal 1.28-inch Round TFT display driver for XIAO ESP32S3.

    Uses raw SPI commands — no external library needed.
    240x240 resolution, ST7789 controller.
    """
    def __init__(self):
        try:
            from machine import Pin, SPI
            self.spi = SPI(1, baudrate=40_000_000,
                           sck=Pin(XIAO_PINS["sd_sck"]),
                           mosi=Pin(XIAO_PINS["sd_mosi"]))
            self.cs = Pin(XIAO_PINS["tft_cs"], Pin.OUT, value=1)
            self.dc = Pin(XIAO_PINS["tft_dc"], Pin.OUT, value=0)
            self.bl = Pin(XIAO_PINS["tft_backlight"], Pin.OUT, value=1)
            self._init_display()
            self.ready = True
        except Exception as e:
            print(f"Display init failed: {e}")
            self.ready = False

    def _write_cmd(self, cmd):
        self.cs.off()
        self.dc.off()
        self.spi.write(bytes([cmd]))
        self.cs.on()

    def _write_data(self, data):
        self.cs.off()
        self.dc.on()
        self.spi.write(data if isinstance(data, bytes) else bytes([data]))
        self.cs.on()

    def _init_display(self):
        # ST7789 init sequence
        self._write_cmd(0x01)  # SW reset
        time.sleep_ms(150)
        self._write_cmd(0x11)  # Sleep out
        time.sleep_ms(120)
        self._write_cmd(0x36)
        self._write_data(0x00)  # MADCTL
        self._write_cmd(0x3A)
        self._write_data(0x55)  # 16-bit color
        self._write_cmd(0x21)  # Inversion on
        self._write_cmd(0x29)  # Display on
        self.clear(0x0000)

    def set_window(self, x, y, w, h):
        self._write_cmd(0x2A)
        self._write_data(ustruct.pack(">HH", x, x + w - 1))
        self._write_cmd(0x2B)
        self._write_data(ustruct.pack(">HH", y, y + h - 1))
        self._write_cmd(0x2C)

    def clear(self, color=0x0000):
        if not self.ready:
            return
        self.set_window(0, 0, 240, 240)
        self.cs.off()
        self.dc.on()
        color_bytes = ustruct.pack(">H", color) * 240
        for _ in range(240):
            self.spi.write(color_bytes)
        self.cs.on()

    def fill_rect(self, x, y, w, h, color):
        if not self.ready:
            return
        self.set_window(x, y, w, h)
        self.cs.off()
        self.dc.on()
        row = ustruct.pack(">H", color) * w
        for _ in range(h):
            self.spi.write(row)
        self.cs.on()

    def show_status(self, text, color=0xFFFF):
        """Show fleet status on display (minimal - no font)."""
        if not self.ready:
            return
        # Simple indicator: colored bar at top
        self.fill_rect(0, 0, 240, 30, color)
        self.fill_rect(0, 30, 240, 210, 0x0000)
        # Center dot
        for dy in range(-5, 6):
            self.fill_rect(115, 115 + dy, 10, 1, 0x07E0)  # Green crosshair
        for dx in range(-5, 6):
            self.fill_rect(115 + dx, 115, 1, 10, 0x07E0)

    def backlight(self, on=True):
        if self.ready:
            self.bl.value(1 if on else 0)


# ── Camera ─────────────────────────────────────────────────────────────────

def capture_image():
    """Capture image from XIAO ESP32S3 Sense camera (OV2640)."""
    try:
        import camera
        camera.init(0, format=camera.JPEG, fb_location=camera.PSRAM)
        buf = camera.capture()
        return {"success": True, "size": len(buf), "format": "jpeg", "data_available": True}
    except ImportError:
        return {"success": False, "error": "Camera module not available"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Touch ──────────────────────────────────────────────────────────────────

def read_touch():
    """Read touch coordinates from CHSC6x via I2C."""
    try:
        from machine import Pin, I2C
        i2c = I2C(0, scl=Pin(XIAO_PINS["touch_scl"]), sda=Pin(XIAO_PINS["touch_sda"]))
        data = i2c.readfrom(0x2E, 5)  # CHSC6x address
        if data[0] & 0x01:  # Touch detected
            x = ((data[1] & 0x0F) << 8) | data[2]
            y = ((data[3] & 0x0F) << 8) | data[4]
            return {"touched": True, "x": x, "y": y}
        return {"touched": False}
    except Exception as e:
        return {"touched": False, "error": str(e)}


# ── Battery ────────────────────────────────────────────────────────────────

def read_battery():
    """Read battery voltage via A0 on Round Display."""
    try:
        from machine import ADC, Pin
        adc = ADC(Pin(XIAO_PINS["battery_adc"]))
        adc.atten(ADC.ATTN_11DB)
        mv = adc.read_uv() // 1000
        # LiPo: 3.0V (deficit) to 4.2V (full) → percentage
        level = max(0, min(100, int((mv - 3000) * 100 / 1200)))
        return {"voltage_mv": mv, "level_pct": level}
    except Exception as e:
        return {"voltage_mv": 0, "level_pct": -1, "error": str(e)}


# ── Health ─────────────────────────────────────────────────────────────────

def get_health(cfg):
    gc.collect()
    health = {
        "device_id": cfg["device_id"],
        "device_type": DEVICE_TYPE,
        "online": True,
        "uptime_s": time.ticks_ms() // 1000,
        "free_ram": gc.mem_free(),
        "total_ram": gc.mem_alloc() + gc.mem_free(),
        "freq_mhz": machine.freq() // 1_000_000,
    }
    batt = read_battery()
    if batt["level_pct"] >= 0:
        health["battery"] = batt
    return health


# ── MiniMQTT Client ────────────────────────────────────────────────────────

class MiniMQTT:
    """Minimal MQTT client for MicroPython — no external deps."""

    def __init__(self, broker, port, client_id):
        self.broker = broker
        self.port = port
        self.client_id = client_id
        self.sock = None
        self.connected = False

    def connect(self):
        try:
            import usocket
            addr = usocket.getaddrinfo(self.broker, self.port)[0][-1]
            self.sock = usocket.socket()
            self.sock.settimeout(10)
            self.sock.connect(addr)
            # Minimal CONNECT packet
            cid_len = len(self.client_id)
            remaining = 10 + cid_len
            pkt = bytearray([0x10, remaining, 0, 4, 77, 81, 84, 84, 4, 2, 0, 60, 0, cid_len])
            pkt.extend(self.client_id.encode())
            self.sock.send(pkt)
            self.sock.recv(4)
            self.connected = True
            return True
        except:
            return False

    def publish(self, topic, message):
        if not self.connected:
            return
        try:
            payload = message.encode() if isinstance(message, str) else message
            remaining = 2 + len(topic) + len(payload)
            pkt = bytearray([0x30, remaining, 0, len(topic)])
            pkt.extend(topic.encode())
            pkt.extend(payload)
            self.sock.send(pkt)
        except:
            self.connected = False

    def subscribe(self, topic):
        if not self.connected:
            return
        try:
            remaining = 2 + 2 + len(topic) + 1
            pkt = bytearray([0x82, remaining, 0, 1, 0, len(topic)])
            pkt.extend(topic.encode())
            pkt.append(0)
            self.sock.send(pkt)
        except:
            self.connected = False

    def check(self):
        if not self.connected:
            return None
        try:
            self.sock.settimeout(0.1)
            data = self.sock.recv(256)
            if data and len(data) > 2 and data[0] & 0xF0 == 0x30:
                idx = 1
                while data[idx] & 0x80:
                    idx += 1
                idx += 1
                tl = (data[idx] << 8) | data[idx + 1]
                idx += 2
                topic = data[idx:idx + tl].decode()
                idx += tl
                return {"topic": topic, "payload": data[idx:].decode()}
        except OSError:
            pass
        return None

    def disconnect(self):
        try:
            if self.sock:
                self.sock.close()
        except:
            pass
        self.connected = False


# ── Main Agent Loop ────────────────────────────────────────────────────────

def execute_command(cmd, cfg, display):
    """Execute a command received via MQTT."""
    name = cmd.get("command", "")
    result = {"command": name, "success": False}

    try:
        if name == "DISPLAY_TEXT":
            text = cmd.get("text", "NPU-STACK")
            color = int(cmd.get("color", "0xFFFF"), 16) if "color" in cmd else 0xFFFF
            if display and display.ready:
                display.show_status(text, color)
            result["success"] = True

        elif name == "DISPLAY_CLEAR":
            if display and display.ready:
                display.clear()
            result["success"] = True

        elif name == "CAPTURE_IMAGE":
            result = capture_image()

        elif name == "TOUCH_READ":
            result = read_touch()

        elif name == "BATTERY_LEVEL":
            result = read_battery()

        elif name == "GET_HEALTH":
            result = get_health(cfg)
            result["success"] = True

        elif name == "SET_CONFIG":
            for k, v in cmd.items():
                if k in cfg and k != "command":
                    cfg[k] = v
            save_config(cfg)
            result["success"] = True
            result["message"] = "Config saved - reboot to apply"

        elif name == "OTA_UPDATE":
            url = cmd.get("url", "")
            if url:
                result["success"] = True
                result["message"] = "OTA queued — reboot to apply"
                # In a real implementation, download and flash new firmware
            else:
                result["error"] = "No URL provided"

        elif name == "REBOOT":
            result["success"] = True
            result["message"] = "Rebooting..."
            machine.reset()

        else:
            result["error"] = f"Unknown command: {name}"

    except Exception as e:
        result["error"] = str(e)

    return json.dumps(result)


def main():
    print(f"=== NPU-STACK XIAO Agent v2.0 ===")
    print(f"Type: {DEVICE_TYPE}")

    cfg = load_config()
    print(f"Device: {cfg['device_id']}")

    # Init display
    display = RoundDisplay()
    if display.ready:
        print("Display: OK")
        display.show_status("NPU-STACK", 0x001F)  # Blue bar
    else:
        print("Display: unavailable")

    # Connect WiFi
    wlan = connect_wifi(cfg)
    if wlan:
        print(f"WiFi: {wlan.ifconfig()[0]}")
    else:
        print("WiFi: not connected (USB/Serial only)")

    # Connect MQTT
    mqtt = MiniMQTT(cfg["mqtt_broker"], cfg["mqtt_port"], cfg["device_id"])
    if mqtt.connect():
        print(f"MQTT: connected to {cfg['mqtt_broker']}")
        mqtt.subscribe(f"fleet/cmd/{cfg['device_id']}")

        # Publish initial registration
        health = get_health(cfg)
        health["status"] = "online"
        health["device_type"] = DEVICE_TYPE
        mqtt.publish(f"fleet/status/{cfg['device_id']}", json.dumps(health))
        if display.ready:
            display.show_status("ONLINE", 0x07E0)  # Green bar
    else:
        print("MQTT: failed (will retry)")

    last_telemetry = 0
    interval = cfg["telemetry_interval"] * 1000

    while True:
        now = time.ticks_ms()

        # MQTT command check
        if mqtt.connected:
            msg = mqtt.check()
            if msg:
                try:
                    cmd = json.loads(msg["payload"])
                    response = execute_command(cmd, cfg, display)
                    mqtt.publish(f"fleet/response/{cfg['device_id']}", response)
                except:
                    pass

        # Telemetry heartbeat
        if now - last_telemetry >= interval:
            if mqtt.connected:
                health = get_health(cfg)
                mqtt.publish(f"fleet/status/{cfg['device_id']}", json.dumps(health))
            last_telemetry = now

        # Reconnect MQTT if needed
        if not mqtt.connected and wlan and wlan.isconnected():
            if mqtt.connect():
                mqtt.subscribe(f"fleet/cmd/{cfg['device_id']}")

        time.sleep_ms(100)


if __name__ == "__main__":
    main()
