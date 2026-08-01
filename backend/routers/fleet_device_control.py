"""Device Control Bridge — relay MQTT commands and proxy HTTP to fleet devices.

GET  /api/fleet/device/{device_id}/status   — fetch device /api/status
POST /api/fleet/device/{device_id}/send     — send command via MQTT
GET  /api/fleet/device/{device_id}/web      — proxy AMB82 web UI
"""
from __future__ import annotations

import json
import os
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/fleet/device", tags=["fleet-device-control"])

# ── Config ──
MQTT_COMMAND_TOPIC = os.getenv("NIRVANA_MQTT_COMMAND_TOPIC", "npu-fleet/amb82/command")
MQTT_BROKER = os.getenv("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))


def _publish_mqtt(topic: str, payload: str) -> bool:
    """Publish a message to the local MQTT broker."""
    try:
        import paho.mqtt.client as mqtt
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        client.connect(MQTT_BROKER, MQTT_PORT, 5)
        client.publish(topic, payload)
        client.disconnect()
        return True
    except Exception as e:
        print(f"[DEV-CTRL] MQTT publish failed: {e}")
        return False


@router.get("/{device_id}/status")
async def get_device_status(device_id: str, device_ip: Optional[str] = Query(None)):
    """Fetch device status JSON from the AMB82 web server."""
    if not device_ip:
        raise HTTPException(400, "device_ip query parameter required")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"http://{device_ip}/api/status")
            if r.status_code == 200:
                return r.json()
            return {"error": f"HTTP {r.status_code}", "device": device_id}
    except Exception as e:
        return {"error": str(e), "device": device_id, "reachable": False}


@router.post("/{device_id}/send")
async def send_device_command(
    device_id: str,
    cmd: str = Query(..., description="Command: home, ai, settings, snapshot, etc."),
):
    """Send a command to the device via MQTT."""
    if device_id == "amb82" or device_id.startswith("npu-amb82"):
        payload = json.dumps({"type": "command", "cmd": cmd})
        ok = _publish_mqtt(MQTT_COMMAND_TOPIC, payload)
        return {
            "status": "sent" if ok else "mqtt_failed",
            "device": device_id,
            "command": cmd,
            "topic": MQTT_COMMAND_TOPIC,
        }
    raise HTTPException(404, f"Device {device_id} not recognized for command relay")


@router.get("/{device_id}/web")
async def proxy_device_web(device_id: str, device_ip: Optional[str] = Query(None)):
    """Proxy the AMB82 web UI for embedding in NPU-STACK frontend."""
    if not device_ip:
        raise HTTPException(400, "device_ip query parameter required")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"http://{device_ip}/", follow_redirects=True)
            if r.status_code == 200:
                from fastapi.responses import HTMLResponse
                return HTMLResponse(content=r.text)
            raise HTTPException(502, "Device not reachable")
    except Exception as e:
        raise HTTPException(502, f"Device proxy failed: {e}")
