"""
Nirvana Edge Agent — MicroPython firmware for ESP32-S3 / ESP32-C6 / ESP32-P4.

This agent:
  - Connects to WiFi
  - Advertises via mDNS (_nirvana-npu._tcp)
  - Serves a minimal HTTP API for health, exec, OTA
  - Reports chip info, free memory, and temperature

Flash with: esptool.py --port COMx write_flash 0x0 firmware.bin
Then upload this file via: ampy --port COMx put main.py
"""

import os
import gc
import sys
import json
import time
import socket
import network
import machine
import esp32
import esp

# ── Configuration ─────────────────────────────────────────────────
# Override these in config.json on the device

CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "wifi_ssid": "",
    "wifi_password": "",
    "device_name": "nirvana-esp32",
    "agent_port": 9200,
    "hub_url": "",  # e.g., http://192.168.1.100:9090
}


def load_config():
    try:
        with open(CONFIG_FILE, "r") as f:
            cfg = json.load(f)
        # Merge with defaults
        for k, v in DEFAULT_CONFIG.items():
            if k not in cfg:
                cfg[k] = v
        return cfg
    except Exception:
        return dict(DEFAULT_CONFIG)


def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f)


config = load_config()
AGENT_VERSION = "0.1.0-esp"


# ── WiFi ──────────────────────────────────────────────────────────

def connect_wifi(ssid, password, timeout=15):
    """Connect to WiFi, returns IP or None."""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if wlan.isconnected():
        return wlan.ifconfig()[0]

    print(f"WiFi: Connecting to {ssid}...")
    wlan.connect(ssid, password)

    start = time.time()
    while not wlan.isconnected():
        if time.time() - start > timeout:
            print("WiFi: Connection timed out")
            return None
        time.sleep(0.5)

    ip = wlan.ifconfig()[0]
    print(f"WiFi: Connected — {ip}")
    return ip


def scan_wifi():
    """Scan for available WiFi networks."""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    results = []
    for ssid, bssid, channel, rssi, authmode, hidden in wlan.scan():
        results.append({
            "ssid": ssid.decode(),
            "rssi": rssi,
            "channel": channel,
            "secure": authmode > 0,
        })
    return results


# ── mDNS ──────────────────────────────────────────────────────────

def start_mdns(name, ip):
    """Advertise this device via mDNS (if supported by firmware)."""
    try:
        import mdns
        mdns.start(name, "Nirvana Edge Agent")
        print(f"mDNS: {name}.local")
    except ImportError:
        # Fallback: many MicroPython builds don't include mdns
        # The host will still be reachable by IP
        print("mDNS: Not available in this firmware")


# ── Hardware Info ─────────────────────────────────────────────────

def get_hw_info():
    """Return hardware information."""
    info = {
        "chip": sys.platform,
        "machine": os.uname().machine,
        "sysname": os.uname().sysname,
        "version": os.uname().version,
        "freq_mhz": machine.freq() // 1_000_000,
        "flash_size_mb": esp.flash_size() // (1024 * 1024),
        "free_memory_kb": gc.mem_free() // 1024,
        "total_memory_kb": (gc.mem_alloc() + gc.mem_free()) // 1024,
        "temperature_c": None,
        "agent_version": AGENT_VERSION,
        "device_name": config["device_name"],
    }

    # CPU temperature (ESP32-S3, C6 have internal sensor)
    try:
        tf = esp32.raw_temperature()
        info["temperature_c"] = round((tf - 32) * 5 / 9, 1)
    except Exception:
        pass

    # Unique ID (MAC-based)
    try:
        uid = machine.unique_id()
        info["unique_id"] = "".join(["{:02x}".format(b) for b in uid])
    except Exception:
        pass

    return info


# ── Minimal HTTP Server ──────────────────────────────────────────

def parse_request(client):
    """Parse an incoming HTTP request."""
    data = client.recv(4096).decode("utf-8")
    lines = data.split("\r\n")
    if not lines:
        return None, None, None, None

    method, path, _ = lines[0].split(" ", 2)
    headers = {}
    body = ""
    in_body = False
    for line in lines[1:]:
        if in_body:
            body += line
        elif line == "":
            in_body = True
        else:
            if ":" in line:
                k, v = line.split(":", 1)
                headers[k.strip().lower()] = v.strip()

    return method, path, headers, body


