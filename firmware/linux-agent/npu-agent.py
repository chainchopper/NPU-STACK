#!/usr/bin/env python3
"""
NPU-STACK Fleet Agent — Linux (systemd daemon)
===============================================
MQTT telemetry + mDNS discovery + ADB over WiFi + remote command execution + OTA

Place at: /usr/local/bin/npu-agent.py
systemd unit: /etc/systemd/system/npu-agent.service

Commands: EXEC_CODE, READ_SENSORS, GPIO_WRITE, GPIO_READ, RESET,
          SET_CONFIG, GET_CONFIG, ENABLE_ADB, DISABLE_ADB, RESTART, UPDATE
"""
import time, json, os, socket, subprocess, platform, threading
from pathlib import Path

# ── Dependencies (pip install these) ──
try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("ERROR: paho-mqtt not installed. Run: pip install paho-mqtt")
    os._exit(1)

try:
    from zeroconf import ServiceInfo, Zeroconf
    HAS_MDNS = True
except ImportError:
    HAS_MDNS = False

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

# ── Configuration ──────────────────────────────────────────────────────────
CONFIG_PATH = Path("/etc/npu-agent/config.json")
DEFAULTS = {
    "device_id": f"sbc-{socket.gethostname()}",
    "mqtt_broker": "127.0.0.1",
    "mqtt_port": 1883,
    "mqtt_user": "",
    "mqtt_pass": "",
    "adb_enabled": True,
    "adb_port": 5555,
    "telemetry_interval": 5,
    "shell_allowed": True,
    "ota_enabled": True,
}

CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

def load_config():
    try:
        return json.loads(CONFIG_PATH.read_text())
    except:
        cfg = dict(DEFAULTS)
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
        return cfg

def save_config(cfg):
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))

config = load_config()

# ── ADB Control ────────────────────────────────────────────────────────────
def enable_adb():
    """Enable ADB over TCP."""
    try:
        subprocess.run(["adb", "tcpip", str(config["adb_port"])],
                      capture_output=True, timeout=10)
        return True
    except:
        return False

def disable_adb():
    """Disable ADB over TCP."""
    try:
        subprocess.run(["adb", "usb"], capture_output=True, timeout=10)
        return True
    except:
        return False

# ── mDNS Broadcasting ──────────────────────────────────────────────────────
class MDNSBroadcaster:
    def __init__(self):
        self.zc = Zeroconf() if HAS_MDNS else None
        self.info = None

    def start(self):
        if not HAS_MDNS or not self.zc:
            return
        try:
            ip_bytes = socket.inet_aton(get_local_ip())
            self.info = ServiceInfo(
                "_iotcommand._tcp.local.",
                f"{config['device_id']}._iotcommand._tcp.local.",
                addresses=[ip_bytes],
                port=config["adb_port"],
                properties={
                    "type": "SBC",
                    "adb": str(config["adb_enabled"]).lower(),
                    "device_id": config["device_id"],
                },
            )
            self.zc.register_service(self.info)
        except Exception:
            pass

    def stop(self):
        if self.info and self.zc:
            try:
                self.zc.unregister_service(self.info)
            except:
                pass

