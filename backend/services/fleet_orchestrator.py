"""Fleet orchestration services for command parsing, transport execution, templates, and mobile agents."""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx

from services.edge_discovery import (
    detect_chip_for_device,
    esp_backup_firmware,
    esp_flash_firmware,
    get_device_from_registry,
    install_prepared_bundle,
    list_prepared_bundles,
    list_registry_devices,
    load_registry,
    prepare_firmware_bundle,
    rp2040_flash_uf2,
    save_registry,
)
from services.gguf_service import chat_completion, get_loaded_models

BACKEND_ROOT = Path(__file__).resolve().parents[1]
MODEL_STORE = BACKEND_ROOT / "data" / "models"
FLEET_STATE_FILE = BACKEND_ROOT / "data" / "fleet_command_state.json"
AGENT_MODEL_FILENAME = "Phi-3-mini-4k-instruct-q4.gguf"
DEFAULT_AGENT_PORT = int(os.getenv("NPU_STACK_AGENT_PORT", "9200"))
DEFAULT_COMMAND_CENTER_URL = os.getenv("NPU_STACK_COMMAND_CENTER_URL", "http://127.0.0.1:8010").rstrip("/")
AGENT_SHARED_SECRET = os.getenv("NPU_STACK_AGENT_SHARED_SECRET", "")
DEFAULT_SSH_USER = os.getenv("NPU_STACK_SSH_USER", "root")
DEFAULT_SSH_KEY_PATH = os.getenv("NPU_STACK_SSH_KEY_PATH", "").strip()
MAX_TELEMETRY_HISTORY = int(os.getenv("NPU_STACK_MAX_TELEMETRY_HISTORY", "200"))

_registry_lock = threading.Lock()
_command_lock = threading.Lock()
_command_history: list[dict[str, Any]] = []
_command_jobs: dict[str, dict[str, Any]] = {}
_pending_agent_jobs: dict[str, list[dict[str, Any]]] = {}
_telemetry_history: dict[str, list[dict[str, Any]]] = {}

DEVICE_FAMILY_KEYWORDS = {
    "esp32": ["esp32", "esp32-s2", "esp32-s3", "esp32-c3", "esp32-c6", "esp32-h2", "esp32-p4", "esp8266"],
    "rp2040": ["rp2040", "rp2350", "pico", "circuitpython"],
    "linux": ["rockchip", "allwinner", "rpi-sbc", "nvidia", "coral", "movidius", "qualcomm"],
}

INTENT_KEYWORDS = {
    "status": ["status", "health", "check", "audit", "list", "query", "show"],
    "telemetry": ["telemetry", "metrics", "sensor", "monitor", "stats"],
    "provision": ["provision", "setup", "configure", "pair", "prepare", "install agent"],
    "firmware": ["firmware", "flash", "upgrade", "update firmware", "backup"],
    "reboot": ["reboot", "restart", "reset", "power cycle"],
    "shell": ["run", "execute", "shell", "ssh", "command", "deploy training"],
    "espnow": ["espnow", "esp-now", "esp_now", "esp now", "mesh deploy", "coin cell", "esp mesh"],
}

