"""
NPU-STACK CircuitPython Agent

A lightweight control/health service intended for boards mounted as CIRCUITPY.
Generated settings are provided through `settings.toml`.
"""

import gc
import json
import os
import socketpool
import time
import wifi
import microcontroller

DEVICE_NAME = os.getenv("DEVICE_NAME") or "nirvana-circuitpython"
AGENT_PORT = int(os.getenv("AGENT_PORT") or "9200")
WIFI_SSID = os.getenv("CIRCUITPY_WIFI_SSID") or ""
WIFI_PASSWORD = os.getenv("CIRCUITPY_WIFI_PASSWORD") or ""


def connect_wifi():
    if not WIFI_SSID:
        print("No Wi-Fi credentials configured in settings.toml")
        return None

    if wifi.radio.ipv4_address:
        return str(wifi.radio.ipv4_address)

    print(f"Connecting to Wi-Fi SSID: {WIFI_SSID}")
    wifi.radio.connect(WIFI_SSID, WIFI_PASSWORD)
    ip = str(wifi.radio.ipv4_address)
    print(f"Wi-Fi connected: {ip}")
    return ip


def get_health():
    gc.collect()
    cpu = getattr(microcontroller, "cpu", None)
    return {
        "status": "healthy",
        "device_name": DEVICE_NAME,
        "agent_port": AGENT_PORT,
        "free_memory_bytes": gc.mem_free(),
        "cpu_temperature_c": getattr(cpu, "temperature", None),
        "uptime_seconds": int(time.monotonic()),
        "ip": str(wifi.radio.ipv4_address) if wifi.radio.ipv4_address else None,
    }


def start_http_server():
    pool = socketpool.SocketPool(wifi.radio)
    server = pool.socket(pool.AF_INET, pool.SOCK_STREAM)
    server.bind(("0.0.0.0", AGENT_PORT))
    server.listen(1)
    server.settimeout(0.2)
    print(f"CircuitPython agent listening on port {AGENT_PORT}")

    while True:
        try:
            client, _ = server.accept()
            try:
                request = client.recv(1024).decode("utf-8")
                first_line = request.split("\r\n", 1)[0]
                parts = first_line.split(" ")
                path = parts[1] if len(parts) > 1 else "/"
                body_dict = get_health() if path in ("/", "/api/health") else {"error": f"Unknown path: {path}"}
                status = "200 OK" if path in ("/", "/api/health") else "404 Not Found"
                body = json.dumps(body_dict)
                response = (
                    f"HTTP/1.1 {status}\r\n"
                    "Content-Type: application/json\r\n"
                    "Access-Control-Allow-Origin: *\r\n"
                    f"Content-Length: {len(body)}\r\n\r\n"
                    f"{body}"
                )
                client.send(response.encode("utf-8"))
            finally:
                client.close()
        except OSError:
            pass
        time.sleep(0.05)


print("Starting NPU-STACK CircuitPython agent")
connect_wifi()
start_http_server()
