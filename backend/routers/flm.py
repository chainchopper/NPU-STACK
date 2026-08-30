"""
FastFlowLM (FLM) Router — /api/flm endpoints.

Exposes NPU-first inference via the FastFlowLM runtime:
  GET  /api/flm/status   — Is FLM installed? Server running?
  GET  /api/flm/models   — List available + catalog models
  POST /api/flm/pull     — Pull a model by tag
  POST /api/flm/serve    — Start the FLM OpenAI server
  POST /api/flm/stop     — Stop the FLM server
  POST /api/flm/chat     — Proxy chat to FLM (streaming SSE supported)
"""

import json
import logging
from typing import Optional, List

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from services.flm_service import (
    detect_flm,
    list_models,
    pull_model,
    check_model,
    start_server,
    stop_server,
    get_server_status,
    proxy_chat,
    FLM_MODEL_CATALOG,
    FLM_INSTALLER_URL,
)

logger = logging.getLogger("flm_router")

router = APIRouter(prefix="/api/flm", tags=["fastflowlm"])


# ────────────────────────────────────────────
# Schemas
# ────────────────────────────────────────────

class PullRequest(BaseModel):
    tag: str = Field(..., description="Model tag to pull, e.g. 'llama3.2:1b'")
    force: bool = Field(False, description="Force re-download")


class ServeRequest(BaseModel):
    model: str = Field(..., description="Model tag to serve, e.g. 'llama3.2:1b'")
    port: int = Field(52625, description="Port for the FLM server")


class CheckRequest(BaseModel):
    tag: str = Field(..., description="Model tag to check, e.g. 'qwen3:4b'")


class ChatMessage(BaseModel):
    role: str = Field(..., description="Role: system, user, or assistant")
    content: str = Field(..., description="Message content")


class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    model: str = Field("", description="Override model (usually auto-detected)")
    temperature: float = Field(0.7, ge=0, le=2)
    max_tokens: int = Field(2048, ge=1, le=131072)
    top_p: float = Field(1.0, ge=0, le=1)
    stream: bool = Field(True, description="Stream response via SSE")


# ────────────────────────────────────────────
# Routes
# ────────────────────────────────────────────

@router.get("/status")
async def flm_status():
    """Check FastFlowLM installation and server status."""
    return await get_server_status()


@router.get("/models")
async def flm_models():
    """List locally-available FLM models + full catalog for discovery."""
    local = list_models()
    local_tags = {m["tag"] for m in local}

    # Merge catalog with local status
    catalog = []
    for m in FLM_MODEL_CATALOG:
        catalog.append({
            **m,
            "installed": m["tag"] in local_tags,
        })

    # Include any local models not in catalog
    for m in local:
        if m["tag"] not in {c["tag"] for c in catalog}:
            catalog.append({
                **m,
                "family": "Other",
                "params": "",
                "type": "llm",
                "ctx": "",
                "installed": True,
            })

    return {
        "local": local,
        "catalog": catalog,
        "local_count": len(local),
        "catalog_count": len(catalog),
    }


@router.post("/pull")
async def flm_pull(body: PullRequest):
    """Pull/download a model by tag. Streams progress."""
    info = detect_flm()
    if not info["installed"]:
        raise HTTPException(
            503,
            "FastFlowLM is not installed. Download from: " + FLM_INSTALLER_URL
        )

    async def stream():
        async for line in pull_model(body.tag, force=body.force):
            yield f"data: {line}\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/check")
async def flm_check(body: CheckRequest):
    """Run `flm check` diagnostics for a local model tag."""
    info = detect_flm()
    if not info["installed"]:
        raise HTTPException(
            503,
            "FastFlowLM is not installed. Download from: " + FLM_INSTALLER_URL
        )

    result = check_model(body.tag)
    if result.get("status") == "error" and result.get("message") == "FLM binary not found on PATH":
        raise HTTPException(503, result["message"])
    return result


@router.post("/serve")
async def flm_serve(body: ServeRequest):
    """Start the FLM server for a given model."""
    info = detect_flm()
    if not info["installed"]:
        raise HTTPException(
            503,
            "FastFlowLM is not installed. Download from: " + FLM_INSTALLER_URL
        )

    result = await start_server(body.model, body.port)
    if result["status"] == "error":
        raise HTTPException(500, result.get("message", "Failed to start FLM server"))
    return result


@router.post("/stop")
async def flm_stop():
    """Stop the managed FLM server."""
    result = await stop_server()
    return result


@router.post("/chat")
async def flm_chat(body: ChatRequest):
    """Proxy a chat completion to the running FLM server."""
    # Verify server is up
    status = await get_server_status()
    if not status["server_running"]:
        raise HTTPException(
            503,
            "FLM server is not running. Start it first via POST /api/flm/serve"
        )

    messages = [{"role": m.role, "content": m.content} for m in body.messages]

    try:
        if body.stream:
            stream_gen = await proxy_chat(
                messages=messages,
                model=body.model,
                temperature=body.temperature,
                max_tokens=body.max_tokens,
                top_p=body.top_p,
                stream=True,
            )

            async def sse():
                async for chunk in stream_gen:
                    yield chunk

            return StreamingResponse(sse(), media_type="text/event-stream")
        else:
            result = await proxy_chat(
                messages=messages,
                model=body.model,
                temperature=body.temperature,
                max_tokens=body.max_tokens,
                top_p=body.top_p,
                stream=False,
            )
            return result

    except Exception as e:
        logger.error(f"FLM chat proxy error: {e}")
        raise HTTPException(502, f"Error communicating with FLM server: {e}")
