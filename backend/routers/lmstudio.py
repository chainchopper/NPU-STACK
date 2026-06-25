"""LM Studio provider router — proxy to local LM Studio API."""
import os
import httpx
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/lmstudio", tags=["lmstudio"])

LMSTUDIO_BASE = os.environ.get("LMSTUDIO_BASE_URL", "https://100.100.2.93:443/v1")
LMSTUDIO_KEY = os.environ.get("LMSTUDIO_API_KEY", "")

_client: Optional[httpx.AsyncClient] = None

def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        headers = {"Authorization": f"Bearer {LMSTUDIO_KEY}"} if LMSTUDIO_KEY else {}
        _client = httpx.AsyncClient(
            base_url=LMSTUDIO_BASE.strip("/"),
            headers=headers,
            timeout=30,
            verify=False,  # LM Studio uses self-signed certs
        )
    return _client


@router.get("/models")
async def list_models():
    """List models loaded/available in LM Studio."""
    try:
        client = _get_client()
        resp = await client.get("/models")
        resp.raise_for_status()
        data = resp.json()
        return {"provider": "lmstudio", "base_url": LMSTUDIO_BASE, **data}
    except httpx.ConnectError:
        return {"provider": "lmstudio", "base_url": LMSTUDIO_BASE, "status": "offline", "models": []}
    except Exception as e:
        raise HTTPException(502, f"LM Studio error: {e}")


class ChatRequest(BaseModel):
    messages: List[Dict[str, str]]
    model: str = ""
    temperature: float = 0.7
    max_tokens: int = 4096


@router.post("/chat")
async def chat(req: ChatRequest):
    """Send chat completion to LM Studio model."""
    try:
        client = _get_client()
        payload = {
            "messages": req.messages,
            "temperature": req.temperature,
            "max_tokens": req.max_tokens,
            "stream": False,
        }
        if req.model:
            # Get the full model ID from LM Studio
            models_resp = await client.get("/models")
            if models_resp.status_code == 200:
                models_data = models_resp.json()
                for m in models_data.get("data", []):
                    if req.model.lower() in m.get("id", "").lower():
                        payload["model"] = m["id"]
                        break
                if "model" not in payload:
                    payload["model"] = req.model

        resp = await client.post("/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return {
            "provider": "lmstudio",
            "response": data["choices"][0]["message"]["content"] if data.get("choices") else "",
            "model": data.get("model", ""),
            "usage": data.get("usage", {}),
        }
    except httpx.ConnectError:
        raise HTTPException(502, "LM Studio is not running or not reachable")
    except Exception as e:
        raise HTTPException(502, f"LM Studio chat error: {e}")


@router.post("/models/load")
async def load_model(model_id: str = ""):
    """Load a model in LM Studio."""
    try:
        client = _get_client()
        resp = await client.post("/models/load", json={"model": model_id} if model_id else {})
        resp.raise_for_status()
        return {"provider": "lmstudio", "status": "loaded", "data": resp.json()}
    except Exception as e:
        raise HTTPException(502, f"LM Studio load error: {e}")


@router.post("/models/download")
async def download_model(repo_id: str = ""):
    """Download a model from HuggingFace via LM Studio."""
    try:
        client = _get_client()
        resp = await client.post("/models/download", json={"model": repo_id} if repo_id else {})
        resp.raise_for_status()
        return {"provider": "lmstudio", "status": "downloading", "data": resp.json()}
    except Exception as e:
        raise HTTPException(502, f"LM Studio download error: {e}")


@router.get("/models/download/status/{job_id}")
async def download_status(job_id: str):
    """Check download job status in LM Studio."""
    try:
        client = _get_client()
        resp = await client.get(f"/models/download/status/{job_id}")
        resp.raise_for_status()
        return {"provider": "lmstudio", "data": resp.json()}
    except Exception as e:
        raise HTTPException(502, f"LM Studio status error: {e}")


@router.get("/status")
async def status():
    """Quick health check for LM Studio connectivity."""
    try:
        client = _get_client()
        resp = await client.get("/models")
        return {"connected": resp.status_code == 200, "base_url": LMSTUDIO_BASE}
    except Exception:
        return {"connected": False, "base_url": LMSTUDIO_BASE}
