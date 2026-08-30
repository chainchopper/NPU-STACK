"""Universal agent runtime catalog, discovery, and selection API."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.agent_runtime_registry import (
    RuntimeRegistryError,
    discover,
    get_runtime,
    list_runtimes,
    probe_runtime,
    register_runtime,
    runtime_capabilities,
    selected_runtime_id,
    select_runtime,
    unregister_runtime,
    update_runtime,
)

router = APIRouter(prefix="/api/agent-runtimes", tags=["agent-runtimes"])


class RuntimeRegistrationPayload(BaseModel):
    runtime_id: Optional[str] = Field(default=None, max_length=120)
    display_name: str = Field(..., min_length=1, max_length=160)
    description: Optional[str] = Field(default=None, max_length=500)
    adapter: str = Field(default="openai-compatible", max_length=40)
    endpoint: str = Field(..., min_length=1, max_length=2048)
    credential_env_var: Optional[str] = Field(default=None, max_length=128)
    allow_insecure_http: bool = False
    capabilities: Optional[Dict[str, bool]] = None


class RuntimeSelectionPayload(BaseModel):
    runtime_id: str = Field(..., min_length=1, max_length=120)
    allow_unready: bool = True


class DiscoveryPayload(BaseModel):
    probe: bool = True


def _error(exc: RuntimeRegistryError, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": "runtime_registry_error", "message": str(exc)})


@router.get("")
@router.get("/")
def catalog(probe: bool = False) -> Dict[str, Any]:
    """Return the credential-free catalog of supported agent runtimes."""
    runtimes = list_runtimes(probe=probe)
    return {
        "schema_version": 1,
        "selected_runtime_id": selected_runtime_id(),
        "runtimes": runtimes,
        "count": len(runtimes),
    }


@router.post("/discover")
def discover_runtimes(payload: DiscoveryPayload = DiscoveryPayload()) -> Dict[str, Any]:
    """Refresh bounded, read-only discovery of known local/configured runtimes."""
    runtimes = discover(probe=payload.probe)
    return {
        "schema_version": 1,
        "selected_runtime_id": selected_runtime_id(),
        "runtimes": runtimes,
        "count": len(runtimes),
        "discovery": {
            "mode": "bounded-configured-endpoints",
            "read_only": True,
            "process_launch": False,
            "subnet_scan": False,
        },
    }


@router.get("/{runtime_id}")
def runtime_detail(runtime_id: str, probe: bool = False) -> Dict[str, Any]:
    runtime = get_runtime(runtime_id, probe=probe)
    if runtime is None:
        raise HTTPException(404, detail={"code": "runtime_not_found", "runtime_id": runtime_id})
    return runtime


@router.post("/{runtime_id}/probe")
def runtime_probe(runtime_id: str) -> Dict[str, Any]:
    try:
        return probe_runtime(runtime_id)
    except RuntimeRegistryError as exc:
        raise _error(exc, 404) from exc


@router.get("/{runtime_id}/capabilities")
def runtime_capabilities_detail(runtime_id: str) -> Dict[str, Any]:
    try:
        return runtime_capabilities(runtime_id)
    except RuntimeRegistryError as exc:
        raise _error(exc, 404) from exc


@router.get("/{runtime_id}/availability/{capability}")
def runtime_availability(runtime_id: str, capability: str) -> Dict[str, Any]:
    runtime = get_runtime(runtime_id)
    if runtime is None:
        raise HTTPException(404, detail={"code": "runtime_not_found", "runtime_id": runtime_id})
    known = capability in runtime.get("capabilities", {})
    available = bool(known and runtime["capabilities"].get(capability) and runtime.get("status") == "ready")
    return {
        "runtime_id": runtime_id,
        "capability": capability,
        "available": available,
        "supported": bool(known and runtime["capabilities"].get(capability)),
        "status": runtime.get("status"),
        "reason": None if available else ("capability_not_supported" if not known or not runtime["capabilities"].get(capability) else "runtime_unavailable"),
    }


@router.post("/register")
def runtime_register(payload: RuntimeRegistrationPayload) -> Dict[str, Any]:
    try:
        return register_runtime(payload.model_dump(exclude_none=True))
    except RuntimeRegistryError as exc:
        raise _error(exc) from exc


@router.patch("/{runtime_id}")
def runtime_update(runtime_id: str, payload: RuntimeRegistrationPayload) -> Dict[str, Any]:
    try:
        data = payload.model_dump(exclude_none=True)
        data.pop("runtime_id", None)
        return update_runtime(runtime_id, data)
    except RuntimeRegistryError as exc:
        raise _error(exc, 404 if "Only explicitly" in str(exc) else 400) from exc


@router.delete("/{runtime_id}")
def runtime_delete(runtime_id: str) -> Dict[str, Any]:
    try:
        unregister_runtime(runtime_id)
    except RuntimeRegistryError as exc:
        raise _error(exc, 404 if "Only explicitly" in str(exc) else 400) from exc
    return {"status": "removed", "runtime_id": runtime_id, "selected_runtime_id": selected_runtime_id()}


@router.get("/selection/current")
def current_selection() -> Dict[str, Any]:
    runtime_id = selected_runtime_id()
    return {"selected_runtime_id": runtime_id, "runtime": get_runtime(runtime_id)}


@router.put("/selection")
def set_selection(payload: RuntimeSelectionPayload) -> Dict[str, Any]:
    try:
        runtime = select_runtime(payload.runtime_id, allow_unready=payload.allow_unready)
    except RuntimeRegistryError as exc:
        raise _error(exc, 404 if "not found" in str(exc).lower() else 409) from exc
    return {"selected_runtime_id": runtime["runtime_id"], "runtime": runtime}
