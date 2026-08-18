"""
NIRVANA OS — branded MicroPython firmware for the NPU-STACK fleet.

Target: Seeed XIAO ESP32-S3 Sense (works on most ESP32-S3 boards).
Firmware: MicroPython ESP32_GENERIC_S3 (newest stable) flashed separately;
          this is the application layer (boot.py + main.py + config.json).

v0.1 — boot, WiFi, backend heartbeat, OTA scaffold, serial setup menu.
       Self-contained: only stdlib MicroPython modules (no mip packages).

Filesystem layout on the device:
  /boot.py            — clock + hostname
  /main.py            — this file
  /config.json        — runtime config (WiFi, backend, device id, OTA channel)
"""
import gc
import json
import machine
import network
import os
import socket
import ssl
import sys
import time

VERSION = "0.1.0"
CONFIG_PATH = "/config.json"

DEFAULTS = {
    "wifi_ssid": "",
    "wifi_pass": "",
    "backend": "http://192.168.1.100:8010",
    "device_id": "xiao-sense-001",
    "update_channel": "",
    "ota_enabled": True,
}


def log(msg):
    print("[NIRVANA] " + msg)


# ── config ──────────────────────────────────────────────────────────────
def load_config():
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, "r") as f:
            cfg.update(json.load(f))
    except Exception:
        pass
    return cfg


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump(cfg, f)
        return True
    except Exception as e:
        log("save_config failed: " + str(e))
        return False


# ── network ─────────────────────────────────────────────────────────────
def connect_wifi(ssid, pwd, timeout=20):
    if not ssid:
        log("no WiFi configured - run setup")
        return None
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        log("connecting to " + ssid)
        wlan.connect(ssid, pwd)
        t = time.time()
        while not wlan.isconnected() and time.time() - t < timeout:
            time.sleep(0.5)
    if wlan.isconnected():
        log("WiFi OK - " + wlan.ifconfig()[0])
        return wlan
    log("WiFi connect failed")
    return None


def http_get(url, timeout=15):
    """Minimal HTTP GET -> (status_code, body_bytes). No external deps."""
    use_ssl = url.startswith("https://")
    url = url.split("://", 1)[1] if "://" in url else url
    if "/" in url:
        host, path = url.split("/", 1)
        path = "/" + path
    else:
        host, path = url, "/"

    try:
        addr = socket.getaddrinfo(host, 443 if use_ssl else 80)[0][-1]
        s = socket.socket()
        s.settimeout(timeout)
        if use_ssl:
            s = ssl.wrap_socket(s, server_hostname=host)
        s.connect(addr)
        s.send(b"GET " + path.encode() + b" HTTP/1.1\r\n"
               b"Host: " + host.encode() + b"\r\n"
               b"Connection: close\r\n\r\n")
        data = b""
        while True:
            chunk = s.recv(1024)
            if not chunk:
                break
            data += chunk
        s.close()
        _head, _sep, body = data.partition(b"\r\n\r\n")
        try:
            status = int(_head.split(b" ")[1])
        except Exception:
            status = -1
        return status, body
    except Exception as e:
        log("http_get error: " + str(e))
        return -1, b""


# ── backend + OTA ───────────────────────────────────────────────────────
def heartbeat(cfg):
    url = cfg["backend"].rstrip("/") + "/api/health"
    status, body = http_get(url)
    log("heartbeat " + url + " -> " + str(status))


def check_ota(cfg):
    if not cfg.get("ota_enabled"):
        return
    channel = cfg.get("update_channel", "").rstrip("/")
    if not channel:
        return
    log("OTA: checking " + channel)
    status, body = http_get(channel + "/version.json", 20)
    if status != 200:
        log("OTA: no manifest (" + str(status) + ")")
        return
    try:
        manifest = json.loads(body)
    except Exception:
        log("OTA: bad manifest")
        return
    latest = manifest.get("version", "")
    if not latest or latest == VERSION:
        log("OTA: up to date (" + VERSION + ")")
        return
    log("OTA: new version " + latest + " (current " + VERSION + ")")
    status, code = http_get(channel + "/" + manifest.get("file", "main.py"), 40)
    if status == 200 and code:
        try:
            with open("/main.py", "wb") as f:
                f.write(code)
            log("OTA: updated main.py - rebooting")
            time.sleep(1)
            machine.reset()
        except Exception as e:
            log("OTA: write failed " + str(e))
    else:
        log("OTA: download failed (" + str(status) + ")")


# ── setup menu ──────────────────────────────────────────────────────────
def setup_menu(cfg):
    log("=== NIRVANA OS first-run setup ===")
    print("No WiFi configured.")
    print("SSID: ", end="")
    ssid = sys.stdin.readline().strip()
    print("Password: ", end="")
    pwd = sys.stdin.readline().strip()
    if ssid:
        cfg["wifi_ssid"] = ssid
        cfg["wifi_pass"] = pwd
        save_config(cfg)


# ── touch loop ──────────────────────────────────────────────────────────
def run_touch_loop(cfg):
    """Poll CHSC6X touch and show taps - foundation for the menu UI."""
    import display
    import touch as touch_mod
    i2c = machine.I2C(0, scl=machine.Pin(5), sda=machine.Pin(4), freq=400000)
    t = touch_mod.Touch(i2c, int_pin=44)
    log("touch ready - tap the screen")
    last = None
    while True:
        p = t.read()
        if p is not None and p != last:
            last = p
            log("touch at %d,%d" % p)
            try:
                display.status("%d,%d" % p, display.YELLOW)
            except Exception:
                pass
        time.sleep_ms(50)


# ── entry ───────────────────────────────────────────────────────────────
def main():
    log("NIRVANA OS v" + VERSION + " booting")
    log("platform=" + sys.platform + " freq=" + str(machine.freq() // 1000000) + "MHz")
    gc.collect()
    log("free mem=" + str(gc.mem_free()))

    cfg = load_config()

    # Round display (GC9A01) — optional, degrades gracefully without it
    if cfg.get("display_enabled", True):
        try:
            import display
            display.splash(VERSION)
            log("display ready (GC9A01 240x240)")
        except Exception as e:
            log("display init failed: " + str(e))

    wlan = connect_wifi(cfg["wifi_ssid"], cfg["wifi_pass"])
    if wlan is None and not cfg["wifi_ssid"]:
        setup_menu(cfg)
        wlan = connect_wifi(cfg["wifi_ssid"], cfg["wifi_pass"])

    if wlan:
        ip = wlan.ifconfig()[0]
        try:
            import display
            display.status(ip, display.GREEN)
        except Exception:
            pass
        heartbeat(cfg)
        check_ota(cfg)

    log("boot complete")
    if cfg.get("display_enabled", True):
        try:
            run_touch_loop(cfg)
        except KeyboardInterrupt:
            raise
        except Exception as e:
            log("touch loop error: " + str(e))
    log("REPL active (Ctrl+C to interrupt)")

main()
