"""
NIRVANA OS — WiFi provisioning: SoftAP + on-screen QR code + captive portal.

When no WiFi is configured the device:
  1. starts a SoftAP ("Nirvana-Setup")
  2. draws a QR code encoding http://192.168.4.1/ on the round display
  3. serves a tiny HTTP form; the phone scans the QR (or joins the AP),
     enters SSID/password, the device saves config.json and reboots into WiFi.

This mirrors the hotspot/QR provisioning xiaozhi does, with no phone app.
"""
import network
import socket
import time

AP_SSID = "Nirvana-Setup"
PORT = 80


def start_ap():
    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    ap.config(essid=AP_SSID, authmode=network.AUTH_OPEN)
    return ap


def ap_ip():
    ap = network.WLAN(network.AP_IF)
    try:
        return ap.ifconfig()[0]
    except Exception:
        return "192.168.4.1"


def _url_decode(s):
    out = bytearray()
    i = 0
    while i < len(s):
        c = s[i]
        if c == '%' and i + 2 < len(s):
            try:
                out.append(int(s[i + 1:i + 3], 16))
                i += 3
                continue
            except ValueError:
                pass
        elif c == '+':
            out.append(ord(' '))
        else:
            out.append(ord(c))
        i += 1
    return out.decode('utf-8')


def _form_html(ip):
    return ("<!DOCTYPE html><html><body style='font-family:sans-serif'>"
            "<h2>Nirvana OS &mdash; WiFi Setup</h2>"
            "<form method='POST' action='/'>"
            "SSID:<br><input name='ssid'><br>"
            "Password:<br><input name='pass' type='password'><br><br>"
            "<input type='submit' value='Connect'>"
            "</form></body></html>")


def _respond(conn, body, code="200 OK"):
    conn.send(("HTTP/1.1 " + code + "\r\nContent-Type: text/html\r\n"
               "Connection: close\r\n\r\n").encode() + body.encode())


def render_qr(text, lcd, scale=4):
    """Draw a QR code for `text` centred on the framebuffer. Returns pixel size."""
    from uQR import QRCode
    qr = QRCode()
    qr.add_data(text)
    qr.make()
    m = qr.get_matrix()
    size = len(m)
    px = size * scale
    x0 = (lcd.width - px) // 2
    y0 = (lcd.height - px) // 2 - 10
    for r in range(size):
        for c in range(size):
            color = 0x0000 if m[r][c] else 0xFFFF
            lcd.fill_rect(x0 + c * scale, y0 + r * scale, scale, scale, color)
    return x0, y0, px


def run_portal(cfg, save_cb, timeout=300):
    """Serve the config portal until credentials are saved or timeout."""
    ip = ap_ip()
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", PORT))
    s.listen(2)
    s.settimeout(1)
    t0 = time.time()
    try:
        while time.time() - t0 < timeout:
            try:
                conn, addr = s.accept()
            except OSError:
                continue
            try:
                req = conn.recv(1024).decode("utf-8", "ignore")
                if "POST" in req:
                    body = req.split("\r\n\r\n", 1)[-1]
                    params = {}
                    for kv in body.split("&"):
                        if "=" in kv:
                            k, v = kv.split("=", 1)
                            params[k] = v
                    ssid = _url_decode(params.get("ssid", "")).strip()
                    pwd = _url_decode(params.get("pass", "")).strip()
                    if ssid:
                        cfg["wifi_ssid"] = ssid
                        cfg["wifi_pass"] = pwd
                        save_cb(cfg)
                        _respond(conn, "<h2>Saved &mdash; rebooting&hellip;</h2>")
                        conn.close()
                        time.sleep(1)
                        import machine
                        machine.reset()
                        return True
                _respond(conn, _form_html(ip))
            except Exception as e:
                print("[NIRVANA] portal error:", e)
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
    finally:
        s.close()
    return False
