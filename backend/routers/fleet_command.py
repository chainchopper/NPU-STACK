"""Fleet Command Orchestrator — natural-language fleet parsing, execution, and templates."""

from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field

from services.edge_discovery import list_registry_devices
from services.fleet_orchestrator import (
        create_command_job,
        execute_command_job,
    get_command_history as get_command_history_service,
        get_command_job,
        get_command_template,
        list_command_templates,
        parse_command as parse_fleet_command,
)

router = APIRouter(prefix="/api/fleet/command", tags=["fleet-command"])


# ── Models ────────────────────────────────────────────────────

class ParseCommandRequest(BaseModel):
    command: str
    context: Optional[Dict] = None  # e.g., user preferences, defaults
    use_agent: bool = True


class ParsedCommand(BaseModel):
    command_text: str
    intent: str  # e.g., "provision", "update_firmware", "get_status", "execute_shell"
    target_devices: List[str]  # device IDs
    action_params: Dict  # action-specific parameters
    confidence: float
    alternatives: List[Dict] = []
    template_id: Optional[str] = None
    reasoning_summary: Optional[str] = None
    tool_context: Dict[str, Any] = Field(default_factory=dict)


class ExecuteCommandRequest(BaseModel):
    parsed_command: ParsedCommand
    dry_run: bool = False


class CommandResult(BaseModel):
    job_id: str
    status: str  # "queued", "executing", "complete", "failed"
    command_text: str
    intent: str
    target_count: int
    results_by_device: Dict[str, Dict]
    created_at: str
    completed_at: Optional[str] = None
    reasoning_summary: Optional[str] = None
    template_id: Optional[str] = None
    tool_context: Dict[str, Any] = Field(default_factory=dict)


@router.post("/parse", response_model=ParsedCommand)
def parse_command(req: ParseCommandRequest):
    """Parse natural language into structured fleet intent, targets, and action params."""
    try:
        parsed = parse_fleet_command(req.command, use_agent=req.use_agent, context=req.context)
        return ParsedCommand(**parsed)
    except Exception as e:
        raise HTTPException(400, f"Failed to parse command: {str(e)}")


@router.post("/execute", response_model=CommandResult)
def execute_command(req: ExecuteCommandRequest, bg_tasks: BackgroundTasks):
    """Queue a parsed fleet command and execute it in the background."""
    parsed_payload = req.parsed_command.model_dump()
    job = create_command_job(parsed_payload, dry_run=req.dry_run)
    bg_tasks.add_task(execute_command_job, job["job_id"], parsed_payload, req.dry_run)
    return CommandResult(**job)


@router.get("/jobs/{job_id}", response_model=CommandResult)
def get_job_status(job_id: str):
    """Poll status of a command job."""
    job = get_command_job(job_id)
    if not job:
        raise HTTPException(404, f"Job '{job_id}' not found")
    return CommandResult(**job)


@router.get("/history")
def get_command_history(limit: int = Query(50, ge=1, le=500)):
    """List recent command execution history."""
    return get_command_history_service(limit)


@router.get("/templates")
def list_templates():
    """Return pre-built fleet recipes/templates for common operations."""
    templates = list_command_templates()
    return {"templates": templates, "count": len(templates)}


@router.post("/templates/{template_id}/parse", response_model=ParsedCommand)
def parse_template(template_id: str, context: Optional[Dict[str, Any]] = None):
    """Instantiate a command template as a parsed fleet command."""
    template = get_command_template(template_id)
    if not template:
        raise HTTPException(404, f"Template '{template_id}' not found")

    selector = template.get("target_selector") or "all"
    prompt = context.get("prompt") if context else template.get("example") or template["label"]
    parsed = parse_fleet_command(str(prompt), use_agent=False, context=context)
    parsed["intent"] = template["intent"]
    parsed["template_id"] = template["id"]
    parsed["action_params"] = {**template.get("action_params", {}), **parsed.get("action_params", {})}
    devices = list_registry_devices(include_low_confidence=False).get("devices", [])
    if selector == "all":
        parsed["target_devices"] = [device.get("id") for device in devices]
    elif selector == "linux":
        parsed["target_devices"] = [
            device.get("id")
            for device in devices
            if str(device.get("tier", "")).lower() == "sbc"
        ]
    return ParsedCommand(**parsed)

# ── Direct Device Command (MQTT bridge) ────────────────────────────────────

class DeviceCommand(BaseModel):
    command: str  # BLINK, READ_SENSORS, GPIO_WRITE, GPIO_READ, EXEC_PYTHON, etc.
    params: Dict[str, Any] = Field(default_factory=dict)

@router.post("/device/{device_id}")
async def send_device_command(device_id: str, cmd: DeviceCommand):
    """Send a command to a specific fleet device via MQTT.
    
    Supported commands vary by device type but include:
    BLINK, READ_SENSORS, GPIO_WRITE, GPIO_READ, EXEC_PYTHON, RESET,
    SET_CONFIG, GET_CONFIG, SHELL (ESP32), EXEC_CODE (Linux).
    """
    payload = {"command": cmd.command, **cmd.params}
    payload["device_id"] = device_id
    
    result = _publish_mqtt_command(device_id, payload)
    if result.get("error"):
        raise HTTPException(502, result["error"])
    return {"device_id": device_id, "command": cmd.command, "sent": True, **result}

def _publish_mqtt_command(device_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Publish a command to a device via MQTT and wait for response."""
    import json as _json
    try:
        import paho.mqtt.client as mqtt
        import threading
        
        response = {"received": False, "data": None}
        lock = threading.Lock()
        
        def on_message(client, userdata, msg):
            with lock:
                response["received"] = True
                try:
                    response["data"] = _json.loads(msg.payload.decode())
                except:
                    response["data"] = {"raw": msg.payload.decode()}
        
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        client.on_message = on_message
        
        # Get MQTT broker from config or use default
        mqtt_broker = os.getenv("NPU_MQTT_BROKER", "127.0.0.1")
        mqtt_port = int(os.getenv("NPU_MQTT_PORT", "1883"))
        
        client.connect(mqtt_broker, mqtt_port, 5)
        client.loop_start()
        
        cmd_topic = f"fleet/cmd/{device_id}"
        resp_topic = f"fleet/response/{device_id}"
        client.subscribe(resp_topic)
        
        client.publish(cmd_topic, _json.dumps(payload))
        
        # Wait up to 5 seconds for response
        timeout = time.time() + 5
        while time.time() < timeout and not response["received"]:
            time.sleep(0.1)
        
        client.loop_stop()
        client.disconnect()
        
        if response["received"]:
            return {"mqtt_response": True, "data": response["data"]}
        else:
            return {"mqtt_response": False, "note": "No response from device (may be offline or processing)"}
            
    except ImportError:
        return {"error": "paho-mqtt not installed. Run: pip install paho-mqtt"}
    except Exception as e:
        return {"error": str(e)}

import os, time
