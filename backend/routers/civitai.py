"""Civitai Hub router — search and download models from Civitai."""

import hashlib
import json
import os
import shutil
import time
from pathlib import Path
from typing import Optional
from urllib.parse import quote, urlparse

import httpx

from fastapi import APIRouter, Depends, HTTPException, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from database import get_db, ModelRecord

router = APIRouter(prefix="/api/civitai", tags=["civitai"])

MODEL_STORE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "models")
os.makedirs(MODEL_STORE, exist_ok=True)

MEDIA_CACHE_DIR = Path(os.path.dirname(os.path.dirname(__file__))) / "data" / "civitai_media_cache"
MEDIA_CACHE_DIR.mkdir(parents=True, exist_ok=True)

CIVITAI_API_URL = "https://civitai.com/api/v1"
CIVITAI_MEDIA_CACHE_TTL_SECONDS = 60 * 60 * 24
_CIVITAI_MEDIA_ALLOWED_HOSTS = {"civitai.com", "image.civitai.com", "image-b.civitai.com", "image-b2.civitai.com"}
_MEDIA_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/apng": ".apng",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "video/webm": ".webm",
}

def _get_api_key():
    return os.environ.get("CIVITAI_API_KEY") or None


def _build_headers() -> dict:
    headers = {"Accept": "application/json"}
    api_key = _get_api_key()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _build_media_headers() -> dict:
    headers = {
        "Accept": "image/*,video/*;q=0.9,*/*;q=0.1",
        "User-Agent": "NPU-STACK/1.0",
    }
    api_key = _get_api_key()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _coerce_int(value) -> Optional[int]:
    try:
        parsed = int(value)
        return parsed if parsed > 0 else None
    except (TypeError, ValueError):
        return None


def _is_allowed_civitai_media_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except Exception:
        return False

    if parsed.scheme not in {"http", "https"}:
        return False

    host = (parsed.hostname or "").lower()
    return host in _CIVITAI_MEDIA_ALLOWED_HOSTS or host.endswith(".civitai.com")


