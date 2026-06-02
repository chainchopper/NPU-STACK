from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import yaml
except ImportError:  # pragma: no cover - fallback path below handles missing PyYAML
    yaml = None

REPO_ROOT = Path(__file__).resolve().parents[2]
HERMES_AGENT_DIR = REPO_ROOT / "hermes-agent"
HERMES_WEBUI_DIR = REPO_ROOT / "hermes-webui"
NIRVANA_DATA_DIR = REPO_ROOT / "backend" / "data" / "nirvana-runtime"
HERMES_HOME = NIRVANA_DATA_DIR / ".hermes"
WEBUI_STATE_DIR = NIRVANA_DATA_DIR / "webui"
RUNTIME_PYTHON_DIR = NIRVANA_DATA_DIR / "python"
CONFIG_PATH = HERMES_HOME / "config.yaml"
ENV_PATH = HERMES_HOME / ".env"
LOG_PATH = WEBUI_STATE_DIR / "nirvana-webui.log"
START_SCRIPT = HERMES_WEBUI_DIR / "start.ps1"
WEBUI_HOST = os.getenv("NIRVANA_WEBUI_HOST", os.getenv("HERMES_WEBUI_HOST", "127.0.0.1"))
WEBUI_PORT = int(os.getenv("NIRVANA_WEBUI_PORT", os.getenv("HERMES_WEBUI_PORT", "8789")))
WEBUI_URL = f"http://{WEBUI_HOST}:{WEBUI_PORT}"
NIRVANA_MODEL_BASE_URL = os.getenv("NIRVANA_MODEL_BASE_URL", "http://127.0.0.1:8010/v1")
NIRVANA_DEFAULT_MODEL = os.getenv("NIRVANA_DEFAULT_MODEL", "Phi-3-mini-4k-instruct-q4")

_PROCESS_LOCK = threading.Lock()
_RUNTIME_LOCK = threading.Lock()
_WEBUI_PROCESS: Optional[subprocess.Popen] = None
_WEBUI_LOG_HANDLE = None


class NirvanaServiceError(RuntimeError):
    """Raised when the upstream Nirvana bridge cannot complete an action."""



