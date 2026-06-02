from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
HERMES_AGENT_DIR = REPO_ROOT / "hermes-agent"
HERMES_WEBUI_DIR = REPO_ROOT / "hermes-webui"
NIRVANA_DATA_DIR = REPO_ROOT / "backend" / "data" / "nirvana-runtime"
HERMES_HOME = NIRVANA_DATA_DIR / ".hermes"
WEBUI_STATE_DIR = NIRVANA_DATA_DIR / "webui"
CONFIG_PATH = HERMES_HOME / "config.yaml"
ENV_PATH = HERMES_HOME / ".env"
LOG_PATH = WEBUI_STATE_DIR / "nirvana-webui.log"
START_SCRIPT = HERMES_WEBUI_DIR / "start.ps1"
WEBUI_HOST = os.getenv("NIRVANA_WEBUI_HOST", os.getenv("HERMES_WEBUI_HOST", "127.0.0.1"))
WEBUI_PORT = int(os.getenv("NIRVANA_WEBUI_PORT", os.getenv("HERMES_WEBUI_PORT", "8789")))
WEBUI_URL = f"http://{WEBUI_HOST}:{WEBUI_PORT}"

_PROCESS_LOCK = threading.Lock()
_WEBUI_PROCESS: Optional[subprocess.Popen] = None
_WEBUI_LOG_HANDLE = None


class NirvanaServiceError(RuntimeError):
    """Raised when the upstream Nirvana bridge cannot complete an action."""



def _yaml_quote(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"



def _ensure_runtime_dirs() -> None:
    HERMES_HOME.mkdir(parents=True, exist_ok=True)
    WEBUI_STATE_DIR.mkdir(parents=True, exist_ok=True)



def _default_config_text() -> str:
    return "\n".join(
        [
            "# Isolated Nirvana runtime config for NPU-STACK",
            "# This keeps the embedded agent/web UI detached from any real user runtime home.",
            "model:",
            "  provider: auto",
            "terminal:",
            '  backend: "local"',
            f"  cwd: {_yaml_quote(str(REPO_ROOT))}",
            "  timeout: 180",
            "  lifetime_seconds: 300",
            "  docker_mount_cwd_to_workspace: false",
            "  container_cpu: 1",
            "  container_memory: 5120",
            "  container_disk: 51200",
            "  container_persistent: true",
            "browser:",
            "  inactivity_timeout: 120",
            "",
        ]
    )



def prepare_runtime() -> Dict[str, Any]:
    _ensure_runtime_dirs()
    created_config = False
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(_default_config_text(), encoding="utf-8")
        created_config = True

    return {
        "prepared": True,
        "created_config": created_config,
        "paths": _paths_payload(),
        "recommended_commands": recommended_commands(),
    }



def _paths_payload() -> Dict[str, str]:
    return {
        "repo_root": str(REPO_ROOT),
        "agent_dir": str(HERMES_AGENT_DIR),
        "webui_dir": str(HERMES_WEBUI_DIR),
        "hermes_home": str(HERMES_HOME),
        "webui_state_dir": str(WEBUI_STATE_DIR),
        "config_path": str(CONFIG_PATH),
        "env_path": str(ENV_PATH),
        "log_path": str(LOG_PATH),
        "start_script": str(START_SCRIPT),
    }



def recommended_commands() -> list[dict[str, str]]:
    return [
        {
            "id": "setup",
            "command": "hermes setup",
            "description": "Complete first-run CLI setup if you prefer terminal-first onboarding.",
        },
        {
            "id": "model",
            "command": "hermes model",
            "description": "Choose or change the active provider/model directly from the CLI.",
        },
        {
            "id": "tools",
            "command": "hermes tools",
            "description": "List the toolsets and integrations available to Nirvana.",
        },
        {
            "id": "doctor",
            "command": "hermes doctor",
            "description": "Run upstream diagnostics against the real agent install.",
        },
        {
            "id": "gateway",
            "command": "hermes gateway",
            "description": "Start the upstream gateway/server path when you want terminal parity outside the WebUI.",
        },
    ]



def _webui_env() -> Dict[str, str]:
    env = os.environ.copy()
    env["HERMES_WEBUI_AGENT_DIR"] = str(HERMES_AGENT_DIR)
    env["HERMES_HOME"] = str(HERMES_HOME)
    env["HERMES_WEBUI_STATE_DIR"] = str(WEBUI_STATE_DIR)
    env["HERMES_WEBUI_HOST"] = WEBUI_HOST
    env["HERMES_WEBUI_PORT"] = str(WEBUI_PORT)
    env["HERMES_WEBUI_DEFAULT_WORKSPACE"] = str(REPO_ROOT)
    return env



def _json_request(method: str, path: str, payload: Optional[Dict[str, Any]] = None, timeout: float = 10.0) -> Dict[str, Any]:
    url = f"{WEBUI_URL}{path}"
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8", errors="replace")
        if not raw.strip():
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"raw": raw}



