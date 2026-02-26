from fastapi import APIRouter, HTTPException
from typing import Dict, Any
from pydantic import BaseModel

from services.nim_service import (
    get_nim_status,
    fetch_cloud_models,
    start_local_nim,
    stop_local_nim
)

router = APIRouter(prefix="/api/nim", tags=["NVIDIA NIM"])

class StartNimRequest(BaseModel):
    image: str
    port: int = 8000
    gpus: str = "all"

class StopNimRequest(BaseModel):
    container_id: str

@router.get("/status")
def nim_status() -> Dict[str, Any]:
    """Get status of NVIDIA NIM cloud access and local docker containers."""
    return get_nim_status()

@router.get("/models")
async def list_nim_models():
    """List available NIM models from the cloud API."""
    models = await fetch_cloud_models()
    return {"models": models}

@router.post("/containers/start")
def start_container(req: StartNimRequest):
    """Start a local NVIDIA NIM docker container."""
    res = start_local_nim(req.image, req.port, req.gpus)
    if not res["success"]:
        raise HTTPException(status_code=400, detail=res.get("error"))
    return res

@router.post("/containers/stop")
def stop_container(req: StopNimRequest):
    """Stop a local NVIDIA NIM container."""
    res = stop_local_nim(req.container_id)
    if not res["success"]:
        raise HTTPException(status_code=400, detail=res.get("error"))
    return res