def _yaml_quote(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _preferred_model_config() -> Dict[str, str]:
    return {
        "default": NIRVANA_DEFAULT_MODEL,
        "provider": "custom",
        "base_url": NIRVANA_MODEL_BASE_URL,
    }



def _ensure_runtime_dirs() -> None:
    HERMES_HOME.mkdir(parents=True, exist_ok=True)
    WEBUI_STATE_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_PYTHON_DIR.mkdir(parents=True, exist_ok=True)


def _runtime_python_path() -> Path:
    if os.name == "nt":
        return RUNTIME_PYTHON_DIR / "Scripts" / "python.exe"
    return RUNTIME_PYTHON_DIR / "bin" / "python"


def _python_version(python_exe: Path | str) -> Optional[tuple[int, int]]:
    try:
        probe = subprocess.run(
            [str(python_exe), "-c", "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except Exception:
        return None
    if probe.returncode != 0:
        return None
    raw = (probe.stdout or "").strip()
    try:
        major, minor = raw.split(".", 1)
        return int(major), int(minor)
    except Exception:
        return None


def _py_launcher_path(version: str) -> Optional[str]:
    launcher = shutil.which("py") or shutil.which("py.exe")
    if not launcher:
        return None
    probe = subprocess.run(
        [launcher, f"-{version}", "-c", "import sys; print(sys.executable)"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if probe.returncode != 0:
        return None
    path = (probe.stdout or "").strip()
    return path or None


def _preferred_runtime_base_python() -> str:
    if os.name == "nt":
        for version in ("3.13", "3.12", "3.11"):
            candidate = _py_launcher_path(version)
            if candidate:
                return candidate
        current_version = _python_version(sys.executable)
        if current_version and current_version <= (3, 13):
            return sys.executable
        raise NirvanaServiceError(
            "Nirvana runtime requires Python 3.13, 3.12, or 3.11 on Windows because pywinpty does not currently build on Python 3.14"
        )
    return sys.executable


def _uv_executable() -> Optional[str]:
    return shutil.which("uv") or shutil.which("uv.exe")


def _runtime_probe_env() -> Dict[str, str]:
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        str(HERMES_AGENT_DIR)
        if not existing_pythonpath
        else f"{HERMES_AGENT_DIR}{os.pathsep}{existing_pythonpath}"
    )
    return env


def _python_runtime_ready(python_exe: Path) -> tuple[bool, str]:
    if not python_exe.exists():
        return False, f"python executable missing at {python_exe}"

    probe = subprocess.run(
        [
            str(python_exe),
            "-c",
            "import yaml, openai; from run_agent import AIAgent; print('ok')",
        ],
        cwd=str(HERMES_WEBUI_DIR),
        env=_runtime_probe_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if probe.returncode == 0:
        return True, "ok"
    detail = (probe.stderr or probe.stdout or "unknown import failure").strip()
    return False, detail


def _run_runtime_install(command: list[str], *, cwd: Path) -> None:
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "runtime install failed").strip()
        raise NirvanaServiceError(detail)


def ensure_runtime_python() -> Path:
    _ensure_runtime_dirs()
    python_path = _runtime_python_path()
    ready, _ = _python_runtime_ready(python_path)
    if ready:
        return python_path

    uv_exe = _uv_executable()
    if not uv_exe:
        raise NirvanaServiceError("uv is required to provision the isolated Nirvana runtime Python")

    with _RUNTIME_LOCK:
        ready, detail = _python_runtime_ready(python_path)
        if ready:
            return python_path

        runtime_version = _python_version(python_path) if python_path.exists() else None
        if runtime_version and runtime_version >= (3, 14):
            shutil.rmtree(RUNTIME_PYTHON_DIR, ignore_errors=True)
            _ensure_runtime_dirs()
            python_path = _runtime_python_path()

        if not python_path.exists():
            _run_runtime_install([uv_exe, "venv", str(RUNTIME_PYTHON_DIR), "--python", _preferred_runtime_base_python()], cwd=REPO_ROOT)

        _run_runtime_install(
            [uv_exe, "pip", "install", "--python", str(python_path), "-r", str(HERMES_WEBUI_DIR / "requirements.txt")],
            cwd=HERMES_WEBUI_DIR,
        )
        _run_runtime_install(
            [uv_exe, "pip", "install", "--python", str(python_path), "-e", str(HERMES_AGENT_DIR)],
            cwd=HERMES_AGENT_DIR,
        )

        ready, detail = _python_runtime_ready(python_path)
        if not ready:
            raise NirvanaServiceError(f"Nirvana runtime Python is still not ready: {detail}")

    return python_path



def _default_config_text() -> str:
    model_config = _preferred_model_config()
    return "\n".join(
        [
            "# Isolated Nirvana runtime config for NPU-STACK",
            "# This keeps the embedded agent/web UI detached from any real user runtime home.",
            "model:",
            f"  default: {_yaml_quote(model_config['default'])}",
            f"  provider: {model_config['provider']}",
            f"  base_url: {_yaml_quote(model_config['base_url'])}",
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


def _fallback_prewire_config_text(raw_text: str) -> tuple[str, bool]:
    model_block = "\n".join(
        [
            "model:",
            f"  default: {_yaml_quote(NIRVANA_DEFAULT_MODEL)}",
            "  provider: custom",
            f"  base_url: {_yaml_quote(NIRVANA_MODEL_BASE_URL)}",
        ]
    )
    if "model:\n  provider: auto" in raw_text:
        return raw_text.replace("model:\n  provider: auto", model_block, 1), True
    if raw_text.startswith("# Isolated Nirvana runtime config for NPU-STACK\nmodel:\n") and "base_url:" not in raw_text:
        parts = raw_text.split("terminal:\n", 1)
        if len(parts) == 2:
            return f"# Isolated Nirvana runtime config for NPU-STACK\n# This keeps the embedded agent/web UI detached from any real user runtime home.\n{model_block}\nterminal:\n{parts[1]}", True
    return raw_text, False


def _prewire_runtime_config() -> bool:
    if not CONFIG_PATH.exists():
        return False

    raw_text = CONFIG_PATH.read_text(encoding="utf-8", errors="replace")
    if yaml is None:
        updated_text, updated = _fallback_prewire_config_text(raw_text)
        if updated:
            CONFIG_PATH.write_text(updated_text, encoding="utf-8")
        return updated

    try:
        config = yaml.safe_load(raw_text) or {}
    except Exception:
        updated_text, updated = _fallback_prewire_config_text(raw_text)
        if updated:
            CONFIG_PATH.write_text(updated_text, encoding="utf-8")
        return updated

    if not isinstance(config, dict):
        config = {}

    model_config = config.get("model")
    if isinstance(model_config, str):
        model_config = {"default": model_config}
    elif not isinstance(model_config, dict):
        model_config = {}

    updated = False
    preferred = _preferred_model_config()

    current_default = str(model_config.get("default", "")).strip()
    if not current_default:
        model_config["default"] = preferred["default"]
        updated = True

    current_base_url = str(model_config.get("base_url", "")).strip()
    if not current_base_url:
        model_config["base_url"] = preferred["base_url"]
        updated = True

    current_provider = str(model_config.get("provider", "")).strip()
    if not current_provider or current_provider == "auto":
        model_config["provider"] = preferred["provider"]
        updated = True

    if not updated:
        return False

    config["model"] = model_config
    CONFIG_PATH.write_text(
        yaml.safe_dump(config, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return True



def prepare_runtime() -> Dict[str, Any]:
    _ensure_runtime_dirs()
    created_config = False
    updated_config = False
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(_default_config_text(), encoding="utf-8")
        created_config = True
    else:
        updated_config = _prewire_runtime_config()

    return {
        "prepared": True,
        "created_config": created_config,
        "updated_config": updated_config,
        "paths": _paths_payload(),
        "recommended_commands": recommended_commands(),
    }



def _paths_payload() -> Dict[str, str]:
    return {
        "repo_root": str(REPO_ROOT),
        "agent_dir": str(HERMES_AGENT_DIR),
        "webui_dir": str(HERMES_WEBUI_DIR),
        "runtime_python_dir": str(RUNTIME_PYTHON_DIR),
        "runtime_python": str(_runtime_python_path()),
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
    env["HERMES_WEBUI_PYTHON"] = str(ensure_runtime_python())
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
    ensure_runtime_python()

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
