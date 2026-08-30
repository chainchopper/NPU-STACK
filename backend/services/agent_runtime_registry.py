"""Normalized agent runtime registry and bounded discovery.

This module deliberately owns runtime identity, not model/provider configuration.
It keeps Nirvana available as the built-in default while allowing users to select
supported runtimes they already own. Discovery is read-only and never launches a
process or persists credentials.
"""
from __future__ import annotations

import copy
import ipaddress
import json
import os
import re
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

SCHEMA_VERSION = 1
REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "backend" / "data"
DATA_FILE = DATA_DIR / "agent_runtimes.json"
DEFAULT_NPU_STACK_BASE_URL = os.getenv("NPU_STACK_RUNTIME_BASE_URL", "http://127.0.0.1:8010/v1")
DEFAULT_FASTFLOWLM_BASE_URL = os.getenv("FASTFLOWLM_BASE_URL", "http://127.0.0.1:52625/v1")
DEFAULT_OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")

_RUNTIME_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,119}$")
_ENV_VAR_RE = re.compile(r"^[A-Z_][A-Z0-9_]{0,127}$")
_SAFE_ID_RE = re.compile(r"[^a-z0-9]+")

CAPABILITY_NAMES = (
    "chat",
    "stream",
    "models",
    "settings",
    "sessions",
    "skills",
    "tools",
    "approvals",
    "clarifications",
    "lifecycle",
    "sandbox",
)

_LOCK = threading.RLock()
_HEALTH_CACHE: Dict[str, Dict[str, Any]] = {}
_TEST_DATA_FILE: Optional[Path] = None


class RuntimeRegistryError(ValueError):
    """Raised when a runtime registration or selection is unsafe or invalid."""


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_detail_code(exc: BaseException) -> str:
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return "timeout"
    if isinstance(exc, urllib.error.HTTPError):
        return f"http_{exc.code}"
    if isinstance(exc, urllib.error.URLError):
        reason = str(exc.reason).lower()
        if "timed out" in reason or "timeout" in reason:
            return "timeout"
        if "refused" in reason or "unreachable" in reason:
            return "connection_refused"
        return "connection_error"
    if isinstance(exc, ValueError):
        return "invalid_response"
    return "probe_error"


def _detail_for_code(code: str) -> str:
    return {
        "ok": "Runtime responded successfully.",
        "timeout": "Runtime probe timed out.",
        "connection_refused": "Runtime is not reachable.",
        "connection_error": "Runtime connection failed.",
        "invalid_response": "Runtime returned an unsupported response.",
        "probe_error": "Runtime probe failed.",
    }.get(code, "Runtime probe did not complete.")


def _capabilities(**enabled: bool) -> Dict[str, bool]:
    result = {name: False for name in CAPABILITY_NAMES}
    result.update({key: bool(value) for key, value in enabled.items() if key in result})
    return result


def _endpoint_parts(url: str, *, allow_insecure_http: bool = False) -> Dict[str, Any]:
    """Validate an endpoint and return credential-free endpoint metadata."""
    raw = str(url or "").strip()
    if not raw or len(raw) > 2048:
        raise RuntimeRegistryError("Endpoint URL is required and must be short enough to validate")
    parsed = urllib.parse.urlsplit(raw)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise RuntimeRegistryError("Endpoint must use http or https")
    if parsed.username or parsed.password:
        raise RuntimeRegistryError("Credentials in endpoint URLs are not supported")
    if parsed.query or parsed.fragment:
        raise RuntimeRegistryError("Endpoint query strings and fragments are not supported")
    host = parsed.hostname
    if not host:
        raise RuntimeRegistryError("Endpoint hostname is required")
    try:
        port = parsed.port
    except ValueError as exc:
        raise RuntimeRegistryError("Endpoint port is invalid") from exc
    if port is not None and not 1 <= port <= 65535:
        raise RuntimeRegistryError("Endpoint port is invalid")

    scheme = parsed.scheme.lower()
    host_lower = host.lower().rstrip(".")
    local_hosts = {"localhost", "127.0.0.1", "::1"}
    is_local = host_lower in local_hosts
    try:
        is_private = ipaddress.ip_address(host_lower).is_private
    except ValueError:
        is_private = False
    if scheme == "http" and not (is_local or is_private or allow_insecure_http):
        raise RuntimeRegistryError("Remote runtime endpoints must use HTTPS")

    path = parsed.path or "/"
    if ".." in Path(path).parts:
        raise RuntimeRegistryError("Endpoint path cannot contain parent traversal")
    display_host = f"[{host_lower}]" if ":" in host_lower and not host_lower.startswith("[") else host_lower
    return {
        "scheme": scheme,
        "host": display_host,
        "port": port,
        "path": path,
        "is_local": is_local,
        "is_private": is_private,
    }


