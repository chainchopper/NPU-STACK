"""LM Studio provider router — lmlink-style multi-instance client.

Proxies the native LM Studio API (``/api/v1/*``) and the OpenAI-compatible
surface (``/v1/*``) across one or more "linked" instances, so edge devices and
boards can offload inference to paired machines that have bigger compute.

Instances are persisted to ``backend/data/lmstudio_instances.json``. The
``local`` instance always mirrors ``LMSTUDIO_BASE_URL`` / ``LMSTUDIO_API_KEY``
from the environment (.env).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/lmstudio", tags=["lmstudio"])

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "lmstudio_instances.json"

DEFAULT_INSTANCE = {
    "id": "local",
    "name": "Local LM Studio",
    "base_url": os.environ.get("LMSTUDIO_BASE_URL", "http://localhost:443").rstrip("/"),
    "api_key": os.environ.get("LMSTUDIO_API_KEY", ""),
}


def _normalize_base_url(value: str) -> str:
    """Store LM Studio's server root, not an OpenAI ``/v1`` subpath."""
    normalized = str(value or "").strip().rstrip("/")
    for suffix in ("/api/v1", "/v1"):
        if normalized.lower().endswith(suffix):
            normalized = normalized[: -len(suffix)].rstrip("/")
            break
    return normalized


DEFAULT_INSTANCE["base_url"] = _normalize_base_url(DEFAULT_INSTANCE["base_url"])


# ── Instance registry ────────────────────────────────────────────────

def _load_instances() -> List[dict]:
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        return [i for i in data.get("instances", []) if i.get("base_url")]
    except Exception:
        return []


def _save_instances(instances: List[dict]) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps({"instances": instances}, indent=2), encoding="utf-8")


def _instances() -> List[dict]:
    """Registered instances; the env 'local' instance is always first."""
    stored = [i for i in _load_instances() if i.get("id") != "local"]
    return [dict(DEFAULT_INSTANCE)] + [
        {**instance, "base_url": _normalize_base_url(instance.get("base_url", ""))}
        for instance in stored
    ]


def _public_instance(instance: dict) -> dict:
    """Return instance metadata without exposing persisted credentials."""
    return {
        key: value
        for key, value in instance.items()
        if key != "api_key"
    } | {"api_key_configured": bool(instance.get("api_key"))}


def _client(instance: dict) -> httpx.AsyncClient:
    headers = {"Authorization": f"Bearer {instance['api_key']}"} if instance.get("api_key") else {}
    return httpx.AsyncClient(
        base_url=instance["base_url"].rstrip("/"),
        headers=headers,
        timeout=180,
        verify=False,  # LM Studio uses self-signed certs
    )


async def _any_client() -> tuple[dict, httpx.AsyncClient]:
    """Return the first reachable instance + client (fallback: local)."""
    last_err: Optional[Exception] = None
    for inst in _instances():
        client = _client(inst)
        try:
            resp = await client.get("/v1/models")
            if resp.status_code == 200:
                return inst, client
        except Exception as exc:  # noqa: BLE001
            last_err = exc
        await client.aclose()
    if last_err:
        raise HTTPException(502, f"No LM Studio instance reachable: {last_err}")
    local = dict(DEFAULT_INSTANCE)
    return local, _client(local)


# ── Models ───────────────────────────────────────────────────────────

class InstanceCreate(BaseModel):
    id: str
    name: Optional[str] = None
    base_url: str
    api_key: Optional[str] = None


class ChatRequest(BaseModel):
    model: str = ""
    messages: Optional[List[Dict[str, str]]] = None  # OpenAI-compatible
    system_prompt: Optional[str] = None             # native API
    input: Optional[str] = None                     # native API
    temperature: float = 0.7
    max_tokens: int = 4096


@router.get("/instances")
async def list_instances():
    """List linked LM Studio instances (lmlink)."""
    instances = _instances()
    return {"instances": [_public_instance(instance) for instance in instances], "count": len(instances)}


@router.post("/instances")
async def add_instance(req: InstanceCreate):
    """Link a new LM Studio instance (e.g. a remote GPU box) for offloading."""
    instances = [i for i in _load_instances() if i.get("id") != req.id]
    instances.append({
        "id": req.id,
        "name": req.name or req.id,
        "base_url": _normalize_base_url(req.base_url),
        "api_key": req.api_key or "",
    })
    _save_instances(instances)
    return {"status": "linked", "instances": [_public_instance(instance) for instance in _instances()]}


