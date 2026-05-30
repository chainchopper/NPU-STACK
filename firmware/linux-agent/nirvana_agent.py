"""
Nirvana Edge Agent — Lightweight agent for Linux-based edge NPU devices.

Runs on: Raspberry Pi (+ Hailo/Coral), Orange Pi (RK3588), LuckFox Pico
Provides: Health reporting, mDNS advertisement, WebSocket terminal, OTA updates

Deploy: scp this to the device, then run:
    pip install flask zeroconf websockets
    python nirvana_agent.py
    
Or install as systemd service (see nirvana-agent.service)
"""

import os
import sys
import json
import time
import socket
import platform
import subprocess
import threading
import asyncio
import logging
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timezone

# Configuration
AGENT_VERSION = "0.1.0"
AGENT_PORT = int(os.environ.get("NIRVANA_AGENT_PORT", "9200"))
DEVICE_NAME = os.environ.get("NIRVANA_DEVICE_NAME", socket.gethostname())
DEVICE_ID = os.environ.get("NIRVANA_DEVICE_ID", DEVICE_NAME)
NPU_TYPE = os.environ.get("NIRVANA_NPU_TYPE", "auto")  # auto, rknn, hailo, coral, cpu
COMMAND_CENTER_URL = os.environ.get("NIRVANA_COMMAND_CENTER_URL", "").rstrip("/")
AGENT_SHARED_SECRET = os.environ.get("NIRVANA_AGENT_SHARED_SECRET", "")
HEARTBEAT_INTERVAL_SECONDS = int(os.environ.get("NIRVANA_HEARTBEAT_INTERVAL", "15"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("nirvana-agent")


def _hub_headers() -> dict:
    headers = {"Content-Type": "application/json"}
    if AGENT_SHARED_SECRET:
        headers["X-NPU-Agent-Secret"] = AGENT_SHARED_SECRET
    return headers


def _hub_request(method: str, path: str, payload: dict | None = None, timeout: int = 10) -> dict | None:
    if not COMMAND_CENTER_URL:
        return None

    url = f"{COMMAND_CENTER_URL}{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, headers=_hub_headers(), method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        logger.warning("Command center HTTP %s on %s: %s", exc.code, path, detail)
    except Exception as exc:
        logger.debug("Command center request failed (%s %s): %s", method, path, exc)
    return None


# ── Hardware Detection ────────────────────────────────────────────

def detect_hardware() -> dict:
    """Detect local hardware including NPU accelerators."""
    import psutil

    info = {
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor() or "unknown",
        "cpu_count": psutil.cpu_count(logical=True),
        "cpu_count_physical": psutil.cpu_count(logical=False),
        "memory_total_mb": round(psutil.virtual_memory().total / (1024 ** 2)),
        "memory_available_mb": round(psutil.virtual_memory().available / (1024 ** 2)),
        "disk_total_gb": 0,
        "disk_free_gb": 0,
        "temperature_c": None,
        "npu": None,
        "npu_type": None,
        "npu_tops": 0,
    }

    # Disk
    try:
        disk = psutil.disk_usage("/")
        info["disk_total_gb"] = round(disk.total / (1024 ** 3), 1)
        info["disk_free_gb"] = round(disk.free / (1024 ** 3), 1)
    except Exception:
        pass

    # CPU Temperature
    try:
        temps = psutil.sensors_temperatures()
        if temps:
            for name, entries in temps.items():
                if entries:
                    info["temperature_c"] = entries[0].current
                    break
    except Exception:
        # Fallback: read from thermal zone (common on ARM Linux)
        try:
            with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                info["temperature_c"] = int(f.read().strip()) / 1000.0
        except Exception:
            pass

    # ── NPU Detection ─────────────────────────────────────────────

    # Rockchip RKNN NPU (Orange Pi 5, LuckFox Pico)
    if os.path.exists("/dev/rknpu") or os.path.exists("/sys/class/misc/rknpu"):
        info["npu"] = "rknn"
        info["npu_type"] = "Rockchip RKNN"
        # Detect specific chip
        try:
            with open("/proc/device-tree/compatible", "rb") as f:
                compat = f.read().decode(errors="ignore")
            if "rk3588" in compat:
                info["npu_tops"] = 6.0
                info["npu_type"] = "Rockchip RK3588 RKNN"
            elif "rk3568" in compat:
                info["npu_tops"] = 1.0
                info["npu_type"] = "Rockchip RK3568 RKNN"
            elif "rv1106" in compat or "rv1103" in compat:
                info["npu_tops"] = 0.5
                info["npu_type"] = "Rockchip RV1106 RKNN (LuckFox)"
        except Exception:
            info["npu_tops"] = 1.0

    # Hailo NPU (Raspberry Pi 5 HAT)
    try:
        result = subprocess.run(
            ["hailortcli", "fw-control", "identify"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            info["npu"] = "hailo"
            info["npu_type"] = "Hailo-8L"
            info["npu_tops"] = 13.0
            # Parse version from output
            for line in result.stdout.split("\n"):
                if "Device:" in line:
                    info["npu_type"] = line.split(":")[-1].strip()
    except (FileNotFoundError, Exception):
        pass

    # Google Coral Edge TPU
    try:
        if os.path.exists("/dev/apex_0") or os.path.exists("/sys/class/apex"):
            info["npu"] = "coral"
            info["npu_type"] = "Google Coral Edge TPU"
            info["npu_tops"] = 4.0
    except Exception:
        pass

    # Intel Movidius / OpenVINO
    try:
        result = subprocess.run(
            ["python3", "-c", "from openvino.runtime import Core; c=Core(); print(c.available_devices)"],
            capture_output=True, text=True, timeout=10
        )
        if "MYRIAD" in result.stdout or "NPU" in result.stdout:
            info["npu"] = "openvino"
            info["npu_type"] = "Intel NPU/Movidius"
            info["npu_tops"] = 1.0
    except Exception:
        pass

    # If no NPU detected, mark as CPU-only
    if info["npu"] is None:
        info["npu"] = "cpu"
        info["npu_type"] = "CPU only"
        info["npu_tops"] = 0

    return info


# ── mDNS Advertisement ───────────────────────────────────────────

def start_mdns_advertisement(hw_info: dict):
    """Advertise this device on the local network via mDNS."""
    try:
        from zeroconf import Zeroconf, ServiceInfo
    except ImportError:
        logger.warning("zeroconf not installed — mDNS advertisement disabled")
        return None

    ip = _get_local_ip()
    if not ip:
        logger.warning("Could not determine local IP — mDNS disabled")
        return None

    service_info = ServiceInfo(
        "_nirvana-npu._tcp.local.",
        f"{DEVICE_NAME}._nirvana-npu._tcp.local.",
        addresses=[socket.inet_aton(ip)],
        port=AGENT_PORT,
        properties={
            "version": AGENT_VERSION,
            "family": hw_info.get("machine", "unknown"),
            "chip": hw_info.get("npu_type", "CPU"),
            "npu": str(hw_info.get("npu") != "cpu").lower(),
            "tops": str(hw_info.get("npu_tops", 0)),
            "mem_mb": str(hw_info.get("memory_total_mb", 0)),
        },
        server=f"{DEVICE_NAME}.local.",
    )

    zc = Zeroconf()
    zc.register_service(service_info)
    logger.info(f"mDNS: advertising {DEVICE_NAME} on {ip}:{AGENT_PORT}")
    return zc, service_info


def _get_local_ip() -> str | None:
    """Get the primary local IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


# ── HTTP API ─────────────────────────────────────────────────────

def create_app(hw_info: dict):
    """Create the Flask app with all agent endpoints."""
    try:
        from flask import Flask, request, jsonify
    except ImportError:
        logger.error("Flask not installed. Run: pip install flask")
        sys.exit(1)

    app = Flask(__name__)
    models_dir = Path.home() / ".nirvana" / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    @app.route("/api/health")
    def health():
        return jsonify({
            "status": "healthy",
            "agent_version": AGENT_VERSION,
            "device_id": DEVICE_ID,
            "device_name": DEVICE_NAME,
            "npu_type": hw_info.get("npu_type"),
            "uptime_seconds": time.time() - app.config.get("start_time", time.time()),
        })

    @app.route("/api/hw")
    def hardware():
        # Re-detect for fresh data (temps change)
        fresh = detect_hardware()
        return jsonify(fresh)

    @app.route("/api/models", methods=["GET"])
    def list_models():
        models = []
        for f in models_dir.iterdir():
            if f.is_file():
                models.append({
                    "name": f.name,
                    "path": str(f),
                    "size_mb": round(f.stat().st_size / (1024 ** 2), 2),
                })
        return jsonify({"models": models})

    @app.route("/api/models", methods=["POST"])
    def deploy_model():
        """Accept a model file upload for local inference."""
        if "file" not in request.files:
            return jsonify({"error": "No file in request"}), 400
        f = request.files["file"]
        dest = models_dir / f.filename
        f.save(str(dest))
        return jsonify({
            "status": "deployed",
            "model": f.filename,
            "path": str(dest),
            "size_mb": round(dest.stat().st_size / (1024 ** 2), 2),
        })

    @app.route("/api/exec", methods=["POST"])
    def execute_command():
        """Execute a shell command on the device (use with caution)."""
        data = request.json or {}
        cmd = data.get("command", "")
        if not cmd:
            return jsonify({"error": "No command provided"}), 400

        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=30
            )
            return jsonify({
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
            })
        except subprocess.TimeoutExpired:
            return jsonify({"error": "Command timed out (30s)"}), 408
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/update", methods=["POST"])
    def self_update():
        """OTA self-update — download new agent from Intellify and restart."""
        data = request.json or {}
        update_url = data.get("url")
        if not update_url:
            return jsonify({"error": "No update URL provided"}), 400

        try:
            import urllib.request
            agent_path = os.path.abspath(__file__)
            backup_path = agent_path + ".bak"

            # Backup current version
            import shutil
            shutil.copy2(agent_path, backup_path)

            # Download new version
            urllib.request.urlretrieve(update_url, agent_path)

            return jsonify({
                "status": "updated",
                "backup": backup_path,
                "note": "Restart the agent to apply the update.",
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/config", methods=["GET"])
    def get_config():
        return jsonify({
            "device_id": DEVICE_ID,
            "device_name": DEVICE_NAME,
            "agent_port": AGENT_PORT,
            "npu_type": NPU_TYPE,
            "agent_version": AGENT_VERSION,
            "models_dir": str(models_dir),
            "python_version": sys.version,
        })

    @app.route("/api/logs")
    def get_logs():
        """Return recent system logs."""
        try:
            result = subprocess.run(
                ["journalctl", "-u", "nirvana-agent", "-n", "100", "--no-pager"],
                capture_output=True, text=True, timeout=5
            )
            return jsonify({"logs": result.stdout})
        except Exception:
            return jsonify({"logs": "journalctl not available"})

    app.config["start_time"] = time.time()
    return app


def _local_health_payload(hw_info: dict) -> dict:
    health = {
        "device_id": DEVICE_ID,
        "device_name": DEVICE_NAME,
        "agent_port": AGENT_PORT,
        "agent_version": AGENT_VERSION,
        "host": socket.gethostname(),
        "ip": _get_local_ip(),
        "status": "online",
        "family": hw_info.get("machine") or platform.machine(),
        "chip": hw_info.get("npu_type") or hw_info.get("processor") or "Linux Edge Device",
        "machine": hw_info.get("machine") or platform.machine(),
        "description": hw_info.get("platform"),
        "capabilities": {
            "http_api": True,
            "shell_exec": True,
            "reboot": True,
        },
        "telemetry": {
            "memory_available_mb": hw_info.get("memory_available_mb"),
            "memory_total_mb": hw_info.get("memory_total_mb"),
            "disk_free_gb": hw_info.get("disk_free_gb"),
            "temperature_c": hw_info.get("temperature_c"),
            "npu_type": hw_info.get("npu_type"),
            "npu_tops": hw_info.get("npu_tops"),
        },
        "agent_transport": "polling",
        "transport_preference": "agent-poll",
    }
    return health


def register_with_command_center(hw_info: dict):
    if not COMMAND_CENTER_URL:
        return
    payload = _local_health_payload(hw_info)
    response = _hub_request("POST", "/api/fleet/agent/register", payload=payload, timeout=10)
    if response:
        logger.info("Registered with command center: %s", COMMAND_CENTER_URL)


def _report_heartbeat(hw_info: dict):
    if not COMMAND_CENTER_URL:
        return
    payload = _local_health_payload(detect_hardware())
    _hub_request("POST", "/api/fleet/agent/heartbeat", payload=payload, timeout=10)


def _claim_job() -> dict | None:
    if not COMMAND_CENTER_URL:
        return None
    response = _hub_request("GET", f"/api/fleet/agent/jobs/claim?device_id={DEVICE_ID}", timeout=10)
    if not response or response.get("status") != "job":
        return None
    return response.get("job")


def _report_job_result(job_id: str, result: dict):
    if not COMMAND_CENTER_URL:
        return
    _hub_request("POST", f"/api/fleet/agent/jobs/{job_id}/result?device_id={DEVICE_ID}", payload=result, timeout=15)


def _execute_claimed_job(job: dict) -> dict:
    intent = job.get("intent")
    action_params = job.get("action_params") or {}

    if intent == "shell":
        command = action_params.get("shell_command") or ""
        try:
            completed = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=60)
            return {
                "status": "success" if completed.returncode == 0 else "failed",
                "stdout": completed.stdout,
                "stderr": completed.stderr,
                "exit_code": completed.returncode,
                "transport": "agent-poll",
            }
        except subprocess.TimeoutExpired:
            return {
                "status": "timeout",
                "stdout": "",
                "stderr": "Command timed out after 60 seconds",
                "transport": "agent-poll",
            }

    if intent == "reboot":
        threading.Thread(target=lambda: subprocess.run("sudo reboot", shell=True), daemon=True).start()
        return {"status": "success", "stdout": "Reboot requested", "transport": "agent-poll"}

    if intent == "status":
        return {"status": "success", "transport": "agent-poll", "details": _local_health_payload(detect_hardware())}

    return {"status": "failed", "stderr": f"Unsupported intent: {intent}", "transport": "agent-poll"}


def command_center_loop(hw_info: dict):
    if not COMMAND_CENTER_URL:
        logger.info("Command center URL not configured; remote orchestration loop disabled")
        return

    register_with_command_center(hw_info)
    while True:
        try:
            _report_heartbeat(hw_info)
            job = _claim_job()
            if job:
                logger.info("Claimed job %s (%s)", job.get("job_id"), job.get("intent"))
                result = _execute_claimed_job(job)
                _report_job_result(job.get("job_id"), result)
        except Exception as exc:
            logger.warning("Command center loop error: %s", exc)
        time.sleep(HEARTBEAT_INTERVAL_SECONDS)


# ── Main ─────────────────────────────────────────────────────────

def main():
    logger.info(f"Nirvana Edge Agent v{AGENT_VERSION}")
    logger.info(f"Device: {DEVICE_NAME}")

    # Detect hardware
    logger.info("Detecting hardware...")
    hw = detect_hardware()
    logger.info(f"  CPU: {hw['processor']} ({hw['cpu_count']} threads)")
    logger.info(f"  RAM: {hw['memory_total_mb']} MB")
    logger.info(f"  NPU: {hw['npu_type']} ({hw['npu_tops']} TOPS)")
    if hw.get("temperature_c"):
        logger.info(f"  Temp: {hw['temperature_c']}°C")

    # Start mDNS advertisement
    mdns = start_mdns_advertisement(hw)

    # Start command center loop
    if COMMAND_CENTER_URL:
        threading.Thread(target=command_center_loop, args=(hw,), daemon=True).start()
        logger.info(f"Command center: {COMMAND_CENTER_URL}")

    # Start HTTP API
    app = create_app(hw)
    ip = _get_local_ip() or "0.0.0.0"
    logger.info(f"Agent API: http://{ip}:{AGENT_PORT}/api/health")
    logger.info(f"mDNS: {DEVICE_NAME}._nirvana-npu._tcp.local.")

    try:
        app.run(host="0.0.0.0", port=AGENT_PORT, debug=False)
    finally:
        if mdns:
            zc, service_info = mdns
            zc.unregister_service(service_info)
            zc.close()


if __name__ == "__main__":
    main()
