"""Civitai Hub router — search and download models from Civitai."""

import os
import shutil
import httpx
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Form
from sqlalchemy.orm import Session

from database import get_db, ModelRecord

router = APIRouter(prefix="/api/civitai", tags=["civitai"])

MODEL_STORE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "models")
os.makedirs(MODEL_STORE, exist_ok=True)

CIVITAI_API_URL = "https://civitai.com/api/v1"

def _get_api_key():
    return os.environ.get("CIVITAI_API_KEY") or None


def _build_headers() -> dict:
    headers = {"Accept": "application/json"}
    api_key = _get_api_key()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _first_image_url(item: dict) -> Optional[str]:
    for version in item.get("modelVersions", []) or []:
        for image in version.get("images", []) or []:
            url = image.get("url")
            if url:
                return url
    return None

@router.get("/search")
async def search_models(
    q: str = "",
    type: Optional[str] = None,
    limit: int = 20,
    page: int = 1,
):
    """Search Civitai for models."""
    params = {
        "query": q,
        "limit": limit,
    }
    if not q.strip() and page:
        params["page"] = page
    if type:
        params["types"] = type

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{CIVITAI_API_URL}/models",
                params=params,
                headers=_build_headers(),
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()
            
            # Map Civitai response to a consistent format
            models = []
            for item in data.get("items", []):
                models.append({
                    "id": str(item.get("id")),
                    "name": item.get("name"),
                    "type": item.get("type"),
                    "creator": item.get("creator", {}).get("username"),
                    "stats": item.get("stats", {}),
                    "tags": item.get("tags", []),
                    "thumbnail": _first_image_url(item),
                    "versions": [
                        {
                            "id": v.get("id"),
                            "name": v.get("name"),
                            "baseModel": v.get("baseModel"),
                        } for v in item.get("modelVersions", [])
                    ]
                })
            
            return {"models": models, "metadata": data.get("metadata", {})}
        except Exception as e:
            raise HTTPException(500, f"Civitai search failed: {str(e)}")

@router.get("/model/{model_id}")
async def get_model_details(model_id: str):
    """Get detailed info about a Civitai model."""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{CIVITAI_API_URL}/models/{model_id}",
                headers=_build_headers(),
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            raise HTTPException(500, f"Failed to get Civitai model details: {str(e)}")

@router.post("/download")
async def download_model(
    version_id: int = Form(...),
    model_name: str = Form(...),
    db: Session = Depends(get_db),
):
    """Download a specific model version from Civitai."""
    api_key = _get_api_key()
    url = f"{CIVITAI_API_URL}/model-versions/{version_id}/download"
    
    headers = _build_headers()

    # We use a stream to download to avoid loading large files into memory
    try:
        async with httpx.AsyncClient() as client:
            async with client.stream("GET", url, headers=headers, follow_redirects=True) as response:
                if response.status_code != 200:
                    raise HTTPException(response.status_code, "Failed to initiate download from Civitai")
                
                # Get filename from headers or use model_name
                content_disposition = response.headers.get("Content-Disposition", "")
                filename = model_name
                if "filename=" in content_disposition:
                    filename = content_disposition.split("filename=")[1].strip('"')
                
                safe_name = filename.replace("/", "_").replace(" ", "_")
                dest_path = os.path.join(MODEL_STORE, safe_name)
                
                with open(dest_path, "wb") as f:
                    async for chunk in response.iter_bytes():
                        f.write(chunk)
                
                file_size = os.path.getsize(dest_path)
                
                # Register the model
                record = ModelRecord(
                    name=os.path.splitext(filename)[0],
                    framework="civitai",
                    format=os.path.splitext(filename)[1].lstrip(".").lower() or "unknown",
                    file_path=dest_path,
                    file_size=file_size,
                    size_mb=file_size / (1024 * 1024),
                    description=f"Downloaded from Civitai (Version ID: {version_id})",
                )
                db.add(record)
                db.commit()
                db.refresh(record)
                
                return {
                    "id": record.id,
                    "name": record.name,
                    "path": dest_path,
                    "message": f"Successfully downloaded {filename} from Civitai",
                }
    except Exception as e:
        raise HTTPException(500, f"Civitai download failed: {str(e)}")