@router.delete("/instances/{instance_id}")
async def remove_instance(instance_id: str):
    """Unlink an LM Studio instance."""
    if instance_id == "local":
        raise HTTPException(400, "The local instance cannot be removed")
    instances = [i for i in _load_instances() if i.get("id") != instance_id]
    _save_instances(instances)
    return {"status": "unlinked", "instances": [_public_instance(instance) for instance in _instances()]}


@router.get("/models")
async def list_models():
    """List loaded models across instances (native /api/v1/models)."""
    out = {"instances": [], "loaded": []}
    seen = set()
    for inst in _instances():
        client = _client(inst)
        entry = {"id": inst["id"], "name": inst.get("name"), "base_url": inst["base_url"], "models": []}
        try:
            resp = await client.get("/api/v1/models")
            if resp.status_code == 200:
                data = resp.json()
                for m in data.get("data", []):
                    mid = m.get("id") or m.get("path") or ""
                    entry["models"].append(m)
                    if mid and mid not in seen:
                        seen.add(mid)
                        out["loaded"].append(m)
        except Exception as exc:  # noqa: BLE001
            entry["error"] = str(exc)
        finally:
            await client.aclose()
        out["instances"].append(entry)
    return out


@router.get("/status")
async def status():
    """Health of every linked instance."""
    results = []
    for inst in _instances():
        client = _client(inst)
        ok = False
        try:
            resp = await client.get("/v1/models")
            ok = resp.status_code == 200
        except Exception:  # noqa: BLE001
            ok = False
        finally:
            await client.aclose()
        results.append({"id": inst["id"], "name": inst.get("name"), "base_url": inst["base_url"], "connected": ok})
    return {"instances": results, "any_connected": any(r["connected"] for r in results)}


# ── Inference ────────────────────────────────────────────────────────

@router.post("/chat")
async def chat(req: ChatRequest):
    """Chat via LM Studio. Uses the native /api/v1/chat when `input` is given,
    otherwise the OpenAI-compatible /v1/chat/completions."""
    inst, client = await _any_client()
    try:
        if req.input is not None:
            payload = {
                "model": req.model,
                "system_prompt": req.system_prompt or "",
                "input": req.input,
                "temperature": req.temperature,
            }
            resp = await client.post("/api/v1/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
            content = ""
            reasoning = ""
            for block in data.get("output", []):
                if block.get("type") == "message":
                    content += block.get("content", "")
                elif block.get("type") == "reasoning":
                    reasoning += block.get("content", "")
            return {
                "provider": "lmstudio",
                "instance": inst["id"],
                "model": req.model or data.get("model_instance_id", ""),
                "response": content,
                "reasoning": reasoning,
                "stats": data.get("stats", {}),
            }
        else:
            messages = req.messages or []
            payload = {
                "model": req.model,
                "messages": messages,
                "temperature": req.temperature,
                "max_tokens": req.max_tokens,
                "stream": False,
            }
            resp = await client.post("/v1/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return {
                "provider": "lmstudio",
                "instance": inst["id"],
                "model": data.get("model", req.model),
                "response": data["choices"][0]["message"]["content"] if data.get("choices") else "",
                "usage": data.get("usage", {}),
            }
    except httpx.ConnectError:
        raise HTTPException(502, "LM Studio not reachable")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"LM Studio chat error: {exc}")
    finally:
        await client.aclose()


@router.post("/models/load")
async def load_model(model_id: str = "", instance_id: str = "local"):
    """Load a model (native /api/v1/models/load) on a linked instance."""
    inst = next((i for i in _instances() if i.get("id") == instance_id), None)
    if not inst:
        raise HTTPException(404, f"Instance '{instance_id}' not linked")
    client = _client(inst)
    try:
        payload = {"model": model_id} if model_id else {}
        resp = await client.post("/api/v1/models/load", json=payload)
        resp.raise_for_status()
        return {"provider": "lmstudio", "instance": instance_id, "status": "loaded", "data": resp.json()}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"LM Studio load error: {exc}")
    finally:
        await client.aclose()

