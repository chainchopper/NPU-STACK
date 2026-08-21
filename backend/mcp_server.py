"""
NPU-STACK MCP Server (Model Context Protocol).
Exposes NPU-STACK functionalities to Nirvana via FastMCP stdio transport.

Discovered by Nirvana through config.yaml mcp_servers entry.
Tools: hardware detection, model registry, fleet ops, system health, training.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

from mcp.server.fastmcp import FastMCP

sys.path.insert(0, os.path.dirname(__file__))

from services.benchmark_service import get_system_info
from services.cross_converter import get_conversion_paths

NPU_API = os.getenv("NPU_STACK_API_BASE", "http://127.0.0.1:8010")

mcp = FastMCP("NPU-STACK MCP Server", json_response=True)


def _api(path: str) -> dict | list | str:
    """Call the NPU-STACK backend API and return parsed JSON."""
    url = f"{NPU_API}{path}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as exc:
        return {"error": str(exc)}


def _post(path: str, body: dict) -> dict:
    """POST JSON to the NPU-STACK backend API."""
    url = f"{NPU_API}{path}"
    try:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as exc:
        return {"error": str(exc)}


# ── Hardware & System ────────────────────────────────────────────────────

@mcp.tool()
def detect_hardware() -> dict:
    """Detect system hardware: CPU, GPU, NPU, RAM, disk. No API call needed."""
    return get_system_info()


@mcp.tool()
def system_health() -> dict:
    """Check NPU-STACK backend health and Nirvana bridge status."""
    return {
        "backend": _api("/api/health"),
        "nirvana": _api("/api/agent/runtime"),
    }


# ── Models ───────────────────────────────────────────────────────────────

@mcp.tool()
def list_models() -> dict:
    """List all models in the NPU-STACK registry (name, format, size, status)."""
    return _api("/api/models")


@mcp.tool()
def get_model_info(model_id: str) -> dict:
    """Get detailed info for a specific model by ID or name."""
    return _api(f"/api/models/{model_id}")


# ── Fleet ────────────────────────────────────────────────────────────────

@mcp.tool()
def list_devices(include_low_confidence: bool = True) -> dict:
    """List all discovered fleet devices (edge, USB, network)."""
    return _api(f"/api/devices?include_low_confidence={str(include_low_confidence).lower()}")


@mcp.tool()
def fleet_status() -> dict:
    """Get fleet overview: device count, online/offline, last seen."""
    return _api("/api/devices")


@mcp.tool()
def run_fleet_command(device_id: str, command: str) -> dict:
    """Dispatch a shell command to a fleet device via the fleet orchestrator."""
    import urllib.request as _req
    body = json.dumps({"device_ids": [device_id], "command": command}).encode("utf-8")
    req = _req.Request(
        f"{NPU_API}/api/fleet-command/dispatch",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with _req.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as exc:
        return {"error": str(exc)}


# ── Training & Jobs ──────────────────────────────────────────────────────

@mcp.tool()
def list_training_jobs() -> dict:
    """List all training jobs (status, model, progress)."""
    return _api("/api/training")


@mcp.tool()
def system_status() -> dict:
    """Get full system status: model count, job count, benchmarks."""
    return _api("/api/status")


# ── Conversion ───────────────────────────────────────────────────────────

@mcp.tool()
def list_conversion_paths() -> dict:
    """List all supported model conversion paths (source → target formats)."""
    return get_conversion_paths()


# ── Nirvana Self-Management ──────────────────────────────────────────────

@mcp.tool()
def nirvana_overview() -> dict:
    """Get the full Nirvana overview: agent config, sessions, skills."""
    return _api("/api/nirvana/overview")


@mcp.tool()
def nirvana_settings() -> dict:
    """Get all Nirvana settings (theme, provider, bot name, preferences)."""
    return _api("/api/nirvana/settings")


@mcp.tool()
def nirvana_sessions(limit: int = 10) -> dict:
    """List recent Nirvana sessions."""
    return _api(f"/api/nirvana/sessions?limit={limit}")


# ── ESP-NOW ──────────────────────────────────────────────────────────────

@mcp.tool()
def espnow_status() -> dict:
    """Check ESP-NOW library availability and toolchain. Baked at libraries/esp-now-lib/."""
    return _api("/api/espnow/status")


@mcp.tool()
def espnow_modules() -> dict:
    """List ESP-NOW source modules: control, OTA, security, provisioning, debug."""
    return _api("/api/espnow/modules")


@mcp.tool()
def espnow_examples() -> dict:
    """List ESP-NOW example projects: get-started, coin_cell_demo, OTA, security, etc."""
    return _api("/api/espnow/examples")


@mcp.tool()
def espnow_build_info(example: str, target: str = "esp32") -> dict:
    """Get build commands for an ESP-NOW example (set-target, build, flash, monitor)."""
    return _api(f"/api/espnow/examples/{example}/build?target={target}")


@mcp.tool()
def espnow_binaries(example: str) -> dict:
    """List built firmware binaries for an ESP-NOW example."""
    return _api(f"/api/espnow/examples/{example}/binaries")


@mcp.tool()
def espnow_deploy(example: str, device_id: str = "", target: str = "esp32") -> dict:
    """Queue ESP-NOW firmware deployment to fleet devices via the fleet command system.
    
    Parses a natural-language fleet command and dispatches it to the target device.
    Use device_id="all" to target all ESP32 devices in the fleet registry.
    """
    # Build the natural language command
    target_desc = f"device {device_id}" if device_id and device_id != "all" else "all esp32 devices"
    nl_command = f"deploy {example} espnow firmware to {target_desc} using target {target}"

    # Step 1: Parse the command
    parse_result = _post("/api/fleet/command/parse", {"command": nl_command, "use_agent": False})
    if "error" in parse_result:
        return {"status": "parse_failed", "error": parse_result["error"], "command": nl_command}

    # Step 2: Queue execution
    exec_result = _post("/api/fleet/command/execute", {"parsed_command": parse_result, "dry_run": False})
    if "error" in exec_result:
        return {"status": "exec_failed", "error": exec_result["error"], "job_id": exec_result.get("job_id", "unknown")}

    return {
        "status": "queued",
        "job_id": exec_result.get("job_id"),
        "command": nl_command,
        "intent": exec_result.get("intent", "espnow"),
        "target_count": exec_result.get("target_count", 0),
        "poll_job": f"/api/fleet/command/jobs/{exec_result.get('job_id')}",
        "hint": "Use fleet_command_job_status to poll this job.",
    }


@mcp.tool()
def fleet_flash(example: str, device_ids: list[str] | None = None, target: str = "esp32") -> dict:
    """Flash ESP-NOW firmware binaries to fleet devices. Requires pre-built binaries.
    
    First check espnow_binaries to confirm binaries exist, then call this tool.
    device_ids: list of device IDs from the registry, or None for all ESP32 devices.
    """
    # Check binaries exist first
    binaries_info = _api(f"/api/espnow/examples/{example}/binaries")
    if not isinstance(binaries_info, dict) or not binaries_info.get("built"):
        return {
            "status": "no_binaries",
            "error": f"No pre-built binaries found for '{example}'. Run espnow_build_info first.",
            "available_binaries": binaries_info,
        }

    targets = device_ids or ["all"]
    target_list = ", ".join(targets)
    nl_command = f"flash {example} firmware to devices {target_list} using target {target}"

    parse_result = _post("/api/fleet/command/parse", {"command": nl_command, "use_agent": False})
    if "error" in parse_result:
        return {"status": "parse_failed", "error": parse_result["error"]}

    exec_result = _post("/api/fleet/command/execute", {"parsed_command": parse_result, "dry_run": False})
    return {
        "status": "queued",
        "job_id": exec_result.get("job_id"),
        "intent": exec_result.get("intent"),
        "target_count": exec_result.get("target_count", 0),
        "binaries": binaries_info.get("binaries", []),
        "poll_job": f"/api/fleet/command/jobs/{exec_result.get('job_id')}",
    }


@mcp.tool()
def fleet_command_job_status(job_id: str) -> dict:
    """Poll the status of a fleet command job (deployment, flash, provision, etc.)."""
    return _api(f"/api/fleet/command/jobs/{job_id}")


@mcp.tool()
def fleet_command_history(limit: int = 20) -> dict:
    """List recent fleet command execution history."""
    return _api(f"/api/fleet/command/history?limit={limit}")


# ── MicroPython emulator ────────────────────────────────────────────────

@mcp.tool()
def emulator_examples() -> dict:
    """List Nirvana OS device apps available to preview in the MicroPython emulator."""
    return _api("/api/emulator/examples")


@mcp.tool()
def emulator_run_app(app_id: str) -> dict:
    """Run a Nirvana OS app through the host MicroPython emulator (virtual
    round display) and report what rendered: non-black pixel count + app logs.
    Lets Nirvana verify device UI code before flashing any board."""
    import base64
    import subprocess
    import tempfile

    examples = _api("/api/emulator/examples")
    apps = examples.get("apps", []) if isinstance(examples, dict) else []
    app = next((a for a in apps if a.get("id") == app_id), None)
    if not app or not app.get("code"):
        return {"error": f"app '{app_id}' not found", "available": [a["id"] for a in apps]}

    fd, tmp = tempfile.mkstemp(suffix=".py", prefix="nirvana_app_")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(app["code"])

    py = sys.executable
    try:
        proc = subprocess.run(
            [py, "-m", "backend.emulator.runner", tmp],
            capture_output=True, timeout=30,
        )
    except subprocess.TimeoutExpired:
        return {"app_id": app_id, "error": "app timed out"}
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass

    logs = []
    frame_bytes = None
    out = proc.stdout
    pos = 0
    while pos < len(out):
        nl = out.find(b"\n", pos)
        if nl < 0:
            break
        line = out[pos:nl]
        pos = nl + 1
        if line.startswith(b"LOG:"):
            logs.append(line[4:].decode("utf-8", "replace"))
        elif line.startswith(b"FRAME:"):
            try:
                length = int(line[6:])
            except Exception:
                continue
            frame_bytes = out[pos:pos + length]
            pos += length

    rendered = None
    if frame_bytes:
        nonzero = sum(1 for b in frame_bytes if b != 0)
        rendered = {"size": len(frame_bytes), "nonzero_pixels_bytes": nonzero}

    return {
        "app_id": app_id,
        "name": app.get("name"),
        "returncode": proc.returncode,
        "rendered": rendered,
        "logs": logs[-20:],
        "ok": proc.returncode == 0,
    }


# ── Resources ────────────────────────────────────────────────────────────

@mcp.resource("info://welcome")
def get_welcome_info() -> str:
    return (
        "Welcome to NPU-STACK MCP Server! "
        "Nirvana can use these tools to manage models, fleet devices, "
        "training jobs, conversion pipelines, and system health."
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
