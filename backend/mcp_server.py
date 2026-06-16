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
def espnow_deploy(example: str, device_id: str = "") -> dict:
    """Queue an ESP-NOW firmware deployment to a fleet device. Returns build/flash status."""
    return _api(f"/api/espnow/examples/{example}/build?target=esp32")


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