def get_webui_health(timeout: float = 3.0) -> Dict[str, Any]:
    try:
        payload = _json_request("GET", "/health", timeout=timeout)
        return {
            "ok": True,
            "url": f"{WEBUI_URL}/health",
            "payload": payload,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "url": f"{WEBUI_URL}/health",
            "detail": str(exc),
        }



def get_onboarding_status(timeout: float = 4.0) -> Dict[str, Any]:
    try:
        payload = _json_request("GET", "/api/onboarding/status", timeout=timeout)
        return {
            "ok": True,
            "payload": payload,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "detail": str(exc),
        }



def tail_log(lines: int = 80) -> str:
    if not LOG_PATH.exists():
        return ""
    try:
        data = LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:  # noqa: BLE001
        return ""
    return "\n".join(data[-lines:])



def _tracked_process_info() -> Dict[str, Any]:
    with _PROCESS_LOCK:
        process = _WEBUI_PROCESS
        if not process:
            return {"tracked": False, "running": False, "pid": None, "exit_code": None}
        exit_code = process.poll()
        return {
            "tracked": True,
            "running": exit_code is None,
            "pid": process.pid,
            "exit_code": exit_code,
        }



def get_bridge_status() -> Dict[str, Any]:
    prepare_runtime()
    process = _tracked_process_info()
    health = get_webui_health()
    onboarding = get_onboarding_status() if health.get("ok") else {"ok": False, "detail": "WebUI not running"}
    onboarding_payload = onboarding.get("payload") or {}
    onboarding_system = onboarding_payload.get("system") or {}

    return {
        "agent_repo_present": HERMES_AGENT_DIR.exists(),
        "webui_repo_present": HERMES_WEBUI_DIR.exists(),
        "start_script_present": START_SCRIPT.exists(),
        "prepared": CONFIG_PATH.exists(),
        "webui_running": bool(health.get("ok")),
        "webui_url": WEBUI_URL,
        "paths": _paths_payload(),
        "process": process,
        "health": health,
        "onboarding": onboarding_payload if onboarding.get("ok") else None,
        "onboarding_error": None if onboarding.get("ok") else onboarding.get("detail"),
        "summary": {
            "completed": onboarding_payload.get("completed"),
            "hermes_found": onboarding_system.get("hermes_found"),
            "imports_ok": onboarding_system.get("imports_ok"),
            "provider_configured": onboarding_system.get("provider_configured"),
            "provider_ready": onboarding_system.get("provider_ready"),
            "chat_ready": onboarding_system.get("chat_ready"),
            "setup_state": onboarding_system.get("setup_state"),
            "current_provider": onboarding_system.get("current_provider"),
            "current_model": onboarding_system.get("current_model"),
            "current_base_url": onboarding_system.get("current_base_url"),
            "config_path": onboarding_system.get("config_path") or str(CONFIG_PATH),
            "env_path": onboarding_system.get("env_path") or str(ENV_PATH),
        },
        "recommended_commands": recommended_commands(),
        "log_excerpt": tail_log(),
    }



