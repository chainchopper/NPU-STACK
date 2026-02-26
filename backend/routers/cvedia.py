from fastapi import APIRouter, HTTPException
from typing import Dict, Any
from pydantic import BaseModel

from services.cvedia_service import get_cvedia_status, process_video

router = APIRouter(prefix="/api/cvedia", tags=["CVEDIA-RT"])

class CvediaProcessRequest(BaseModel):
    video_path: str
    model: str = "person_detection"

@router.get("/status")
def cvedia_status() -> Dict[str, Any]:
    """Get status of CVEDIA-RT installation and Python bindings."""
    return get_cvedia_status()

@router.post("/process")
def run_cvedia_process(req: CvediaProcessRequest):
    """Process a video stream using CVEDIA-RT."""
    res = process_video(req.video_path, req.model)
    if not res["success"]:
        raise HTTPException(status_code=400, detail=res.get("error"))
    return res