def _cache_key_for_url(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def _cache_meta_path(cache_key: str) -> Path:
    return MEDIA_CACHE_DIR / f"{cache_key}.json"


def _guess_media_extension(content_type: str, source_url: str) -> str:
    cleaned_content_type = (content_type or "").split(";", 1)[0].strip().lower()
    if cleaned_content_type in _MEDIA_EXTENSIONS:
        return _MEDIA_EXTENSIONS[cleaned_content_type]

    path_suffix = Path(urlparse(source_url).path).suffix.lower()
    if path_suffix in {".jpg", ".jpeg", ".png", ".apng", ".gif", ".webp", ".webm"}:
        return ".jpg" if path_suffix == ".jpeg" else path_suffix

    return ".bin"


def _cache_file_path(cache_key: str, extension: str) -> Path:
    return MEDIA_CACHE_DIR / f"{cache_key}{extension}"


def _read_cached_media(cache_key: str) -> Optional[dict]:
    meta_path = _cache_meta_path(cache_key)
    if not meta_path.exists():
        return None
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_cached_media(cache_key: str, metadata: dict):
    _cache_meta_path(cache_key).write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def _cache_is_fresh(metadata: Optional[dict]) -> bool:
    if not metadata:
        return False
    cached_at = metadata.get("cached_at") or 0
    try:
        cached_at = float(cached_at)
    except (TypeError, ValueError):
        return False
    return (time.time() - cached_at) < CIVITAI_MEDIA_CACHE_TTL_SECONDS


def _infer_media_kind(url: str, explicit_type: Optional[str] = None) -> str:
    lowered_type = str(explicit_type or "").strip().lower()
    lowered_url = (url or "").lower()

    if lowered_type in {"image", "video"}:
        return lowered_type
    if lowered_url.endswith(".webm"):
        return "video"
    return "image"


def _aspect_preset(width: Optional[int], height: Optional[int]) -> str:
    if width and height:
        ratio = width / height
        if abs(ratio - 1.0) <= 0.12:
            return "square"
        if ratio < 0.8:
            return "portrait"
        return "landscape"
    return "square"


def _aspect_ratio(width: Optional[int], height: Optional[int]) -> str:
    if width and height:
        return f"{width} / {height}"
    return "1 / 1"


def _build_media_proxy_url(url: str) -> str:
    return f"/api/civitai/media?url={quote(url, safe='')}"


def _normalize_media_asset(image: dict) -> Optional[dict]:
    if not isinstance(image, dict):
        return None

    url = image.get("url")
    if not url:
        return None

    width = _coerce_int(image.get("width"))
    height = _coerce_int(image.get("height"))
    media_kind = _infer_media_kind(url, image.get("type"))

    normalized = dict(image)
    normalized.update({
        "media_kind": media_kind,
        "proxy_url": _build_media_proxy_url(url),
        "aspect_ratio": _aspect_ratio(width, height),
        "aspect_preset": _aspect_preset(width, height),
        "width": width,
        "height": height,
    })
    return normalized


def _first_media_asset(item: dict) -> Optional[dict]:
    for version in item.get("modelVersions", []) or []:
        for image in version.get("images", []) or []:
            asset = _normalize_media_asset(image)
            if asset:
                return asset
    return None


def _augment_model_detail_payload(payload: dict) -> dict:
    if not isinstance(payload, dict):
        return payload

    enriched = dict(payload)
    versions = []
    for version in payload.get("modelVersions", []) or []:
        version_copy = dict(version)
        version_copy["images"] = [
            asset for asset in (_normalize_media_asset(image) for image in version.get("images", []) or []) if asset
        ]
        version_copy["preview_media"] = version_copy["images"][0] if version_copy["images"] else None
        versions.append(version_copy)
    enriched["modelVersions"] = versions
    return enriched

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
                preview_media = _first_media_asset(item)
                models.append({
                    "id": str(item.get("id")),
                    "name": item.get("name"),
                    "type": item.get("type"),
                    "creator": item.get("creator", {}).get("username"),
                    "stats": item.get("stats", {}),
                    "tags": item.get("tags", []),
                    "thumbnail": preview_media.get("proxy_url") if preview_media else None,
                    "thumbnail_original_url": preview_media.get("url") if preview_media else None,
                    "thumbnail_type": preview_media.get("media_kind") if preview_media else None,
                    "thumbnail_width": preview_media.get("width") if preview_media else None,
                    "thumbnail_height": preview_media.get("height") if preview_media else None,
                    "thumbnail_aspect_ratio": preview_media.get("aspect_ratio") if preview_media else "1 / 1",
                    "thumbnail_aspect_preset": preview_media.get("aspect_preset") if preview_media else "square",
                    "preview_media": preview_media,
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
            return _augment_model_detail_payload(response.json())
        except Exception as e:
            raise HTTPException(500, f"Failed to get Civitai model details: {str(e)}")


@router.get("/media")
async def get_civitai_media(url: str):
    """Proxy and cache Civitai media locally so the frontend does not hotlink the CDN directly."""
    if not _is_allowed_civitai_media_url(url):
        raise HTTPException(400, "Unsupported Civitai media URL")

    cache_key = _cache_key_for_url(url)
    metadata = _read_cached_media(cache_key)
    cached_file = Path(metadata.get("file_path", "")) if metadata else None

    def _serve_cached_file(meta: dict, stale: bool = False):
        file_path = Path(meta["file_path"])
        headers = {
            "Cache-Control": f"public, max-age={CIVITAI_MEDIA_CACHE_TTL_SECONDS}",
            "X-Civitai-Cache": "HIT" if not stale else "STALE",
        }
        return FileResponse(
            file_path,
            media_type=meta.get("content_type") or "application/octet-stream",
            filename=file_path.name,
            headers=headers,
        )

    if metadata and cached_file and cached_file.exists() and _cache_is_fresh(metadata):
        return _serve_cached_file(metadata)

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=45.0) as client:
            async with client.stream("GET", url, headers=_build_media_headers()) as response:
                response.raise_for_status()
                final_url = str(response.url)
                content_type = response.headers.get("Content-Type", "application/octet-stream").split(";", 1)[0].strip()
                extension = _guess_media_extension(content_type, final_url)
                output_path = _cache_file_path(cache_key, extension)
                temp_path = _cache_file_path(cache_key, ".tmp")

                with open(temp_path, "wb") as fh:
                    async for chunk in response.aiter_bytes():
                        fh.write(chunk)

                if output_path.exists() and output_path != temp_path:
                    output_path.unlink()
                temp_path.replace(output_path)

                metadata = {
                    "cache_key": cache_key,
                    "source_url": url,
                    "final_url": final_url,
                    "content_type": content_type,
                    "file_path": str(output_path),
                    "cached_at": time.time(),
                }
                _write_cached_media(cache_key, metadata)
                return _serve_cached_file(metadata)
    except Exception as exc:
        if metadata and cached_file and cached_file.exists():
            return _serve_cached_file(metadata, stale=True)
        raise HTTPException(502, f"Failed to cache Civitai media: {str(exc)}")

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
