"""Orchestration router — Nirvana runtime settings and AutoResearch run/profile state."""

from __future__ import annotations

import json
import os
import shutil
import uuid
from datetime import datetime, timezone
import time
from threading import Lock, Thread
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/orchestration", tags=["orchestration"])

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)
STATE_FILE = os.path.join(DATA_DIR, "orchestration_state.json")
_STATE_LOCK = Lock()
_WARMUP_LOCK = Lock()
_WARMUP_THREAD: Optional[Thread] = None
_WARMUP_STATUS: Dict[str, Any] = {
    "active": False,
    "started_at": None,
    "finished_at": None,
    "attempts": 0,
    "max_attempts": 0,
    "interval_seconds": 0,
    "ready": False,
    "detail": "not started",
}


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.dirname(__file__)))


def _read_json_file(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        return None
    return None


def _discover_mcp_servers(configured: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Discover MCP server candidates from workspace and common user config paths."""
    project_root = _project_root()
    home_dir = os.path.expanduser("~")
    configured_set = set(configured or [])
    discovered: Dict[str, Dict[str, Any]] = {}

    def _add(server_id: str, label: str, source: str, path: Optional[str], auto_add: bool) -> None:
        if not server_id:
            return
        key = server_id.strip()
        if not key:
            return
        if key in discovered:
            existing = discovered[key]
            # Prefer auto-add=true and preserve first valid path if already set.
            existing["auto_add"] = bool(existing.get("auto_add") or auto_add)
            if (not existing.get("path")) and path:
                existing["path"] = path
            return
        discovered[key] = {
            "id": key,
            "label": label or key,
            "source": source,
            "path": path,
            "auto_add": bool(auto_add),
            "already_configured": key in configured_set,
        }

    # 1) Workspace packaged MCP server bundles
    servers_src = os.path.join(project_root, "mcp_temp_assets", "servers", "src")
    if os.path.isdir(servers_src):
        for name in sorted(os.listdir(servers_src)):
            full = os.path.join(servers_src, name)
            if os.path.isdir(full):
                _add(name, name.replace("-", " ").title(), "workspace-bundle", full, auto_add=True)

    # 2) Local backend MCP server implementation
    backend_mcp = os.path.join(project_root, "backend", "mcp_server.py")
    if os.path.exists(backend_mcp):
        _add("npu-stack-local", "NPU-STACK Local MCP", "workspace-local", backend_mcp, auto_add=True)

    # 3) Read mcp server IDs from known config files
    candidate_config_files = [
        os.path.join(project_root, ".mcp.json"),
        os.path.join(project_root, "mcp.json"),
        os.path.join(project_root, "mcp_temp_assets", "servers", ".mcp.json"),
        os.path.join(project_root, ".vscode", "mcp.json"),
        os.path.join(home_dir, ".mcp.json"),
    ]
    for cfg_path in candidate_config_files:
        cfg_data = _read_json_file(cfg_path)
        if not cfg_data:
            continue
        servers = cfg_data.get("mcpServers")
        if isinstance(servers, dict):
            for server_name in servers.keys():
                _add(server_name, server_name, "config-file", cfg_path, auto_add=True)

    return sorted(discovered.values(), key=lambda item: item["id"].lower())


def _discover_skills() -> List[Dict[str, Any]]:
    """Discover skills from common workspace/user skill directories."""
    project_root = _project_root()
    home_dir = os.path.expanduser("~")
    bases = [
        os.path.join(project_root, ".agents", "skills"),
        os.path.join(project_root, ".copilot", "skills"),
        os.path.join(home_dir, ".agents", "skills"),
        os.path.join(home_dir, ".copilot", "skills"),
    ]

    found: Dict[str, Dict[str, Any]] = {}
    for base in bases:
        if not os.path.isdir(base):
            continue
        for root, dirs, files in os.walk(base):
            if "SKILL.md" not in files:
                continue
            skill_name = os.path.basename(root)
            rel = os.path.relpath(root, base)
            key = f"{base}:{rel}".lower()
            found[key] = {
                "id": skill_name,
                "path": root,
                "source": "workspace" if base.startswith(project_root) else "user-home",
            }
            if len(found) >= 200:
                return sorted(found.values(), key=lambda item: item["id"].lower())
    return sorted(found.values(), key=lambda item: item["id"].lower())


def _discover_mcp_tools() -> List[Dict[str, Any]]:
    """Discover local MCP tool names from backend MCP implementation."""
    project_root = _project_root()
    backend_mcp = os.path.join(project_root, "backend", "mcp_server.py")
    if not os.path.exists(backend_mcp):
        return []

    tool_entries: List[Dict[str, Any]] = []
    try:
        with open(backend_mcp, "r", encoding="utf-8") as f:
            lines = f.readlines()
        for idx, line in enumerate(lines):
            if "@mcp.tool" in line:
                # Find the next function definition.
                for look_ahead in range(idx + 1, min(idx + 8, len(lines))):
                    maybe_def = lines[look_ahead].strip()
                    if maybe_def.startswith("def ") and "(" in maybe_def:
                        name = maybe_def.split("def ", 1)[1].split("(", 1)[0].strip()
                        if name:
                            tool_entries.append(
                                {
                                    "id": name,
                                    "source": "backend-mcp",
                                    "path": backend_mcp,
                                }
                            )
                        break
    except Exception:
        return []
    return tool_entries


def _ensure_default_mcp_servers(state: Dict[str, Any]) -> bool:
    """Auto-add discovered baseline MCP servers so they are ready out-of-the-box."""
    hermes_cfg = state.get("hermes", {})
    configured = set(hermes_cfg.get("mcp_servers") or [])
    discovered = _discover_mcp_servers(list(configured))
    changed = False
    for item in discovered:
        if item.get("auto_add") and item["id"] not in configured:
            configured.add(item["id"])
            changed = True
    if changed:
        hermes_cfg["mcp_servers"] = sorted(configured)
        hermes_cfg["updated_at"] = _utc_iso()
        state["hermes"] = hermes_cfg
    return changed


def _existing_path(path: str) -> Optional[str]:
    if path and os.path.exists(path):
        return path
    return None


def _resolve_env_alias(nirvana_key: str, hermes_key: str) -> Dict[str, Optional[str]]:
    """Resolve branding aliases while preserving Hermes backward compatibility.

    Resolution order:
      1) NIRVANA_* (preferred branding)
      2) HERMES_*  (legacy compatibility)
    """
    nirvana_value = os.getenv(nirvana_key)
    hermes_value = os.getenv(hermes_key)

    if nirvana_value not in (None, ""):
        return {


            "value": nirvana_value,
            "source": nirvana_key,
            "nirvana": nirvana_value,
            "hermes": hermes_value,
        }

    if hermes_value not in (None, ""):
        return {
            "value": hermes_value,
            "source": hermes_key,
            "nirvana": nirvana_value,
            "hermes": hermes_value,
        }

    return {
        "value": None,
        "source": None,
        "nirvana": nirvana_value,
        "hermes": hermes_value,
    }


def _discover_hermes_config_sources(config: Dict[str, Any]) -> Dict[str, Any]:
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    home_dir = os.path.expanduser("~")
    venv_dir = os.path.join(project_root, ".venv")

    checked_paths = [
        os.path.join(project_root, ".env"),
        os.path.join(project_root, ".hermes"),
        os.path.join(project_root, ".hermes", "config.yaml"),
        os.path.join(project_root, ".hermes", "config.yml"),
        os.path.join(venv_dir, ".hermes"),
        os.path.join(venv_dir, ".hermes", "config.yaml"),
        os.path.join(venv_dir, ".hermes", "config.yml"),
        os.path.join(home_dir, ".hermes"),
        os.path.join(home_dir, ".hermes", "config.yaml"),
        os.path.join(home_dir, ".hermes", "config.yml"),
        os.path.join(home_dir, ".config", "hermes", "config.yaml"),
        os.path.join(home_dir, ".config", "hermes", "config.yml"),
    ]

    existing = [p for p in checked_paths if os.path.exists(p)]

    api_base = _resolve_env_alias("NIRVANA_API_BASE", "HERMES_API_BASE")
    default_model = _resolve_env_alias("NIRVANA_DEFAULT_MODEL", "HERMES_DEFAULT_MODEL")
    default_provider = _resolve_env_alias("NIRVANA_DEFAULT_PROVIDER", "HERMES_DEFAULT_PROVIDER")
    tool_policy = _resolve_env_alias("NIRVANA_TOOL_POLICY", "HERMES_TOOL_POLICY")

    env_config = {
        # Preferred branding
        "NIRVANA_API_BASE": api_base["nirvana"],
        "NIRVANA_DEFAULT_MODEL": default_model["nirvana"],
        "NIRVANA_DEFAULT_PROVIDER": default_provider["nirvana"],
        "NIRVANA_TOOL_POLICY": tool_policy["nirvana"],
        # Backward-compatible legacy keys
        "HERMES_API_BASE": api_base["hermes"],
        "HERMES_DEFAULT_MODEL": default_model["hermes"],
        "HERMES_DEFAULT_PROVIDER": default_provider["hermes"],
        "HERMES_TOOL_POLICY": tool_policy["hermes"],
    }

    return {
        "checked_paths": checked_paths,
        "existing_paths": existing,
        "project_env_file": _existing_path(os.path.join(project_root, ".env")),
        "env_variables": env_config,
        "resolved_env": {
            "api_base": api_base,
            "default_model": default_model,
            "default_provider": default_provider,
            "tool_policy": tool_policy,
        },
        "effective": {
            "api_base": config.get("api_base") or api_base["value"],
            "default_model": config.get("default_model") or default_model["value"],
            "default_provider": config.get("default_provider") or default_provider["value"],
            "tool_policy": config.get("tool_policy") or tool_policy["value"] or "approval-required",
        },
    }


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_state() -> Dict[str, Any]:
    return {
        "nirvana": {
            "agent_name": "Nirvana",
            "agent_brand": "NPU-STACK",
            "identity_statement": (


                "You are Nirvana, the built-in system orchestration assistant for NPU-STACK. "
                "You can help across model lifecycle tasks, local inference, fine-tuning, fleet operations, "
                "conversion, benchmarking, and tooling orchestration."
            ),
            "mission": "Universal stack assistant with unified runtime orchestration context.",
            "updated_at": _utc_iso(),
        },
        "hermes": {
            "enabled": False,
            "api_base": "http://localhost:11437/v1",
            "default_provider": "openai-compatible",
            "default_model": "",
            "tool_policy": "approval-required",
            "mcp_servers": [],
            "updated_at": _utc_iso(),
        },
        "autoresearch": {
            "profiles": [
                {
                    "id": "baseline-quick-loop",
                    "name": "Baseline Quick Loop",
                    "objective": "Small constrained experiment cycle with low risk.",
                    "max_iterations": 3,
                    "time_budget_minutes": 25,
                    "safety_mode": "strict",
                    "updated_at": _utc_iso(),
                }
            ],
            "runs": [],
        },
    }


def _load_state() -> Dict[str, Any]:
    if not os.path.exists(STATE_FILE):
        state = _default_state()
        _save_state(state)
        return state

    with open(STATE_FILE, "r", encoding="utf-8") as f:
        state = json.load(f)

    # Backfill schema fields for forward compatibility
    if "hermes" not in state:
        state["hermes"] = _default_state()["hermes"]
    if "nirvana" not in state:
        state["nirvana"] = _default_state()["nirvana"]
    # Enforce branding protocol in perpetuity
    state["nirvana"]["agent_name"] = "Nirvana"
    # Migrate any legacy mission wording away from Hermes branding.
    mission = state["nirvana"].get("mission", "")
    if isinstance(mission, str) and "Hermes-compatible" in mission:
        state["nirvana"]["mission"] = mission.replace(
            "Hermes-compatible orchestration context",
            "unified runtime orchestration context",
        )
    if "autoresearch" not in state:
        state["autoresearch"] = _default_state()["autoresearch"]
    if "profiles" not in state["autoresearch"]:
        state["autoresearch"]["profiles"] = _default_state()["autoresearch"]["profiles"]
    if "runs" not in state["autoresearch"]:
        state["autoresearch"]["runs"] = []

    # Auto-register discovered baseline MCP servers if missing.
    if _ensure_default_mcp_servers(state):
        _save_state(state)

    return state


def _save_state(state: Dict[str, Any]) -> None:
    temp_path = f"{STATE_FILE}.tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    os.replace(temp_path, STATE_FILE)


def _hermes_runtime_status(config: Dict[str, Any]) -> Dict[str, Any]:
    cli_path = shutil.which("hermes-agent") or shutil.which("hermes")
    api_base_env = _resolve_env_alias("NIRVANA_API_BASE", "HERMES_API_BASE")["value"]
    api_base = config.get("api_base") or api_base_env
    return {
        "cli_installed": bool(cli_path),
        "cli_path": cli_path,
        "api_base": api_base,
        "api_configured": bool(api_base),
        "config_sources": _discover_hermes_config_sources(config),
        "startup_warmup": _get_warmup_status(),
    }


def _truthy_env(name: str) -> bool:
    value = os.getenv(name)
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _env_int_alias(nirvana_key: str, hermes_key: str, default: int, minimum: int = 0) -> int:
    value = _resolve_env_alias(nirvana_key, hermes_key).get("value")
    if value in (None, ""):
        return default
    try:
        return max(minimum, int(str(value).strip()))
    except Exception:
        return default


def _set_warmup_status(**kwargs) -> None:
    with _WARMUP_LOCK:
        _WARMUP_STATUS.update(kwargs)


def _get_warmup_status() -> Dict[str, Any]:
    with _WARMUP_LOCK:
        return dict(_WARMUP_STATUS)


def _probe_runtime_api(api_base: str) -> Dict[str, Any]:
    """Best-effort readiness probe for OpenAI-compatible runtime endpoints."""
    try:
        import requests
    except Exception as exc:
        return {"ready": False, "detail": f"probe dependency unavailable: {exc}"}

    normalized = (api_base or "").rstrip("/")
    if not normalized:
        return {"ready": False, "detail": "api_base not configured"}

    candidates = [
        f"{normalized}/models",
        f"{normalized}/health",
    ]

    errors: List[str] = []
    for url in candidates:
        try:
            response = requests.get(url, timeout=4)
            if 200 <= response.status_code < 500:
                # 2xx = healthy, 4xx still proves runtime is reachable
                return {
                    "ready": True,
                    "url": url,
                    "status_code": response.status_code,
                }
            errors.append(f"{url} -> HTTP {response.status_code}")
        except Exception as exc:
            errors.append(f"{url} -> {exc}")

    return {
        "ready": False,
        "detail": "; ".join(errors) if errors else "runtime not reachable",
    }


def initialize_nirvana_runtime_on_startup() -> Dict[str, Any]:
    """Apply env aliases and warm up runtime at backend startup.

    This is intentionally non-fatal: startup should continue even if the external
    runtime is unavailable.
    """
    with _STATE_LOCK:
        state = _load_state()
        cfg = state.get("hermes", {})

        sources = _discover_hermes_config_sources(cfg)
        effective = sources.get("effective", {})

        changed = False

        # Hydrate missing config values from env aliases (NIRVANA_* preferred,
        # HERMES_* fallback) without clobbering explicit saved values.
        for key in ("api_base", "default_model", "default_provider", "tool_policy"):
            if (not cfg.get(key)) and effective.get(key):
                cfg[key] = effective[key]
                changed = True

        auto_enable = (
            _truthy_env("NIRVANA_AUTO_ENABLE")
            or _truthy_env("HERMES_AUTO_ENABLE")
        )
        if auto_enable and cfg.get("api_base") and not cfg.get("enabled"):
            cfg["enabled"] = True
            changed = True

        if changed:
            cfg["updated_at"] = _utc_iso()
            state["hermes"] = cfg
            _save_state(state)

    runtime_status = _hermes_runtime_status(cfg)
    probe = (
        _probe_runtime_api(runtime_status.get("api_base"))
        if cfg.get("enabled") and runtime_status.get("api_base")
        else {"ready": False, "detail": "runtime disabled or api_base missing"}
    )

    return {
        "enabled": bool(cfg.get("enabled")),
        "api_base": runtime_status.get("api_base"),
        "probe": probe,
        "config_changed": changed,
    }


def start_nirvana_runtime_warmup_retry(startup_state: Dict[str, Any]) -> Dict[str, Any]:
    """Start a non-blocking retry loop that probes runtime readiness after boot.

    This never raises and never blocks process startup.
    """
    global _WARMUP_THREAD

    enabled = bool(startup_state.get("enabled"))
    probe = startup_state.get("probe") or {}
    api_base = startup_state.get("api_base")

    retry_window_seconds = _env_int_alias(
        "NIRVANA_STARTUP_RETRY_SECONDS",
        "HERMES_STARTUP_RETRY_SECONDS",
        default=30,
        minimum=0,
    )
    retry_interval_seconds = _env_int_alias(
        "NIRVANA_STARTUP_RETRY_INTERVAL_SECONDS",
        "HERMES_STARTUP_RETRY_INTERVAL_SECONDS",
        default=3,
        minimum=1,
    )

    if not enabled:
        _set_warmup_status(
            active=False,
            ready=False,
            detail="runtime disabled",
            finished_at=_utc_iso(),
        )
        return _get_warmup_status()

    if probe.get("ready"):
        _set_warmup_status(
            active=False,
            ready=True,
            detail="runtime already ready",
            finished_at=_utc_iso(),
        )
        return _get_warmup_status()

    if retry_window_seconds <= 0:
        _set_warmup_status(
            active=False,
            ready=False,
            detail="warmup retries disabled",
            finished_at=_utc_iso(),
        )
        return _get_warmup_status()

    max_attempts = max(1, retry_window_seconds // retry_interval_seconds)

    with _WARMUP_LOCK:
        if _WARMUP_THREAD and _WARMUP_THREAD.is_alive():
            return dict(_WARMUP_STATUS)

        _WARMUP_STATUS.update(
            {
                "active": True,
                "started_at": _utc_iso(),
                "finished_at": None,
                "attempts": 0,
                "max_attempts": max_attempts,
                "interval_seconds": retry_interval_seconds,
                "ready": False,
                "detail": "probing runtime readiness",
            }
        )

    def _runner() -> None:
        latest_detail = "runtime unreachable"
        for attempt in range(1, max_attempts + 1):
            probe_result = _probe_runtime_api(api_base)
            _set_warmup_status(attempts=attempt, detail=probe_result.get("detail", "checking"))
            if probe_result.get("ready"):
                _set_warmup_status(
                    active=False,
                    ready=True,
                    detail="runtime became ready",
                    finished_at=_utc_iso(),
                )
                return
            latest_detail = probe_result.get("detail") or latest_detail
            if attempt < max_attempts:
                time.sleep(retry_interval_seconds)

        _set_warmup_status(
            active=False,
            ready=False,
            detail=f"runtime not ready after retries: {latest_detail}",
            finished_at=_utc_iso(),
        )

    thread = Thread(target=_runner, name="nirvana-runtime-warmup", daemon=True)
    _WARMUP_THREAD = thread
    thread.start()
    return _get_warmup_status()


class HermesConfigPayload(BaseModel):
    enabled: bool = False
    api_base: str = "http://localhost:11437/v1"
    default_provider: str = "openai-compatible"
    default_model: str = ""
    tool_policy: Literal["approval-required", "allowlisted-only", "open"] = "approval-required"
    mcp_servers: List[str] = Field(default_factory=list)


class NirvanaIdentityPayload(BaseModel):
    identity_statement: str
    mission: str


class MCPAutoAddPayload(BaseModel):
    server_ids: List[str] = Field(default_factory=list)


def _capabilities_catalog(state: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "agent": state.get("nirvana", {}),
        "tools": [
            {"id": "models", "label": "Model Registry", "scope": "upload/list/delete/chat"},
            {"id": "training", "label": "Training", "scope": "jobs/start/stop/monitor"},
            {"id": "inference", "label": "Inference", "scope": "text/image/audio/video"},
            {"id": "conversion", "label": "Conversion", "scope": "quantize/validate/format convert"},
            {"id": "benchmark", "label": "Benchmark", "scope": "runtime performance + compare"},
            {"id": "datasets", "label": "Datasets", "scope": "upload/scan/delete"},
            {"id": "fleet", "label": "Fleet Ops", "scope": "discover/pair/prepare/install"},
            {"id": "orchestration", "label": "Orchestration", "scope": "runtime + autoresearch controls"},
        ],
        "skills": [
            {
                "id": "nirvana-core",
                "label": "Nirvana Core",
                "description": "Identity + mission + stack-aware orchestration behavior",
            },
            {
                "id": "fleet-orchestrator",
                "label": "Fleet Orchestrator",
                "description": "Device operations context for fleet-aware assistance",
            },
            {
                "id": "autoresearch-loop",
                "label": "AutoResearch Loop",
                "description": "Profile/run lifecycle planning and tracking",
            },
        ],
        "mcp": {
            "enabled": bool(state.get("hermes", {}).get("enabled")),
            "servers": state.get("hermes", {}).get("mcp_servers", []),
            "policy": state.get("hermes", {}).get("tool_policy", "approval-required"),
        },
    }


class AutoResearchProfilePayload(BaseModel):
    name: str
    objective: str
    max_iterations: int = Field(default=3, ge=1, le=200)
    time_budget_minutes: int = Field(default=30, ge=1, le=24 * 60)
    safety_mode: Literal["strict", "balanced", "experimental"] = "strict"


class AutoResearchRunPayload(BaseModel):
    profile_id: str
    notes: str = ""


class AutoResearchRunStatusPayload(BaseModel):
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    result_summary: Optional[str] = None


@router.get("/state")
def get_orchestration_state():
    with _STATE_LOCK:
        state = _load_state()
    return {
        **state,
        "capabilities": _capabilities_catalog(state),
        "hermes_runtime": _hermes_runtime_status(state["hermes"]),
    }


@router.get("/nirvana")
def get_nirvana_identity():
    with _STATE_LOCK:
        state = _load_state()
        nirvana = state["nirvana"]
    return {
        "identity": nirvana,
    }


@router.put("/nirvana")
def update_nirvana_identity(payload: NirvanaIdentityPayload):
    with _STATE_LOCK:
        state = _load_state()
        # Branding protocol: agent name is immutable
        state["nirvana"] = {
            "agent_name": "Nirvana",
            "agent_brand": "NPU-STACK",
            "identity_statement": payload.identity_statement,
            "mission": payload.mission,
            "updated_at": _utc_iso(),
        }
        _save_state(state)
    return {
        "message": "Nirvana identity updated.",
        "identity": state["nirvana"],
    }


@router.get("/capabilities")
def get_orchestration_capabilities():
    with _STATE_LOCK:
        state = _load_state()
    return _capabilities_catalog(state)


@router.get("/hermes")
def get_hermes_config():
    with _STATE_LOCK:
        state = _load_state()
        config = state["hermes"]
    return {
        "config": config,
        "runtime": _hermes_runtime_status(config),
    }


@router.get("/nirvana-config")
def get_nirvana_runtime_config():
    """Nirvana-branded alias of /hermes for UI-facing usage."""
    with _STATE_LOCK:
        state = _load_state()
        config = state["hermes"]
    return {
        "config": config,
        "runtime": _hermes_runtime_status(config),
    }


@router.put("/hermes")
def update_hermes_config(payload: HermesConfigPayload):
    with _STATE_LOCK:
        state = _load_state()
        state["hermes"] = {
            **payload.model_dump(),
            "updated_at": _utc_iso(),
        }
        _save_state(state)
        config = state["hermes"]
    return {
        "message": "Nirvana runtime configuration saved.",
        "config": config,
        "runtime": _hermes_runtime_status(config),
    }


@router.put("/nirvana-config")
def update_nirvana_runtime_config(payload: HermesConfigPayload):
    """Nirvana-branded alias of /hermes for UI-facing usage."""
    with _STATE_LOCK:
        state = _load_state()
        state["hermes"] = {
            **payload.model_dump(),
            "updated_at": _utc_iso(),
        }
        _save_state(state)
        config = state["hermes"]
    return {
        "message": "Nirvana runtime configuration saved.",
        "config": config,
        "runtime": _hermes_runtime_status(config),
    }


@router.get("/mcp/discover")
def discover_mcp_assets():
    """Discover MCP servers/tools/skills from common workspace and user locations."""
    with _STATE_LOCK:
        state = _load_state()
        configured = state.get("hermes", {}).get("mcp_servers", [])

    return {
        "configured_servers": configured,
        "servers": _discover_mcp_servers(configured),
        "tools": _discover_mcp_tools(),
        "skills": _discover_skills(),
    }


@router.post("/mcp/auto-add")
def auto_add_discovered_mcp_servers(payload: MCPAutoAddPayload):
    """One-click add discovered MCP servers into active runtime config."""
    with _STATE_LOCK:
        state = _load_state()
        cfg = state.get("hermes", {})
        existing = set(cfg.get("mcp_servers") or [])
        discovered = _discover_mcp_servers(list(existing))

        if payload.server_ids:
            selected = {s.strip() for s in payload.server_ids if s.strip()}
            to_add = [item["id"] for item in discovered if item["id"] in selected]
        else:
            to_add = [item["id"] for item in discovered if item.get("auto_add")]

        added = []
        for server_id in to_add:
            if server_id not in existing:
                existing.add(server_id)
                added.append(server_id)

        cfg["mcp_servers"] = sorted(existing)
        if added:
            cfg["updated_at"] = _utc_iso()
            state["hermes"] = cfg
            _save_state(state)

    return {
        "message": "MCP servers updated.",
        "added": added,
        "count_added": len(added),
        "mcp_servers": cfg.get("mcp_servers", []),
    }


@router.get("/autoresearch/profiles")
def list_autoresearch_profiles():
    with _STATE_LOCK:
        state = _load_state()
        profiles = state["autoresearch"].get("profiles", [])
    return {
        "count": len(profiles),
        "profiles": profiles,
    }


@router.post("/autoresearch/profiles")
def create_autoresearch_profile(payload: AutoResearchProfilePayload):
    with _STATE_LOCK:
        state = _load_state()
        profile = {
            "id": f"profile-{uuid.uuid4().hex[:10]}",
            **payload.model_dump(),
            "updated_at": _utc_iso(),
        }
        state["autoresearch"]["profiles"].insert(0, profile)
        _save_state(state)

    return {
        "message": "AutoResearch profile created.",
        "profile": profile,
    }


@router.delete("/autoresearch/profiles/{profile_id}")
def delete_autoresearch_profile(profile_id: str):
    with _STATE_LOCK:
        state = _load_state()
        profiles = state["autoresearch"].get("profiles", [])
        before = len(profiles)
        profiles = [p for p in profiles if p.get("id") != profile_id]
        if len(profiles) == before:
            raise HTTPException(status_code=404, detail="Profile not found")
        state["autoresearch"]["profiles"] = profiles
        _save_state(state)

    return {"message": "AutoResearch profile removed."}


@router.get("/autoresearch/runs")
def list_autoresearch_runs(limit: int = 25):
    limit = max(1, min(limit, 200))
    with _STATE_LOCK:
        state = _load_state()
        runs = state["autoresearch"].get("runs", [])[:limit]
    return {
        "count": len(runs),
        "runs": runs,
    }


@router.post("/autoresearch/runs")
def create_autoresearch_run(payload: AutoResearchRunPayload):
    with _STATE_LOCK:
        state = _load_state()
        profiles = state["autoresearch"].get("profiles", [])
        profile = next((p for p in profiles if p.get("id") == payload.profile_id), None)
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")

        run = {
            "id": f"run-{uuid.uuid4().hex[:10]}",
            "profile_id": profile["id"],
            "profile_name": profile["name"],
            "notes": payload.notes,
            "status": "queued",
            "created_at": _utc_iso(),
            "updated_at": _utc_iso(),
            "result_summary": None,
        }

        state["autoresearch"]["runs"].insert(0, run)
        _save_state(state)

    return {
        "message": "AutoResearch run queued.",
        "run": run,
    }


@router.patch("/autoresearch/runs/{run_id}")
def update_autoresearch_run(run_id: str, payload: AutoResearchRunStatusPayload):
    with _STATE_LOCK:
        state = _load_state()
        runs = state["autoresearch"].get("runs", [])
        run = next((r for r in runs if r.get("id") == run_id), None)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")

        run["status"] = payload.status
        run["result_summary"] = payload.result_summary
        run["updated_at"] = _utc_iso()
        _save_state(state)

    return {
        "message": "AutoResearch run updated.",
        "run": run,
    }