def send_response(client, status, body_dict):
    """Send an HTTP JSON response."""
    body = json.dumps(body_dict)
    response = (
        f"HTTP/1.1 {status}\r\n"
        f"Content-Type: application/json\r\n"
        f"Access-Control-Allow-Origin: *\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"\r\n"
        f"{body}"
    )
    client.send(response.encode())


def handle_request(client, method, path, headers, body):
    """Route HTTP requests to handlers."""

    if path == "/api/health":
        send_response(client, "200 OK", {
            "status": "healthy",
            "agent_version": AGENT_VERSION,
            "device_name": config["device_name"],
            "free_memory_kb": gc.mem_free() // 1024,
        })

    elif path == "/api/hw":
        gc.collect()
        send_response(client, "200 OK", get_hw_info())

    elif path == "/api/wifi/scan" and method == "GET":
        networks = scan_wifi()
        send_response(client, "200 OK", {"networks": networks})

    elif path == "/api/config" and method == "GET":
        # Don't expose wifi password
        safe = dict(config)
        safe["wifi_password"] = "***" if safe.get("wifi_password") else ""
        send_response(client, "200 OK", safe)

    elif path == "/api/config" and method == "POST":
        try:
            new_cfg = json.loads(body)
            for k, v in new_cfg.items():
                if k in config:
                    config[k] = v
            save_config(config)
            send_response(client, "200 OK", {"status": "updated"})
        except Exception as e:
            send_response(client, "400 Bad Request", {"error": str(e)})

    elif path == "/api/exec" and method == "POST":
        try:
            data = json.loads(body)
            cmd = data.get("command", "")
            # Execute MicroPython expression
            result = eval(cmd)
            send_response(client, "200 OK", {"result": str(result)})
        except Exception as e:
            send_response(client, "500 Internal Server Error", {"error": str(e)})

    elif path == "/api/reboot" and method == "POST":
        send_response(client, "200 OK", {"status": "rebooting"})
        time.sleep(0.5)
        machine.reset()

    elif path == "/api/gc":
        gc.collect()
        send_response(client, "200 OK", {
            "free_kb": gc.mem_free() // 1024,
            "collected": True,
        })

    else:
        send_response(client, "404 Not Found", {"error": f"Unknown: {method} {path}"})


def start_server(port):
    """Start the HTTP API server."""
    addr = socket.getaddrinfo("0.0.0.0", port)[0][-1]
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(addr)
    s.listen(5)
    s.settimeout(1)  # Non-blocking with 1s timeout for watchdog
    print(f"HTTP API: listening on port {port}")

    while True:
        try:
            client, addr = s.accept()
            try:
                method, path, headers, body = parse_request(client)
                if method and path:
                    handle_request(client, method, path, headers, body)
            except Exception as e:
                print(f"Request error: {e}")
                try:
                    send_response(client, "500 Internal Server Error", {"error": str(e)})
                except Exception:
                    pass
            finally:
                client.close()
        except OSError:
            # Timeout — just loop (allows Ctrl+C and watchdog)
            pass
        except KeyboardInterrupt:
            print("Shutting down...")
            s.close()
            break


# ── LED Status Indicator ─────────────────────────────────────────

def blink(pin_num=2, times=3, delay=0.15):
    """Blink the onboard LED for status indication."""
    try:
        led = machine.Pin(pin_num, machine.Pin.OUT)
        for _ in range(times):
            led.value(1)
            time.sleep(delay)
            led.value(0)
            time.sleep(delay)
    except Exception:
        pass


# ── Main ─────────────────────────────────────────────────────────

def main():
    print("=" * 40)
    print(f"  Nirvana Edge Agent v{AGENT_VERSION}")
    print(f"  Device: {config['device_name']}")
    print("=" * 40)

    # Status blink: starting
    blink(times=2)

    # Connect WiFi
    ip = None
    if config["wifi_ssid"]:
        ip = connect_wifi(config["wifi_ssid"], config["wifi_password"])

    if ip:
        # mDNS
        start_mdns(config["device_name"], ip)
        # Status blink: connected
        blink(times=5, delay=0.05)
        # Start server
        start_server(config["agent_port"])
    else:
        print("No WiFi configured. Enter REPL for setup.")
        print("  import json; open('config.json','w').write(json.dumps({'wifi_ssid':'YOUR_SSID','wifi_password':'YOUR_PASS'}))")
        # Slow blink to indicate waiting
        while True:
            blink(times=1, delay=1)
            time.sleep(3)


# Run
main()