def _endpoint_url(endpoint: Dict[str, Any]) -> str:
    host = str(endpoint.get("host") or "")
    if host.startswith("["):
        host_for_url = host
    elif ":" in host:
        host_for_url = f"[{host}]"
    else:
        host_for_url = host
    port = endpoint.get("port")
    authority = f"{host_for_url}:{port}" if port else host_for_url
    path = str(endpoint.get("path") or "/")
    return f"{endpoint.get('scheme', 'http')}://{authority}{path}"


def _normalize_endpoint_url(endpoint: Dict[str, Any]) -> str:
    return _endpoint_url(endpoint).rstrip("/")


def _join_endpoint_path(base_url: str, path: str) -> str:
    """Append a request path without duplicating a configured base path."""
    base = str(base_url or "").rstrip("/")
    requested = str(path or "/")
    if not requested.startswith("/"):
        requested = f"/{requested}"
    parsed = urllib.parse.urlsplit(base)
    base_path = (parsed.path or "/").rstrip("/")
    if base_path and base_path != "/" and (requested == base_path or requested.startswith(f"{base_path}/")):
        origin = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
        return f"{origin}{requested}"
    return f"{base}{requested}"


def _credential_source(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    raw = str(value).strip()
    if raw.startswith("env:"):
        raw = raw[4:]
    if not _ENV_VAR_RE.fullmatch(raw):
        raise RuntimeRegistryError("Credentials must reference an environment variable")
    return f"env:{raw}"


def _slug(value: str) -> str:
    cleaned = _SAFE_ID_RE.sub("-", str(value or "").strip().lower()).strip("-")
    return cleaned[:70] or uuid.uuid4().hex[:10]


def _valid_runtime_id(runtime_id: str) -> str:
    value = str(runtime_id or "").strip().lower()
    if not _RUNTIME_ID_RE.fullmatch(value):
        raise RuntimeRegistryError("Runtime id contains unsupported characters")
    return value


def _health(status: str = "unconfigured", *, code: str = "", latency_ms: Optional[int] = None) -> Dict[str, Any]:
    return {
        "checked_at": _utc_iso() if code else None,
        "latency_ms": latency_ms,
        "detail_code": code or None,
        "detail": _detail_for_code(code) if code else None,
    }


def _base_descriptor(
    *,
    runtime_id: str,
    display_name: str,
    description: str,
    adapter: str,
    source: str,
    status: str,
    endpoint: Optional[Dict[str, Any]],
    capabilities: Dict[str, bool],
    configuration: Optional[Dict[str, Any]] = None,
    provenance: Optional[Dict[str, Any]] = None,
    models: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "runtime_id": runtime_id,
        "display_name": display_name,
        "description": description,
        "adapter": adapter,
        "source": source,
        "status": status,
        "selected": False,
        "profile_bindable": True,
        "endpoint": copy.deepcopy(endpoint),
        "capabilities": {name: bool(capabilities.get(name)) for name in CAPABILITY_NAMES},
        "models": copy.deepcopy(models or []),
        "health": _health(),
        "configuration": {
            "configured": False,
            "credential_source": None,
            "needs_user_action": False,
            **(configuration or {}),
        },
        "provenance": {
            "detectors": [],
            "confidence": "known",
            **(provenance or {}),
        },
    }


def nirvana_descriptor() -> Dict[str, Any]:
    return _base_descriptor(
        runtime_id="nirvana-default",
        display_name="Nirvana (Default)",
        description="Built-in NPU-STACK orchestration runtime with recovery support.",
        adapter="nirvana",
        source="builtin",
        status="ready",
        endpoint=None,
        capabilities=_capabilities(
            chat=True,
            stream=True,
            models=True,
            settings=True,
            sessions=True,
            skills=True,
            tools=True,
            approvals=True,
            clarifications=True,
            lifecycle=True,
        ),
        configuration={"configured": True, "needs_user_action": False},
        provenance={"detectors": ["builtin"]},
    )


def _default_local_descriptors() -> List[Dict[str, Any]]:
    return [
        _base_descriptor(
            runtime_id="npu-stack-local",
            display_name="NPU-STACK Local API",
            description="The local NPU-STACK OpenAI-compatible serving endpoint.",
            adapter="openai-compatible",
            source="discovered",
            status="offline",
            endpoint=_endpoint_parts(DEFAULT_NPU_STACK_BASE_URL),
            capabilities=_capabilities(chat=True, stream=True, models=True),
            configuration={"configured": True, "needs_user_action": False},
            provenance={"detectors": ["npu-stack-config"]},
        ),
        _base_descriptor(
            runtime_id="ollama-local",
            display_name="Ollama (Local)",
            description="Local Ollama HTTP runtime; discovery never starts Ollama.",
            adapter="ollama",
            source="discovered",
            status="unconfigured",
            endpoint=_endpoint_parts(DEFAULT_OLLAMA_BASE_URL),
            capabilities=_capabilities(chat=True, stream=True, models=True),
            configuration={"configured": bool(os.getenv("OLLAMA_BASE_URL")), "needs_user_action": True},
            provenance={"detectors": ["ollama-config"]},
        ),
        _base_descriptor(
            runtime_id="fastflowlm-local",
            display_name="FastFlowLM (Local)",
            description="Known FastFlowLM local API; direct inference remains separate from agent selection.",
            adapter="fastflowlm",
            source="discovered",
            status="unconfigured",
            endpoint=_endpoint_parts(DEFAULT_FASTFLOWLM_BASE_URL),
            capabilities=_capabilities(chat=True, stream=True, models=True),
            configuration={"configured": bool(os.getenv("FASTFLOWLM_BASE_URL")), "needs_user_action": True},
            provenance={"detectors": ["fastflowlm-config"]},
        ),
    ]


def _read_state(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError):
        return {"schema_version": SCHEMA_VERSION, "selected_runtime_id": "nirvana-default", "registrations": []}
    if not isinstance(data, dict):
        return {"schema_version": SCHEMA_VERSION, "selected_runtime_id": "nirvana-default", "registrations": []}
    registrations = data.get("registrations")
    if not isinstance(registrations, list):
        registrations = []
    return {
        "schema_version": SCHEMA_VERSION,
        "selected_runtime_id": str(data.get("selected_runtime_id") or "nirvana-default"),
        "registrations": [item for item in registrations if isinstance(item, dict)],
    }


def _state_path() -> Path:
    return _TEST_DATA_FILE or DATA_FILE


def _write_state(state: Dict[str, Any]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(temp_path, path)


def _stored_registrations() -> List[Dict[str, Any]]:
    state = _read_state(_state_path())
    return state["registrations"]


def _stored_to_descriptor(item: Dict[str, Any]) -> Dict[str, Any]:
    endpoint = item.get("endpoint") if isinstance(item.get("endpoint"), dict) else None
    descriptor = _base_descriptor(
        runtime_id=str(item.get("runtime_id") or ""),
        display_name=str(item.get("display_name") or item.get("runtime_id") or "Registered Runtime"),
        description=str(item.get("description") or "User-registered agent runtime."),
        adapter=str(item.get("adapter") or "openai-compatible"),
        source="registered",
        status="offline",
        endpoint=endpoint,
        capabilities=item.get("capabilities") if isinstance(item.get("capabilities"), dict) else _capabilities(chat=True, models=True),
        configuration=item.get("configuration") if isinstance(item.get("configuration"), dict) else {"configured": True},
        provenance=item.get("provenance") if isinstance(item.get("provenance"), dict) else {"detectors": ["explicit-registration"], "confidence": "explicit"},
        models=item.get("models") if isinstance(item.get("models"), list) else [],
    )
    descriptor["registered_at"] = item.get("registered_at")
    return descriptor


def _lmstudio_descriptors() -> List[Dict[str, Any]]:
    try:
        from routers.lmstudio import _instances

        instances = _instances()
    except Exception:
        instances = []
    output: List[Dict[str, Any]] = []
    for instance in instances:
        if not isinstance(instance, dict) or not instance.get("base_url"):
            continue
        instance_id = _slug(str(instance.get("id") or "local"))
        runtime_id = f"lmstudio:{instance_id}"
        try:
            endpoint = _endpoint_parts(str(instance["base_url"]))
        except RuntimeRegistryError:
            continue
        credential = "env:LMSTUDIO_API_KEY" if instance_id == "local" and os.getenv("LMSTUDIO_API_KEY") else None
        if instance_id != "local" and instance.get("api_key"):
            credential = "legacy-configured"
        output.append(
            _base_descriptor(
                runtime_id=runtime_id,
                display_name=str(instance.get("name") or f"LM Studio ({instance_id})"),
                description="Linked LM Studio OpenAI-compatible instance.",
                adapter="lmstudio",
                source="discovered",
                status="offline",
                endpoint=endpoint,
                capabilities=_capabilities(chat=True, stream=True, models=True),
                configuration={
                    "configured": True,
                    "credential_source": credential,
                    "needs_user_action": False,
                },
                provenance={"detectors": ["lmstudio-instance-registry"], "confidence": "configured"},
            )
        )
    return output


def runtime_credential(runtime_id: str) -> Optional[str]:
    """Resolve adapter credentials internally without exposing them in descriptors."""
    runtime_key = str(runtime_id or "").strip().lower()
    if not runtime_key.startswith("lmstudio:"):
        return None
    try:
        from routers.lmstudio import _instances

        instance_key = runtime_key.split(":", 1)[1]
        for instance in _instances():
            if _slug(str(instance.get("id") or "local")) == instance_key:
                return str(instance.get("api_key") or "") or None
    except Exception:
        return None
    return None


def _legacy_external_descriptor() -> Optional[Dict[str, Any]]:
    """Expose the pre-registry Hermes/Nirvana API setting as a runtime."""
    try:
        from routers.orchestration import _load_state

        config = _load_state().get("hermes") or {}
    except Exception:
        return None
    if not config.get("enabled") or not config.get("api_base"):
        return None
    try:
        endpoint = _endpoint_parts(str(config["api_base"]))
    except RuntimeRegistryError:
        return None
    return _base_descriptor(
        runtime_id="openai-compatible:legacy-external",
        display_name="Configured External Runtime",
        description="Legacy NPU-STACK external runtime configuration.",
        adapter="openai-compatible",
        source="legacy-configured",
        status="offline",
        endpoint=endpoint,
        capabilities=_capabilities(chat=True, stream=True, models=True),
        configuration={
            "configured": True,
            "credential_source": None,
            "needs_user_action": False,
        },
        provenance={"detectors": ["legacy-hermes-config"], "confidence": "configured"},
        models=([{"id": str(config["default_model"])}] if config.get("default_model") else []),
    )


def _catalog_without_probe() -> List[Dict[str, Any]]:
    descriptors = [nirvana_descriptor(), *_default_local_descriptors(), *_lmstudio_descriptors()]
    legacy_external = _legacy_external_descriptor()
    if legacy_external:
        descriptors.append(legacy_external)
    descriptors.extend(_stored_to_descriptor(item) for item in _stored_registrations())
    unique: Dict[str, Dict[str, Any]] = {}
    for descriptor in descriptors:
        runtime_id = descriptor.get("runtime_id")
        if runtime_id and runtime_id not in unique:
            unique[runtime_id] = descriptor
    state = _read_state(_state_path())
    selected_id = state.get("selected_runtime_id") or "nirvana-default"
    if selected_id not in unique:
        selected_id = "nirvana-default"
        if state.get("selected_runtime_id") != selected_id:
            state["selected_runtime_id"] = selected_id
            _write_state(state)
    for descriptor in unique.values():
        descriptor["selected"] = descriptor["runtime_id"] == selected_id
        cached = _HEALTH_CACHE.get(str(descriptor["runtime_id"]))
        if cached:
            descriptor.update({key: copy.deepcopy(value) for key, value in cached.get("descriptor", {}).items() if key in {"status", "health", "models"}})
    return sorted(unique.values(), key=lambda item: (not item["selected"], item["source"], item["display_name"].lower()))


def _no_redirect_opener() -> urllib.request.OpenerDirector:
    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
            return None

    return urllib.request.build_opener(_NoRedirect)


def _probe_http(endpoint: Dict[str, Any], paths: Iterable[str], *, timeout: float = 1.5) -> Dict[str, Any]:
    base = _normalize_endpoint_url(endpoint)
    opener = _no_redirect_opener()
    started = time.perf_counter()
    last_code = "connection_error"
    attempted_urls = set()
    for path in paths:
        path_value = str(path or "/")
        if not path_value.startswith("/"):
            path_value = f"/{path_value}"
        url = _join_endpoint_path(base, path_value)
        if url in attempted_urls:
            continue
        attempted_urls.add(url)
        request = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
        try:
            with opener.open(request, timeout=timeout) as response:
                status = int(getattr(response, "status", 200))
                raw = response.read(1024 * 1024).decode("utf-8", errors="replace")
                if status < 200 or status >= 300:
                    last_code = f"http_{status}"
                    continue
                try:
                    payload = json.loads(raw) if raw.strip() else {}
                except ValueError as exc:
                    raise ValueError("non-json response") from exc
                elapsed = max(0, int((time.perf_counter() - started) * 1000))
                models = _extract_models(payload)
                return {"ok": True, "code": "ok", "latency_ms": elapsed, "payload": payload, "models": models}
        except urllib.error.HTTPError as exc:
            last_code = _safe_detail_code(exc)
        except Exception as exc:  # noqa: BLE001
            last_code = _safe_detail_code(exc)
    return {
        "ok": False,
        "code": last_code,
        "latency_ms": max(0, int((time.perf_counter() - started) * 1000)),
        "payload": {},
        "models": [],
    }


def _extract_models(payload: Any) -> List[Dict[str, Any]]:
    raw_models = payload.get("data") if isinstance(payload, dict) else None
    if raw_models is None and isinstance(payload, dict):
        raw_models = payload.get("models")
    if not isinstance(raw_models, list):
        return []
    models: List[Dict[str, Any]] = []
    for item in raw_models[:100]:
        if isinstance(item, str):
            models.append({"id": item})
        elif isinstance(item, dict):
            model_id = item.get("id") or item.get("name") or item.get("model")
            if model_id:
                models.append({"id": str(model_id), "name": str(item.get("name") or model_id)})
    return models


def _nirvana_probe() -> Dict[str, Any]:
    try:
        from services.nirvana_service import get_bridge_status

        status = get_bridge_status()
        summary = status.get("summary") or {}
        ready = bool(summary.get("chat_ready") or status.get("webui_running"))
        return {
            "ok": ready,
            "code": "ok" if ready else "connection_error",
            "latency_ms": 0,
            "models": ([{"id": str(summary["current_model"]), "name": str(summary["current_model"])}] if summary.get("current_model") else []),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "code": _safe_detail_code(exc), "latency_ms": 0, "models": []}


def _probe_descriptor(descriptor: Dict[str, Any]) -> Dict[str, Any]:
    adapter = descriptor.get("adapter")
    if adapter == "nirvana":
        result = _nirvana_probe()
    else:
        endpoint = descriptor.get("endpoint")
        if not isinstance(endpoint, dict):
            result = {"ok": False, "code": "connection_error", "latency_ms": 0, "models": []}
        elif adapter == "ollama":
            result = _probe_http(endpoint, ("/api/tags", "/v1/models"))
        elif adapter == "fastflowlm":
            result = _probe_http(endpoint, ("/models", "/v1/models"))
        else:
            result = _probe_http(endpoint, ("/models", "/v1/models"))

    if result.get("ok"):
        descriptor["status"] = "ready"
    elif descriptor.get("configuration", {}).get("configured"):
        descriptor["status"] = "offline"
    else:
        descriptor["status"] = "unconfigured"
    descriptor["models"] = result.get("models") or descriptor.get("models") or []
    descriptor["health"] = _health(
        descriptor["status"],
        code=str(result.get("code") or "probe_error"),
        latency_ms=result.get("latency_ms"),
    )
    return descriptor


def list_runtimes(*, probe: bool = False) -> List[Dict[str, Any]]:
    with _LOCK:
        descriptors = _catalog_without_probe()
        if probe:
            descriptors = [_probe_and_cache(item) for item in descriptors]
        return copy.deepcopy(descriptors)


def _probe_and_cache(descriptor: Dict[str, Any]) -> Dict[str, Any]:
    result = _probe_descriptor(descriptor)
    _HEALTH_CACHE[str(descriptor["runtime_id"])] = {"descriptor": copy.deepcopy(result), "stored_at": _utc_iso()}
    return result


def get_runtime(runtime_id: str, *, probe: bool = False) -> Optional[Dict[str, Any]]:
    runtime_key = str(runtime_id or "").strip().lower()
    with _LOCK:
        descriptor = next((item for item in _catalog_without_probe() if item["runtime_id"] == runtime_key), None)
        if descriptor is None:
            return None
        if probe:
            descriptor = _probe_and_cache(descriptor)
        return copy.deepcopy(descriptor)


def discover(*, probe: bool = True) -> List[Dict[str, Any]]:
    """Refresh bounded discovery; this never launches or mutates runtimes."""
    return list_runtimes(probe=probe)


def probe_runtime(runtime_id: str) -> Dict[str, Any]:
    runtime = get_runtime(runtime_id, probe=True)
    if runtime is None:
        raise RuntimeRegistryError("Runtime not found")
    return runtime


def _registration_record(payload: Dict[str, Any], *, existing_id: Optional[str] = None) -> Dict[str, Any]:
    adapter = str(payload.get("adapter") or "openai-compatible").strip().lower()
    if adapter not in {"openai-compatible", "ollama", "lmstudio", "hermes"}:
        raise RuntimeRegistryError("Unsupported registration adapter")
    requested_id = str(payload.get("runtime_id") or existing_id or "").strip().lower()
    if requested_id:
        runtime_id = _valid_runtime_id(requested_id)
    else:
        runtime_id = f"openai-compatible:{_slug(str(payload.get('display_name') or payload.get('name') or 'runtime'))}"
    if runtime_id in {"nirvana-default", "npu-stack-local", "ollama-local", "fastflowlm-local"} or runtime_id.startswith("lmstudio:"):
        raise RuntimeRegistryError("That runtime id is reserved for a built-in or discovered runtime")

    endpoint_value = payload.get("endpoint") or payload.get("base_url") or payload.get("api_base")
    endpoint = _endpoint_parts(str(endpoint_value), allow_insecure_http=bool(payload.get("allow_insecure_http")))
    credential = _credential_source(payload.get("credential_env_var") or payload.get("credential_source"))
    capabilities = payload.get("capabilities") if isinstance(payload.get("capabilities"), dict) else _capabilities(chat=True, models=True)
    return {
        "runtime_id": runtime_id,
        "display_name": str(payload.get("display_name") or payload.get("name") or runtime_id),
        "description": str(payload.get("description") or "User-registered agent runtime."),
        "adapter": adapter,
        "endpoint": endpoint,
        "capabilities": {name: bool(capabilities.get(name)) for name in CAPABILITY_NAMES},
        "configuration": {
            "configured": True,
            "credential_source": credential,
            "needs_user_action": False,
        },
        "provenance": {"detectors": ["explicit-registration"], "confidence": "explicit"},
        "registered_at": _utc_iso(),
    }


def register_runtime(payload: Dict[str, Any]) -> Dict[str, Any]:
    with _LOCK:
        record = _registration_record(payload)
        state = _read_state(_state_path())
        state["registrations"] = [item for item in state["registrations"] if item.get("runtime_id") != record["runtime_id"]]
        state["registrations"].append(record)
        _write_state(state)
        _HEALTH_CACHE.pop(record["runtime_id"], None)
    return get_runtime(record["runtime_id"]) or _stored_to_descriptor(record)


def update_runtime(runtime_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    with _LOCK:
        existing = next((item for item in _stored_registrations() if item.get("runtime_id") == runtime_id), None)
        if existing is None:
            raise RuntimeRegistryError("Only explicitly registered runtimes can be updated")
        merged = {**existing, **payload, "runtime_id": runtime_id}
        record = _registration_record(merged, existing_id=runtime_id)
        state = _read_state(_state_path())
        state["registrations"] = [record if item.get("runtime_id") == runtime_id else item for item in state["registrations"]]
        _write_state(state)
        _HEALTH_CACHE.pop(runtime_id, None)
    return get_runtime(runtime_id) or _stored_to_descriptor(record)


def unregister_runtime(runtime_id: str) -> None:
    runtime_key = str(runtime_id or "").strip().lower()
    if runtime_key == "nirvana-default":
        raise RuntimeRegistryError("Nirvana (Default) cannot be removed")
    with _LOCK:
        state = _read_state(_state_path())
        before = len(state["registrations"])
        state["registrations"] = [item for item in state["registrations"] if item.get("runtime_id") != runtime_key]
        if len(state["registrations"]) == before:
            raise RuntimeRegistryError("Only explicitly registered runtimes can be removed")
        if state.get("selected_runtime_id") == runtime_key:
            state["selected_runtime_id"] = "nirvana-default"
        _write_state(state)
        _HEALTH_CACHE.pop(runtime_key, None)


def selected_runtime_id() -> str:
    with _LOCK:
        state = _read_state(_state_path())
        selected = str(state.get("selected_runtime_id") or "nirvana-default")
        if get_runtime(selected) is None:
            selected = "nirvana-default"
            state["selected_runtime_id"] = selected
            _write_state(state)
        return selected


def select_runtime(runtime_id: str, *, allow_unready: bool = True) -> Dict[str, Any]:
    runtime_key = str(runtime_id or "").strip().lower()
    with _LOCK:
        runtime = get_runtime(runtime_key, probe=True)
        if runtime is None:
            raise RuntimeRegistryError("Runtime not found")
        if not allow_unready and runtime.get("status") != "ready":
            raise RuntimeRegistryError("Runtime is not ready")
        state = _read_state(_state_path())
        state["selected_runtime_id"] = runtime_key
        _write_state(state)
        runtime["selected"] = True
        return runtime


def resolve_runtime_id(
    *,
    request_runtime_id: Optional[str] = None,
    profile_runtime_id: Optional[str] = None,
    legacy_runtime_mode: Optional[str] = None,
) -> Dict[str, Any]:
    """Resolve request → profile → global → legacy mode → Nirvana."""
    candidates: List[tuple[str, str]] = []
    if request_runtime_id:
        candidates.append((str(request_runtime_id).strip().lower(), "request"))
    if profile_runtime_id:
        candidates.append((str(profile_runtime_id).strip().lower(), "profile"))

    legacy = str(legacy_runtime_mode or "").strip().lower()
    global_id = selected_runtime_id()
    # The default global value is implicit legacy state, not an explicit user
    # override. Preserve old local/external runtime_mode behavior until a user
    # selects a non-default runtime (or binds a request/profile explicitly).
    if not (global_id == "nirvana-default" and legacy in {"local", "external"}):
        candidates.append((global_id, "global"))
    if legacy == "local":
        candidates.append(("nirvana-default", "legacy-local"))
    elif legacy == "external":
        candidates.append(("openai-compatible:legacy-external", "legacy-external"))
    else:
        candidates.append(("nirvana-default", "legacy-auto"))

    if request_runtime_id and get_runtime(str(request_runtime_id).strip().lower()) is None:
        raise RuntimeRegistryError("Requested runtime was not found")
    if profile_runtime_id and get_runtime(str(profile_runtime_id).strip().lower()) is None:
        raise RuntimeRegistryError("Profile runtime was not found")

    for runtime_id, source in candidates:
        runtime = get_runtime(runtime_id)
        if runtime is not None:
            return {"runtime": runtime, "binding_source": source, "requested_runtime_id": request_runtime_id}
    runtime = nirvana_descriptor()
    return {"runtime": runtime, "binding_source": "default", "requested_runtime_id": request_runtime_id}


def reset_registry_for_tests(path: Optional[str] = None) -> None:
    """Reset transient state and optionally redirect persistence for isolated tests."""
    global _TEST_DATA_FILE
    with _LOCK:
        _HEALTH_CACHE.clear()
        _TEST_DATA_FILE = Path(path) if path else None
        if _TEST_DATA_FILE:
            _TEST_DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
            _write_state({"schema_version": SCHEMA_VERSION, "selected_runtime_id": "nirvana-default", "registrations": []})


def runtime_capabilities(runtime_id: str) -> Dict[str, Any]:
    runtime = get_runtime(runtime_id)
    if runtime is None:
        raise RuntimeRegistryError("Runtime not found")
    return {
        "runtime_id": runtime["runtime_id"],
        "capabilities": runtime["capabilities"],
        "available": runtime.get("status") == "ready",
    }


def runtime_endpoint(runtime_id: str) -> Optional[str]:
    """Return a validated runtime endpoint for backend adapters."""
    runtime = get_runtime(runtime_id)
    endpoint = runtime.get("endpoint") if runtime else None
    return _normalize_endpoint_url(endpoint) if isinstance(endpoint, dict) else None