FLEET_TEMPLATES: dict[str, dict[str, Any]] = {
    "fleet-health-audit": {
        "id": "fleet-health-audit",
        "label": "Fleet Health Audit",
        "description": "Query health and hardware state across the fleet.",
        "intent": "status",
        "target_selector": "all",
        "action_params": {"include_hardware": True},
        "example": "audit the whole fleet",
        "keywords": ["audit fleet", "fleet health", "fleet status", "check all devices"],
    },
    "backup-flash-verify": {
        "id": "backup-flash-verify",
        "label": "Backup, Flash, Verify",
        "description": "Run a staged firmware workflow with backup and verification.",
        "intent": "firmware",
        "target_selector": "all",
        "action_params": {"backup_before_update": True, "verify_after_flash": True},
        "example": "backup flash and verify esp32 devices using firmware.bin",
        "keywords": ["backup flash verify", "roll out firmware", "firmware workflow"],
    },
    "linux-agent-rollout": {
        "id": "linux-agent-rollout",
        "label": "Roll Out Linux Agent",
        "description": "Prepare Linux edge-agent bundles for SBC devices.",
        "intent": "provision",
        "target_selector": "linux",
        "action_params": {"profile_id": "linux-agent", "install_after_prepare": False},
        "example": "deploy the linux agent to all sbcs",
        "keywords": ["linux agent", "edge agent", "deploy agent"],
    },
    "deploy-training-job": {
        "id": "deploy-training-job",
        "label": "Deploy Training Job",
        "description": "Dispatch a training worker command to edge Linux devices.",
        "intent": "shell",
        "target_selector": "linux",
        "action_params": {
            "shell_command": "python3 /opt/npu-stack/edge_worker.py --mode training",
            "workflow": "deploy-training",
        },
        "example": "deploy a training job to all edge devices",
        "keywords": ["deploy training", "training worker", "edge training"],
    },
    "espnow-deploy": {
        "id": "espnow-deploy",
        "label": "Deploy ESP-NOW Firmware",
        "description": "Build and flash an ESP-NOW example to a fleet ESP32 device.",
        "intent": "espnow",
        "target_selector": "esp32",
        "action_params": {"example": "get-started", "target": "esp32", "build_before_flash": True},
        "example": "deploy coin_cell_demo espnow firmware to esp32 devices",
        "keywords": ["espnow", "esp-now", "esp now", "mesh", "coin cell", "deploy mesh"],
    },
}


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _load_command_state() -> None:
    if not FLEET_STATE_FILE.exists():
        return
    try:
        payload = json.loads(FLEET_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return

    with _command_lock:
        _command_history.clear()
        _command_history.extend(payload.get("command_history") or [])
        _command_jobs.clear()
        _command_jobs.update(payload.get("command_jobs") or {})
        _pending_agent_jobs.clear()
        _pending_agent_jobs.update(payload.get("pending_agent_jobs") or {})
        _telemetry_history.clear()
        for device_id, snapshots in (payload.get("telemetry_history") or {}).items():
            if isinstance(snapshots, list):
                _telemetry_history[str(device_id)] = snapshots[-MAX_TELEMETRY_HISTORY:]


def _save_command_state() -> None:
    with _command_lock:
        payload = {
            "command_history": deepcopy(_command_history),
            "command_jobs": deepcopy(_command_jobs),
            "pending_agent_jobs": deepcopy(_pending_agent_jobs),
            "telemetry_history": deepcopy(_telemetry_history),
        }
    try:
        FLEET_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        FLEET_STATE_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception:
        return


def _registry_devices() -> list[dict[str, Any]]:
    return list(load_registry().get("devices", {}).values())


def record_device_telemetry(device_id: str, telemetry: Optional[dict[str, Any]], *, source: str = "heartbeat", metadata: Optional[dict[str, Any]] = None) -> Optional[dict[str, Any]]:
    telemetry = telemetry or {}
    metadata = metadata or {}
    if not telemetry and not metadata:
        return None

    snapshot = {
        "device_id": device_id,
        "recorded_at": utcnow_iso(),
        "source": source,
        "telemetry": deepcopy(telemetry),
        "metadata": deepcopy(metadata),
    }

    with _command_lock:
        history = _telemetry_history.setdefault(device_id, [])
        history.append(snapshot)
        if len(history) > MAX_TELEMETRY_HISTORY:
            del history[:-MAX_TELEMETRY_HISTORY]
    _save_command_state()
    return deepcopy(snapshot)


def get_device_telemetry(device_id: str, *, limit: int = 50) -> dict[str, Any]:
    device = get_device_from_registry(device_id)
    if not device:
        raise KeyError(f"Device '{device_id}' not found")

    with _command_lock:
        history = deepcopy((_telemetry_history.get(device_id) or [])[-max(1, limit):])

    registry_telemetry = deepcopy(device.get("telemetry") or {})
    latest = deepcopy(history[-1]) if history else None
    if not latest and registry_telemetry:
        latest = {
            "device_id": device_id,
            "recorded_at": device.get("last_agent_seen_at") or device.get("last_seen") or utcnow_iso(),
            "source": "registry",
            "telemetry": registry_telemetry,
            "metadata": {"status": device.get("status")},
        }

    return {
        "device_id": device_id,
        "device": device,
        "latest": latest,
        "history": history,
        "history_count": len(history),
        "registry_telemetry": registry_telemetry,
    }


def query_device_telemetry(device_id: str, *, limit: int = 50, refresh: bool = False) -> dict[str, Any]:
    device = get_device_from_registry(device_id)
    if not device:
        raise KeyError(f"Device '{device_id}' not found")

    if refresh:
        status_result = _execute_status(device)
        if status_result.get("status") == "success":
            record_device_telemetry(
                device_id,
                {
                    "health": status_result.get("health") or {},
                    "hardware": status_result.get("hardware") or {},
                    "registry_telemetry": deepcopy(device.get("telemetry") or {}),
                },
                source=status_result.get("transport") or "status-query",
            )

    return get_device_telemetry(device_id, limit=limit)


def list_command_templates() -> list[dict[str, Any]]:
    return [deepcopy(template) for template in FLEET_TEMPLATES.values()]


def get_command_template(template_id: str) -> Optional[dict[str, Any]]:
    template = FLEET_TEMPLATES.get(template_id)
    return deepcopy(template) if template else None


def _target_selector_devices(selector: str, devices: list[dict[str, Any]]) -> list[str]:
    normalized = (selector or "").strip().lower()
    if normalized in {"all", "fleet"}:
        return [device["id"] for device in devices]
    if normalized in {"paired", "managed"}:
        return [device["id"] for device in devices if device.get("paired")]
    if normalized in {"online", "reachable"}:
        return [device["id"] for device in devices if device.get("status") in {"online", "reachable", "mounted", "detected"}]
    if normalized in DEVICE_FAMILY_KEYWORDS:
        families = set(DEVICE_FAMILY_KEYWORDS[normalized])
        return [device["id"] for device in devices if str(device.get("family", "")).lower() in families]
    return []


def _match_template(command_text: str) -> Optional[dict[str, Any]]:
    lowered = command_text.lower()
    for template in FLEET_TEMPLATES.values():
        if template["id"] in lowered:
            return deepcopy(template)
        if any(keyword in lowered for keyword in template.get("keywords", [])):
            return deepcopy(template)
    return None


def _extract_shell_command(command_text: str) -> Optional[str]:
    quoted = re.findall(r'"([^"]+)"|\'([^\']+)\'', command_text)
    for first, second in quoted:
        value = first or second
        if value:
            return value.strip()

    if ":" in command_text:
        tail = command_text.split(":", 1)[1].strip()
        if tail:
            return tail

    match = re.search(r"(?:run|execute|ssh|command)\s+(.+)$", command_text, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def _extract_firmware_path(command_text: str) -> Optional[str]:
    match = re.search(r"([A-Za-z]:\\[^\s]+\.(?:bin|uf2|zip)|/[^\s]+\.(?:bin|uf2|zip)|[^\s]+\.(?:bin|uf2|zip))", command_text)
    return match.group(1).strip() if match else None


def _resolve_target_devices(command_text: str, devices: list[dict[str, Any]]) -> list[str]:
    lowered = command_text.lower()
    targets: list[str] = []

    if " all " in f" {lowered} " or lowered.startswith("all "):
        return [device["id"] for device in devices]

    for selector in ["esp32", "rp2040", "linux", "paired", "online"]:
        if selector in lowered:
            targets.extend(_target_selector_devices(selector, devices))

    for device in devices:
        device_id = str(device.get("id", ""))
        nickname = str(device.get("nickname", ""))
        chip = str(device.get("chip", ""))
        family = str(device.get("family", ""))
        host = str(device.get("host", ""))
        candidates = [device_id.lower(), nickname.lower(), chip.lower(), family.lower(), host.lower()]
        if any(candidate and candidate in lowered for candidate in candidates):
            targets.append(device_id)

    deduped = []
    seen = set()
    for target in targets:
        if target and target not in seen:
            deduped.append(target)
            seen.add(target)

    if deduped:
        return deduped

    online = [device["id"] for device in devices if device.get("status") in {"online", "reachable", "mounted", "detected"}]
    return online[:1] if online else ([devices[0]["id"]] if devices else [])


def _heuristic_parse(command_text: str) -> dict[str, Any]:
    devices = _registry_devices()
    lowered = command_text.lower()
    matched_template = _match_template(command_text)
    detected_intent = matched_template["intent"] if matched_template else "status"

    for intent, keywords in INTENT_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            detected_intent = intent
            break

    targets = _resolve_target_devices(command_text, devices)
    action_params: dict[str, Any] = {}
    if matched_template:
        action_params.update(deepcopy(matched_template.get("action_params", {})))

    if detected_intent == "shell":
        action_params.setdefault("shell_command", _extract_shell_command(command_text) or matched_template and matched_template.get("action_params", {}).get("shell_command") or "")
    if detected_intent == "telemetry":
        action_params.setdefault("refresh", any(keyword in lowered for keyword in ["live", "refresh", "poll"]))
        action_params.setdefault("limit", 20)
    if detected_intent == "firmware":
        action_params.setdefault("backup_before_update", True)
        action_params.setdefault("verify_after_flash", True)
        firmware_path = _extract_firmware_path(command_text)
        if firmware_path:
            action_params["firmware_path"] = firmware_path
    if detected_intent == "provision":
        action_params.setdefault("install_after_prepare", "install" in lowered or "copy" in lowered)
        if "linux agent" in lowered:
            action_params.setdefault("profile_id", "linux-agent")

    alternatives = [
        {"template_id": template["id"], "label": template["label"]}
        for template in list_command_templates()[:3]
        if not matched_template or template["id"] != matched_template["id"]
    ]

    return {
        "command_text": command_text,
        "intent": detected_intent,
        "target_devices": targets or ["_no_match"],
        "action_params": action_params,
        "confidence": 0.62 if targets else 0.3,
        "alternatives": alternatives,
        "template_id": matched_template["id"] if matched_template else None,
        "reasoning_summary": "Heuristic parser selected the most likely fleet intent and targets.",
        "tool_context": build_tool_context(include_jobs=False),
    }


def build_tool_context(include_jobs: bool = True) -> dict[str, Any]:
    fleet_status = list_registry_devices(include_low_confidence=False)
    context: dict[str, Any] = {
        "query-fleet-status": {
            "total_devices": fleet_status["count"],
            "paired_count": fleet_status["paired_count"],
            "available_count": fleet_status["available_count"],
            "devices": [
                {
                    "id": device.get("id"),
                    "family": device.get("family"),
                    "chip": device.get("chip"),
                    "status": device.get("status"),
                    "paired": device.get("paired"),
                    "available": device.get("available"),
                    "connection": device.get("connection"),
                    "agent_installed": device.get("agent_installed"),
                }
                for device in fleet_status["devices"]
            ],
        },
        "query-fleet-telemetry": {
            "devices": [
                {
                    "id": device.get("id"),
                    "telemetry_keys": sorted(list((device.get("telemetry") or {}).keys())),
                    "has_history": bool(_telemetry_history.get(device.get("id"))),
                    "last_agent_seen_at": device.get("last_agent_seen_at"),
                }
                for device in fleet_status["devices"]
            ]
        },
        "list-fleet-templates": list_command_templates(),
    }
    if include_jobs:
        with _command_lock:
            context["monitor-fleet-job"] = {
                "active_jobs": [
                    {
                        "job_id": job["job_id"],
                        "status": job["status"],
                        "intent": job["intent"],
                        "target_count": job["target_count"],
                    }
                    for job in _command_jobs.values()
                    if job.get("status") in {"queued", "executing"}
                ]
            }
    return context


def _phi_agent_model_path() -> Path:
    return MODEL_STORE / AGENT_MODEL_FILENAME


def _phi_agent_loaded() -> bool:
    return any(model.get("filename") == AGENT_MODEL_FILENAME for model in get_loaded_models()) and _phi_agent_model_path().exists()


def _extract_json_payload(text: str) -> Optional[dict[str, Any]]:
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    snippet = text[start:end + 1]
    try:
        return json.loads(snippet)
    except Exception:
        return None


def _agent_parse(command_text: str, context: Optional[dict[str, Any]] = None) -> Optional[dict[str, Any]]:
    if not _phi_agent_loaded():
        return None

    tool_context = build_tool_context(include_jobs=True)
    if context:
        tool_context["user_context"] = context

    system_prompt = (
        "You are a fleet orchestration planner for NPU-STACK. "
        "Use the provided tool outputs to determine the best intent, targets, and action parameters. "
        "Return JSON only with keys: intent, target_devices, action_params, confidence, reasoning_summary, template_id, alternatives. "
        "Valid intents: status, telemetry, provision, firmware, reboot, shell, espnow. "
        "Only select target device ids that exist in query-fleet-status.devices."
    )
    user_prompt = (
        f"Command: {command_text}\n\n"
        f"Tool outputs:\n{json.dumps(tool_context, indent=2)}\n\n"
        "Return strict JSON only."
    )

    response = chat_completion(
        model_path=str(_phi_agent_model_path()),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
        max_tokens=384,
    )
    content = (((response or {}).get("choices") or [{}])[0].get("message") or {}).get("content", "")
    payload = _extract_json_payload(content)
    if not payload:
        return None

    devices = {device["id"] for device in _registry_devices()}
    payload["target_devices"] = [device_id for device_id in payload.get("target_devices", []) if device_id in devices]
    payload.setdefault("action_params", {})
    payload.setdefault("confidence", 0.75)
    payload.setdefault("alternatives", [])
    payload.setdefault("reasoning_summary", "Phi-3 reviewed fleet context before choosing an action.")
    payload.setdefault("template_id", None)
    return {
        "command_text": command_text,
        "intent": str(payload.get("intent") or "status"),
        "target_devices": payload.get("target_devices") or ["_no_match"],
        "action_params": payload.get("action_params") or {},
        "confidence": float(payload.get("confidence") or 0.75),
        "alternatives": payload.get("alternatives") or [],
        "template_id": payload.get("template_id"),
        "reasoning_summary": payload.get("reasoning_summary"),
        "tool_context": tool_context,
    }


def parse_command(command_text: str, use_agent: bool = True, context: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    parsed = _agent_parse(command_text, context=context) if use_agent else None
    if parsed:
        return parsed
    return _heuristic_parse(command_text)


def get_command_history(limit: int = 50) -> dict[str, Any]:
    with _command_lock:
        history = _command_history[-limit:]
    return {"history": history, "total_commands": len(_command_history)}


def get_command_job(job_id: str) -> Optional[dict[str, Any]]:
    with _command_lock:
        job = _command_jobs.get(job_id)
        return deepcopy(job) if job else None


def _save_registered_device(device_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    with _registry_lock:
        registry = load_registry()
        devices = registry.setdefault("devices", {})
        existing = devices.get(device_id, {})
        now = utcnow_iso()
        device = {
            **existing,
            **updates,
            "id": device_id,
            "first_seen": existing.get("first_seen") or now,
            "last_seen": now,
            "discovered_at": existing.get("discovered_at") or now,
            "agent_installed": True,
            "paired": True,
            "management_state": updates.get("management_state", existing.get("management_state") or "managed"),
        }
        devices[device_id] = device
        registry["last_scan"] = now
        save_registry(registry)
    refreshed = get_device_from_registry(device_id)
    return refreshed or device


def register_mobile_agent(payload: dict[str, Any]) -> dict[str, Any]:
    device_id = str(payload.get("device_id") or payload.get("device_name") or f"agent-{uuid.uuid4().hex[:8]}")
    host = payload.get("host") or payload.get("ip")
    port = int(payload.get("agent_port") or DEFAULT_AGENT_PORT)
    endpoint = payload.get("agent_endpoint") or (f"http://{host}:{port}" if host else None)
    updates = {
        "nickname": payload.get("device_name") or payload.get("nickname") or "",
        "family": payload.get("family") or payload.get("machine") or "linux",
        "chip": payload.get("chip") or payload.get("npu_type") or payload.get("family") or "Edge Agent",
        "connection": payload.get("connection") or "wifi",
        "status": payload.get("status") or "online",
        "host": payload.get("host"),
        "ip": payload.get("ip"),
        "agent_port": port,
        "agent_endpoint": endpoint,
        "last_agent_seen_at": utcnow_iso(),
        "agent_transport": payload.get("agent_transport") or "polling",
        "transport_preference": payload.get("transport_preference") or "agent-poll",
        "firmware_version": payload.get("agent_version") or payload.get("firmware_version") or "",
        "capabilities": payload.get("capabilities") or {},
        "machine": payload.get("machine"),
        "description": payload.get("description") or payload.get("npu_type") or "Mobile agent",
        "telemetry": payload.get("telemetry") or {},
    }
    device = _save_registered_device(device_id, updates)
    record_device_telemetry(device_id, updates.get("telemetry") or {}, source="agent-register", metadata={"status": updates.get("status")})
    return {"status": "registered", "device": device}


def heartbeat_mobile_agent(payload: dict[str, Any]) -> dict[str, Any]:
    device_id = str(payload.get("device_id") or "")
    if not device_id:
        raise ValueError("device_id is required")

    telemetry = payload.get("telemetry") or {}
    host = payload.get("host") or payload.get("ip")
    port = int(payload.get("agent_port") or DEFAULT_AGENT_PORT)
    endpoint = payload.get("agent_endpoint") or (f"http://{host}:{port}" if host else None)
    updates = {
        "status": payload.get("status") or "online",
        "host": payload.get("host"),
        "ip": payload.get("ip"),
        "agent_port": port,
        "agent_endpoint": endpoint,
        "last_agent_seen_at": utcnow_iso(),
        "telemetry": telemetry,
        "firmware_version": payload.get("firmware_version") or payload.get("agent_version") or "",
        "description": payload.get("description"),
    }
    device = _save_registered_device(device_id, updates)
    record_device_telemetry(device_id, telemetry, source="agent-heartbeat", metadata={"status": updates.get("status")})
    return {"status": "ok", "device": device}


def _resolve_agent_endpoint(device: dict[str, Any]) -> Optional[str]:
    if device.get("agent_endpoint"):
        return str(device["agent_endpoint"]).rstrip("/")
    host = device.get("ip") or device.get("host")
    if not host:
        return None
    port = int(device.get("agent_port") or DEFAULT_AGENT_PORT)
    return f"http://{host}:{port}"


def _http_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if AGENT_SHARED_SECRET:
        headers["X-NPU-Agent-Secret"] = AGENT_SHARED_SECRET
    return headers


def _http_request(method: str, url: str, *, payload: Optional[dict[str, Any]] = None, timeout: float = 15.0) -> dict[str, Any]:
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        response = client.request(method, url, json=payload, headers=_http_headers())
        response.raise_for_status()
        if not response.text.strip():
            return {}
        return response.json()


def _ssh_command(device: dict[str, Any], command: str, timeout: int = 30) -> dict[str, Any]:
    host = device.get("ip") or device.get("host")
    if not host:
        return {"status": "failed", "transport": "ssh", "error": "No host/IP available for SSH transport"}

    ssh_user = device.get("ssh_user") or DEFAULT_SSH_USER
    if not ssh_user:
        return {"status": "failed", "transport": "ssh", "error": "SSH user is not configured"}

    ssh_cmd = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=10"]
    if DEFAULT_SSH_KEY_PATH:
        ssh_cmd.extend(["-i", DEFAULT_SSH_KEY_PATH])
    ssh_cmd.append(f"{ssh_user}@{host}")
    ssh_cmd.append(command)

    try:
        completed = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=timeout, check=False)
        return {
            "status": "success" if completed.returncode == 0 else "failed",
            "transport": "ssh",
            "exit_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "command": command,
        }
    except FileNotFoundError:
        return {"status": "failed", "transport": "ssh", "error": "OpenSSH client is not installed on this host"}
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "transport": "ssh", "error": f"SSH command timed out after {timeout}s", "command": command}
    except Exception as exc:
        return {"status": "failed", "transport": "ssh", "error": str(exc), "command": command}


def _queue_mobile_agent_job(device: dict[str, Any], parent_job: dict[str, Any], intent: str, action_params: dict[str, Any]) -> dict[str, Any]:
    device_id = device["id"]
    queued_job = {
        "job_id": parent_job["job_id"],
        "intent": intent,
        "action_params": deepcopy(action_params),
        "command_text": parent_job["command_text"],
        "queued_at": utcnow_iso(),
    }
    with _command_lock:
        _pending_agent_jobs.setdefault(device_id, []).append(queued_job)
    _save_command_state()
    return {
        "status": "queued_for_agent",
        "transport": "agent-poll",
        "message": "Job queued for the device-side mobile agent.",
        "queued_at": queued_job["queued_at"],
    }


def claim_mobile_agent_job(device_id: str) -> dict[str, Any]:
    with _command_lock:
        queue = _pending_agent_jobs.get(device_id) or []
        if not queue:
            return {"status": "empty"}
        job = queue.pop(0)
        if not queue:
            _pending_agent_jobs.pop(device_id, None)
        command_job = _command_jobs.get(job["job_id"])
        if command_job:
            command_job.setdefault("results_by_device", {}).setdefault(device_id, {})
            command_job["results_by_device"][device_id].update({
                "status": "agent_claimed",
                "transport": "agent-poll",
                "claimed_at": utcnow_iso(),
            })
    _save_command_state()
    return {"status": "job", "job": job}


def _refresh_job_status(job: dict[str, Any]) -> None:
    results = list((job.get("results_by_device") or {}).values())
    statuses = {str(result.get("status")) for result in results if isinstance(result, dict)}
    if not results:
        return
    if statuses & {"queued_for_agent", "agent_claimed", "executing"}:
        job["status"] = "executing"
        job["completed_at"] = None
        return
    if statuses and statuses <= {"success", "complete", "queried", "dry_run", "manual-step-required", "skipped"}:
        job["status"] = "complete"
        job["completed_at"] = job.get("completed_at") or utcnow_iso()
        return
    if "failed" in statuses or "error" in statuses or "timeout" in statuses:
        job["status"] = "failed"
        job["completed_at"] = job.get("completed_at") or utcnow_iso()
        return
    job["status"] = "complete"
    job["completed_at"] = job.get("completed_at") or utcnow_iso()


def report_mobile_agent_job_result(device_id: str, job_id: str, result: dict[str, Any]) -> dict[str, Any]:
    with _command_lock:
        job = _command_jobs.get(job_id)
        if not job:
            raise KeyError(f"Job '{job_id}' not found")
        job.setdefault("results_by_device", {})[device_id] = {
            **result,
            "reported_at": utcnow_iso(),
            "transport": result.get("transport") or "agent-poll",
        }
        _refresh_job_status(job)
        updated = deepcopy(job)
    _save_command_state()
    return updated


def _status_via_http(device: dict[str, Any]) -> dict[str, Any]:
    endpoint = _resolve_agent_endpoint(device)
    if not endpoint:
        return {"status": "failed", "transport": "http-agent", "error": "No agent endpoint available"}
    try:
        health = _http_request("GET", f"{endpoint}/api/health", timeout=8)
        hardware = {}
        try:
            hardware = _http_request("GET", f"{endpoint}/api/hw", timeout=10)
        except Exception:
            hardware = {}
        record_device_telemetry(
            device["id"],
            {
                "health": health,
                "hardware": hardware,
                "registry_telemetry": deepcopy(device.get("telemetry") or {}),
            },
            source="http-agent-status",
        )
        return {"status": "success", "transport": "http-agent", "health": health, "hardware": hardware}
    except Exception as exc:
        return {"status": "failed", "transport": "http-agent", "error": str(exc)}


def _execute_shell(device: dict[str, Any], action_params: dict[str, Any], parent_job: dict[str, Any]) -> dict[str, Any]:
    command = str(action_params.get("shell_command") or "").strip()
    if not command:
        return {"status": "failed", "error": "No shell command provided"}

    if device.get("transport_preference") == "agent-poll":
        return _queue_mobile_agent_job(device, parent_job, "shell", {"shell_command": command})

    endpoint = _resolve_agent_endpoint(device)
    if endpoint:
        try:
            response = _http_request("POST", f"{endpoint}/api/exec", payload={"command": command}, timeout=float(action_params.get("timeout_seconds") or 30))
            return {
                "status": "success" if response.get("returncode", 0) == 0 and not response.get("error") else "failed",
                "transport": "http-agent",
                "command": command,
                **response,
            }
        except Exception:
            pass

    return _ssh_command(device, command, timeout=int(action_params.get("timeout_seconds") or 30))


def _execute_reboot(device: dict[str, Any], parent_job: dict[str, Any]) -> dict[str, Any]:
    if device.get("transport_preference") == "agent-poll":
        return _queue_mobile_agent_job(device, parent_job, "reboot", {})

    endpoint = _resolve_agent_endpoint(device)
    if endpoint:
        try:
            response = _http_request("POST", f"{endpoint}/api/reboot", payload={}, timeout=10)
            return {"status": "success", "transport": "http-agent", **response}
        except Exception:
            pass
    return _ssh_command(device, "sudo reboot", timeout=10)


def _execute_status(device: dict[str, Any]) -> dict[str, Any]:
    http_result = _status_via_http(device)
    if http_result.get("status") == "success":
        return http_result

    if device.get("telemetry"):
        record_device_telemetry(device["id"], deepcopy(device.get("telemetry") or {}), source="registry-status", metadata={"status": device.get("status")})

    return {
        "status": "queried",
        "transport": "registry",
        "device": device,
        "note": "Returned registry metadata because no live transport was available.",
    }


def _execute_telemetry(device: dict[str, Any], action_params: dict[str, Any]) -> dict[str, Any]:
    limit = int(action_params.get("limit") or 20)
    refresh = bool(action_params.get("refresh"))
    return query_device_telemetry(device["id"], limit=limit, refresh=refresh)


def _execute_provision(device: dict[str, Any], action_params: dict[str, Any]) -> dict[str, Any]:
    config = {**action_params}
    config.setdefault("command_center_url", DEFAULT_COMMAND_CENTER_URL)
    config.setdefault("shared_secret", AGENT_SHARED_SECRET)
    profile_id = config.get("profile_id")
    prepared = prepare_firmware_bundle(device_id=device["id"], profile_id=profile_id, config=config)
    if prepared.get("status") == "failed" or prepared.get("error"):
        return prepared

    install_result = None
    if config.get("install_after_prepare"):
        install_result = install_prepared_bundle(device["id"], prepared.get("bundle_id"))
    elif prepared.get("installable"):
        install_result = install_prepared_bundle(device["id"], prepared.get("bundle_id"))

    result = {"status": "success", "prepared_bundle": prepared}
    if install_result:
        result["install_result"] = install_result
        result["status"] = install_result.get("status", "success")
    return result


def _execute_firmware(device: dict[str, Any], action_params: dict[str, Any]) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    device_id = device["id"]
    firmware_path = action_params.get("firmware_path")
    family = str(device.get("family", "")).lower()
    chip = str(device.get("chip", "")).lower()
    is_esp_device = "esp" in family or "esp" in chip
    esp_write_requested = is_esp_device and bool(firmware_path or action_params.get("ota_url"))

    if esp_write_requested:
        if not device.get("port"):
            blocked = {"status": "failed", "error": "ESP32 firmware writes require a serial port for the mandatory 8 MB backup"}
            steps.append({"step": "backup", **blocked})
            return {"status": "failed", "steps": steps, "error": blocked["error"]}
        backup = esp_backup_firmware(device["port"], flash_size_mb=8, output_name=device_id)
        steps.append({"step": "backup", **backup})
        if backup.get("status") != "success" or backup.get("size_bytes") != 8 * 1024 * 1024:
            return {
                "status": "failed",
                "steps": steps,
                "error": backup.get("error", "Complete 8 MB ESP32 backup was not validated"),
            }
    elif action_params.get("backup_before_update"):
        steps.append({"step": "backup", "status": "skipped", "reason": "Backup not supported for this device"})

    flash_result: dict[str, Any]
    if action_params.get("bundle_id"):
        flash_result = install_prepared_bundle(device_id, action_params["bundle_id"])
        steps.append({"step": "install_bundle", **flash_result})
    elif firmware_path and device.get("port") and is_esp_device:
        flash_result = esp_flash_firmware(device["port"], firmware_path, flash_offset=str(action_params.get("flash_offset") or "0x0"))
        steps.append({"step": "flash", **flash_result})
    elif firmware_path and (device.get("drive") or action_params.get("drive")) and str(device.get("family", "")).startswith("rp"):
        flash_result = rp2040_flash_uf2(action_params.get("drive") or device.get("drive"), firmware_path)
        steps.append({"step": "flash", **flash_result})
    elif action_params.get("ota_url") and _resolve_agent_endpoint(device):
        endpoint = _resolve_agent_endpoint(device)
        try:
            flash_result = _http_request("POST", f"{endpoint}/api/update", payload={"url": action_params["ota_url"]}, timeout=20)
            flash_result["status"] = flash_result.get("status") or "success"
        except Exception as exc:
            flash_result = {"status": "failed", "error": str(exc)}
        steps.append({"step": "ota", **flash_result})
    else:
        flash_result = {"status": "failed", "error": "No compatible flash/install strategy resolved"}
        steps.append({"step": "flash", **flash_result})

    if flash_result.get("status") == "failed":
        return {"status": "failed", "steps": steps, "error": flash_result.get("error")}

    if action_params.get("verify_after_flash"):
        if device.get("port") and str(device.get("family", "")).startswith("esp"):
            verify = detect_chip_for_device(device_id)
        else:
            verify = _execute_status(get_device_from_registry(device_id) or device)
        steps.append({"step": "verify", **verify})
        if verify.get("status") in {"failed", "error"}:
            return {"status": "failed", "steps": steps, "error": verify.get("error", "Verification failed")}

    return {"status": "success", "steps": steps, "report": {"device_id": device_id, "completed_at": utcnow_iso()}}


def _execute_espnow(device: dict[str, Any], action_params: dict[str, Any]) -> dict[str, Any]:
    """Dispatch ESP-NOW firmware deployment — discover available examples, build if needed, flash."""
    device_id = device["id"]
    example = action_params.get("example", "get-started")
    target = action_params.get("target", "esp32")
    build_before = action_params.get("build_before_flash", True)

    from services.espnow_service import build_command, get_firmware_binaries

    # Check if binaries already exist
    binaries = get_firmware_binaries(example)
    if not binaries.get("built"):
        if not build_before:
            return {
                "status": "failed",
                "error": f"No pre-built binaries for '{example}' and build_before_flash is disabled. Run build first.",
            }
        build_info = build_command(example, target=target, port=device.get("port", ""))
        return {
            "status": "queued_for_build",
            "device_id": device_id,
            "example": example,
            "target": target,
            "build_commands": build_info.get("commands", {}),
            "note": f"Binaries not found. Run the build command from {build_info.get('directory')} then retry flash.",
        }

    # Binary exists — ready to flash via the existing firmware pipeline
    return {
        "status": "ready_for_flash",
        "device_id": device_id,
        "example": example,
        "binaries": binaries["binaries"],
        "count": binaries["count"],
        "next_action": "Use the firmware flash intent with the binary paths listed above.",
    }


def _execute_device_action(device_id: str, intent: str, action_params: dict[str, Any], parent_job: dict[str, Any], dry_run: bool = False) -> dict[str, Any]:
    if device_id == "_no_match":
        return {"status": "skipped", "reason": "No matching devices found"}

    device = get_device_from_registry(device_id)
    if not device:
        return {"status": "failed", "error": f"Device '{device_id}' not found"}

    if dry_run:
        return {"status": "dry_run", "intent": intent, "device": device_id, "action_params": action_params}

    if intent == "status":
        return _execute_status(device)
    if intent == "telemetry":
        return _execute_telemetry(device, action_params)
    if intent == "shell":
        return _execute_shell(device, action_params, parent_job)
    if intent == "reboot":
        return _execute_reboot(device, parent_job)
    if intent == "provision":
        return _execute_provision(device, action_params)
    if intent == "firmware":
        return _execute_firmware(device, action_params)
    if intent == "espnow":
        return _execute_espnow(device, action_params)

    return {"status": "skipped", "reason": f"Unsupported intent '{intent}'"}


def create_command_job(parsed_command: dict[str, Any], dry_run: bool = False) -> dict[str, Any]:
    job_id = f"cmd-{uuid.uuid4().hex[:12]}"
    job = {
        "job_id": job_id,
        "status": "queued",
        "command_text": parsed_command.get("command_text", ""),
        "intent": parsed_command.get("intent", "status"),
        "target_count": len(parsed_command.get("target_devices") or []),
        "results_by_device": {},
        "created_at": utcnow_iso(),
        "completed_at": None,
        "dry_run": dry_run,
        "reasoning_summary": parsed_command.get("reasoning_summary"),
        "template_id": parsed_command.get("template_id"),
        "tool_context": parsed_command.get("tool_context") or build_tool_context(include_jobs=False),
    }
    with _command_lock:
        _command_jobs[job_id] = job
        _command_history.append({
            "job_id": job_id,
            "command": job["command_text"],
            "timestamp": job["created_at"],
            "intent": job["intent"],
        })
    _save_command_state()
    return deepcopy(job)


def execute_command_job(job_id: str, parsed_command: dict[str, Any], dry_run: bool = False) -> None:
    with _command_lock:
        job = _command_jobs[job_id]
        job["status"] = "executing"
    _save_command_state()

    results: dict[str, Any] = {}
    try:
        for device_id in parsed_command.get("target_devices") or []:
            results[device_id] = _execute_device_action(device_id, parsed_command.get("intent", "status"), parsed_command.get("action_params") or {}, _command_jobs[job_id], dry_run=dry_run)
            with _command_lock:
                _command_jobs[job_id]["results_by_device"] = deepcopy(results)
                _refresh_job_status(_command_jobs[job_id])
            _save_command_state()

        with _command_lock:
            _command_jobs[job_id]["results_by_device"] = deepcopy(results)
            _refresh_job_status(_command_jobs[job_id])
            if _command_jobs[job_id]["status"] == "complete" and not _command_jobs[job_id].get("completed_at"):
                _command_jobs[job_id]["completed_at"] = utcnow_iso()
        _save_command_state()
    except Exception as exc:
        with _command_lock:
            _command_jobs[job_id]["status"] = "failed"
            _command_jobs[job_id]["completed_at"] = utcnow_iso()
            _command_jobs[job_id]["error"] = str(exc)
        _save_command_state()


def run_device_control_action(device_id: str, intent: str, action_params: Optional[dict[str, Any]] = None, *, dry_run: bool = False) -> dict[str, Any]:
    parsed = {
        "command_text": f"manual {intent} on {device_id}",
        "intent": intent,
        "target_devices": [device_id],
        "action_params": deepcopy(action_params or {}),
        "confidence": 1.0,
        "alternatives": [],
        "template_id": None,
        "reasoning_summary": "Manual device control action requested via API.",
        "tool_context": build_tool_context(include_jobs=False),
    }
    job = create_command_job(parsed, dry_run=dry_run)
    execute_command_job(job["job_id"], parsed, dry_run=dry_run)
    return get_command_job(job["job_id"]) or job


__all__ = [
    "AGENT_SHARED_SECRET",
    "DEFAULT_COMMAND_CENTER_URL",
    "build_tool_context",
    "claim_mobile_agent_job",
    "create_command_job",
    "execute_command_job",
    "get_command_history",
    "get_command_job",
    "get_command_template",
    "get_device_telemetry",
    "heartbeat_mobile_agent",
    "list_command_templates",
    "parse_command",
    "query_device_telemetry",
    "record_device_telemetry",
    "register_mobile_agent",
    "report_mobile_agent_job_result",
    "run_device_control_action",
]


_load_command_state()