def _wait_for_webui(timeout_seconds: float = 35.0, interval_seconds: float = 1.0) -> Dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last_detail = "waiting for WebUI health"
    while time.time() < deadline:
        health = get_webui_health(timeout=2.0)
        if health.get("ok"):
            return {"ok": True, "health": health}
        last_detail = health.get("detail") or last_detail
        process = _tracked_process_info()
        if process.get("tracked") and not process.get("running"):
            break
        time.sleep(interval_seconds)
    return {"ok": False, "detail": last_detail, "log_excerpt": tail_log()}



def start_webui(timeout_seconds: float = 35.0) -> Dict[str, Any]:
    prepare_runtime()

    if get_webui_health().get("ok"):
        status = get_bridge_status()
        return {
            "success": True,
            "message": "Nirvana WebUI is already running.",
            **status,
        }

    if not START_SCRIPT.exists():
        raise NirvanaServiceError(f"Nirvana WebUI launcher not found at {START_SCRIPT}")
    if not HERMES_AGENT_DIR.exists():
        raise NirvanaServiceError(f"Nirvana agent source not found at {HERMES_AGENT_DIR}")

    launcher = shutil.which("powershell") or shutil.which("powershell.exe") or "powershell.exe"

    with _PROCESS_LOCK:
        global _WEBUI_PROCESS, _WEBUI_LOG_HANDLE
        if _WEBUI_PROCESS and _WEBUI_PROCESS.poll() is None:
            pass
        else:
            if _WEBUI_LOG_HANDLE:
                try:
                    _WEBUI_LOG_HANDLE.close()
                except Exception:  # noqa: BLE001
                    pass
            _WEBUI_LOG_HANDLE = open(LOG_PATH, "a", encoding="utf-8", buffering=1)
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            _WEBUI_PROCESS = subprocess.Popen(
                [
                    launcher,
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(START_SCRIPT),
                    "-Port",
                    str(WEBUI_PORT),
                    "-BindHost",
                    WEBUI_HOST,
                ],
                cwd=str(HERMES_WEBUI_DIR),
                env=_webui_env(),
                stdout=_WEBUI_LOG_HANDLE,
                stderr=subprocess.STDOUT,
                creationflags=creationflags,
            )

    waited = _wait_for_webui(timeout_seconds=timeout_seconds)
    status = get_bridge_status()
    if waited.get("ok"):
        return {
            "success": True,
            "message": "Nirvana WebUI started.",
            **status,
        }

    return {
        "success": False,
        "message": "Nirvana WebUI did not become healthy yet.",
        **status,
        "startup_error": waited.get("detail"),
        "log_excerpt": waited.get("log_excerpt") or status.get("log_excerpt", ""),
    }



def ensure_webui_running(timeout_seconds: float = 35.0) -> Dict[str, Any]:
    if get_webui_health().get("ok"):
        return get_bridge_status()
    started = start_webui(timeout_seconds=timeout_seconds)
    if not started.get("success"):
        raise NirvanaServiceError(started.get("startup_error") or started.get("message") or "Nirvana WebUI failed to start")
    return started



def create_webui_session(preferred_model: str = "") -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "workspace": str(REPO_ROOT),
        "profile": "npu-stack",
    }
    if preferred_model:
        payload["model"] = preferred_model

    response = _json_request("POST", "/api/session/new", payload=payload, timeout=30.0)
    session = response.get("session") or {}
    session_id = str(session.get("session_id") or "").strip()
    if not session_id:
        raise NirvanaServiceError("Nirvana WebUI returned no session_id when creating a session")
    return {
        "session_id": session_id,
        "session": session,
    }



def send_sync_chat(session_id: str, message: str, preferred_model: str = "") -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "session_id": session_id,
        "message": message,
        "workspace": str(REPO_ROOT),
    }
    if preferred_model:
        payload["model"] = preferred_model

    try:
        return _json_request("POST", "/api/chat", payload=payload, timeout=300.0)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise NirvanaServiceError(f"Nirvana chat HTTP {exc.code}: {detail}") from exc
    except Exception as exc:  # noqa: BLE001
        raise NirvanaServiceError(f"Nirvana sync chat failed: {exc}") from exc