def get_local_ip():
    """Get the primary local IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

# ── Health / Telemetry ─────────────────────────────────────────────────────
def get_health():
    """Collect system health snapshot."""
    health = {
        "device_id": config["device_id"],
        "hostname": socket.gethostname(),
        "ip": get_local_ip(),
        "online": True,
        "uptime": time.time(),
    }

    if HAS_PSUTIL:
        health.update({
            "cpu_percent": psutil.cpu_percent(interval=1),
            "ram_percent": psutil.virtual_memory().percent,
            "disk_percent": psutil.disk_usage("/").percent,
            "cpu_count": psutil.cpu_count(),
        })

        try:
            temps = psutil.sensors_temperatures()
            if temps:
                for name, entries in temps.items():
                    if entries:
                        health["cpu_temp"] = entries[0].current
                        break
        except:
            pass

    return health

# ── Command Execution ──────────────────────────────────────────────────────
def execute_command(cmd):
    """Execute a remote command and return result."""
    result = {"command": cmd.get("command", "unknown"), "success": False}
    name = cmd.get("command", "")

    try:
        if name == "EXEC_CODE":
            if not config["shell_allowed"]:
                result["output"] = "Shell execution disabled in config"
                return result
            code = cmd.get("code", "")
            shell = cmd.get("shell", False)
            timeout = int(cmd.get("timeout", 30))
            proc = subprocess.run(
                code, shell=shell, capture_output=True, text=True, timeout=timeout
            )
            result["output"] = proc.stdout
            if proc.stderr:
                result["output"] += "\n[stderr]\n" + proc.stderr
            result["exit_code"] = proc.returncode
            result["success"] = proc.returncode == 0

        elif name == "READ_SENSORS":
            result["output"] = json.dumps(get_health())
            result["success"] = True

        elif name == "GPIO_WRITE":
            pin = cmd.get("pin")
            value = int(cmd.get("value", 0))
            os.system(f"gpioset {pin}={value}" if shutil.which("gpioset") else f"echo {value} > /sys/class/gpio/gpio{pin}/value 2>/dev/null")
            result["success"] = True
            result["output"] = f"Pin {pin} -> {value}"

        elif name == "GPIO_READ":
            pin = cmd.get("pin")
            try:
                val = subprocess.run(["gpioget", str(pin)], capture_output=True, text=True)
                result["output"] = val.stdout.strip()
                result["success"] = True
            except:
                result["output"] = "GPIO read failed (gpioget not available?)"

        elif name == "ENABLE_ADB":
            result["success"] = enable_adb()
            result["output"] = f"ADB enabled on port {config['adb_port']}" if result["success"] else "ADB enable failed"

        elif name == "DISABLE_ADB":
            result["success"] = disable_adb()
            result["output"] = "ADB disabled" if result["success"] else "ADB disable failed"

        elif name == "RESTART":
            result["output"] = "Restarting agent..."
            result["success"] = True
            os._exit(0)

        elif name == "REBOOT":
            result["output"] = "Rebooting system..."
            result["success"] = True
            os.system("sudo reboot")

        elif name == "UPDATE":
            url = cmd.get("url", "")
            if url:
                subprocess.run(["wget", "-O", str(CONFIG_PATH.parent / "update.py"), url])
                result["success"] = True
                result["output"] = "Update downloaded, restarting..."
                os._exit(0)

        elif name == "SET_CONFIG":
            for k, v in cmd.items():
                if k in config and k != "command":
                    config[k] = v
            save_config(config)
            result["success"] = True
            result["output"] = "Config updated"

        elif name == "GET_CONFIG":
            result["output"] = json.dumps(config)
            result["success"] = True

        else:
            result["output"] = f"Unknown command: {name}"

    except Exception as e:
        result["output"] = str(e)

    return result


# ── MQTT ───────────────────────────────────────────────────────────────────
TOPIC_STATUS = f"fleet/status/{config['device_id']}"
TOPIC_CMD = f"fleet/cmd/{config['device_id']}"
TOPIC_RESPONSE = f"fleet/response/{config['device_id']}"

def on_connect(client, userdata, flags, reason_code, properties=None):
    client.subscribe(TOPIC_CMD)
    presence = {"event": "online", "device_id": config["device_id"],
               "hostname": socket.gethostname(), "ip": get_local_ip()}
    client.publish(TOPIC_STATUS, json.dumps(presence))

def on_message(client, userdata, msg):
    try:
        cmd = json.loads(msg.payload.decode())
        result = execute_command(cmd)
        client.publish(TOPIC_RESPONSE, json.dumps(result))
    except Exception as e:
        client.publish(TOPIC_RESPONSE, json.dumps({"error": str(e)}))


def main():
    print(f"NPU-STACK Linux Agent | Device: {config['device_id']} | Host: {socket.gethostname()}")

    if config["adb_enabled"]:
        enable_adb()

    mdns = MDNSBroadcaster()
    mdns.start()

    # MQTT client
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=config["device_id"],
    )
    if config["mqtt_user"]:
        client.username_pw_set(config["mqtt_user"], config["mqtt_pass"])
    client.on_connect = on_connect
    client.on_message = on_message

    # Last-will testament: if agent disconnects, broker announces offline
    client.will_set(TOPIC_STATUS, json.dumps({"event": "offline", "device_id": config["device_id"]}), qos=1)

    while True:
        try:
            client.connect(config["mqtt_broker"], config["mqtt_port"], 60)
            client.loop_start()
            break
        except Exception:
            print(f"MQTT connect failed, retrying in 5s...")
            time.sleep(5)

    last_telemetry = 0

    try:
        while True:
            now = time.time()
            if now - last_telemetry > config["telemetry_interval"]:
                last_telemetry = now
                health = get_health()
                client.publish(TOPIC_STATUS, json.dumps(health))

            # Also publish as LWT keepalive (will won't fire while connected)
            time.sleep(config["telemetry_interval"])

    except KeyboardInterrupt:
        pass
    finally:
        client.publish(TOPIC_STATUS, json.dumps({"event": "offline", "device_id": config["device_id"]}))
        client.loop_stop()
        client.disconnect()
        mdns.stop()
        print("Agent stopped")


if __name__ == "__main__":
    main()
