"""HuggingFace Hub router — search, browse, and download models from HuggingFace."""

import os
import shutil
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Form
from sqlalchemy.orm import Session

from database import get_db, ModelRecord

router = APIRouter(prefix="/api/huggingface", tags=["huggingface"])

MODEL_STORE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "models")
os.makedirs(MODEL_STORE, exist_ok=True)


def _get_token():
    return os.environ.get("HUGGINGFACE_TOKEN") or None


def _get_api():
    try:
        from huggingface_hub import HfApi
        return HfApi(token=_get_token())
    except ImportError:
        raise HTTPException(500, "huggingface_hub not installed. Run: pip install huggingface_hub")


@router.get("/search")
def search_models(
    q: str = "",
    task: Optional[str] = None,
    sort: str = "downloads",
    direction: str = "-1",
    limit: int = 20,
):
    """Search HuggingFace Hub for models.

    Tasks: image-classification, object-detection, text-generation,
           text2text-generation, image-to-text, text-to-image,
           feature-extraction, automatic-speech-recognition, etc.
    """
    api = _get_api()

    try:
        # Newer huggingface_hub uses pipeline_tag instead of task
        kwargs = {"limit": limit}
        if q:
            kwargs["search"] = q
        if task:
            kwargs["pipeline_tag"] = task
        try:
            kwargs["sort"] = sort
            kwargs["direction"] = int(direction)
        except Exception:
            pass

        try:
            models = api.list_models(**kwargs)
        except TypeError:
            # Fallback for older API versions
            kwargs.pop("pipeline_tag", None)
            if task:
                kwargs["task"] = task
            models = api.list_models(**kwargs)

        results = []
        for m in models:
            results.append({
                "id": m.id,
                "author": m.author,
                "task": m.pipeline_tag,
                "downloads": m.downloads,
                "likes": m.likes,
                "tags": m.tags[:10] if m.tags else [],
                "last_modified": str(m.last_modified) if m.last_modified else None,
                "private": m.private,
            })

        return {"query": q, "task": task, "count": len(results), "models": results}

    except Exception as e:
        raise HTTPException(500, f"HuggingFace search failed: {str(e)}")


@router.get("/model/{repo_id:path}")
def get_model_details(repo_id: str):
    """Get detailed info about a HuggingFace model including its files."""
    api = _get_api()

    try:
        info = api.model_info(repo_id, token=_get_token())

        # List files
        files = []
        try:
            from huggingface_hub import list_repo_files
            file_list = list_repo_files(repo_id, token=_get_token())
            for f in file_list:
                ext = os.path.splitext(f)[1].lower()
                files.append({
                    "name": f,
                    "is_model": ext in (".onnx", ".pt", ".pth", ".bin", ".safetensors", ".xml", ".tflite", ".pb"),
                })
        except Exception:
            pass

        return {
            "id": info.id,
            "author": info.author,
            "task": info.pipeline_tag,
            "downloads": info.downloads,
            "likes": info.likes,
            "tags": info.tags[:20] if info.tags else [],
            "library_name": info.library_name,
            "last_modified": str(info.last_modified) if info.last_modified else None,
            "card_data": str(info.card_data) if info.card_data else None,
            "files": files,
        }

    except Exception as e:
        raise HTTPException(500, f"Failed to get model info: {str(e)}")


@router.post("/download")
def download_model(
    repo_id: str = Form(...),
    filename: Optional[str] = Form(None),
    revision: str = Form("main"),
    db: Session = Depends(get_db),
):
    """Download a model file from HuggingFace Hub and register it locally.

    If no filename is specified, auto-detects the first ONNX, PT, or safetensors file.
    """
    try:
        from huggingface_hub import hf_hub_download, list_repo_files
    except ImportError:
        raise HTTPException(500, "huggingface_hub not installed")

    token = _get_token()

    try:
        if not filename:
            files = list_repo_files(repo_id, revision=revision, token=token)
            # Priority: .onnx > .safetensors > .pt > .pth > .bin
            for ext in [".onnx", ".safetensors", ".pt", ".pth", ".bin"]:
                matches = [f for f in files if f.endswith(ext)]
                if matches:
                    filename = matches[0]
                    break
            if not filename:
                raise HTTPException(400, f"No model files found in {repo_id}. Files: {files[:20]}")

        local_path = hf_hub_download(
            repo_id=repo_id,
            filename=filename,
            revision=revision,
            token=token,
            cache_dir=os.path.join(os.path.dirname(MODEL_STORE), "hf_cache"),
        )

        safe_name = f"{repo_id.replace('/', '_')}_{os.path.basename(filename)}"
        dest_path = os.path.join(MODEL_STORE, safe_name)
        shutil.copy2(local_path, dest_path)

        file_size = os.path.getsize(dest_path)

        # Detect framework
        ext = os.path.splitext(filename)[1].lower()
        fw_map = {
            ".onnx": ("onnx", "onnx"),
            ".pt": ("pytorch", "pt"),
            ".pth": ("pytorch", "pth"),
            ".safetensors": ("pytorch", "safetensors"),
            ".bin": ("pytorch", "bin"),
            ".xml": ("openvino", "openvino_ir"),
            ".tflite": ("tflite", "tflite"),
        }
        framework, fmt = fw_map.get(ext, ("unknown", ext.lstrip(".")))

        # Get ONNX metadata if applicable
        metadata = None
        input_shape = None
        output_shape = None
        if fmt == "onnx":
            try:
                from services.conversion_service import get_onnx_model_info
                info = get_onnx_model_info(dest_path)
                metadata = info
                if info.get("inputs"):
                    input_shape = str(info["inputs"][0].get("shape", []))
                if info.get("outputs"):
                    output_shape = str(info["outputs"][0].get("shape", []))
            except Exception:
                pass

        record = ModelRecord(
            name=repo_id.split("/")[-1],
            framework=framework,
            format=fmt,
            file_path=dest_path,
            file_size=file_size,
            input_shape=input_shape,
            output_shape=output_shape,
            description=f"Downloaded from HuggingFace: {repo_id}/{filename}",
            metadata_json=metadata,
        )
        db.add(record)
        db.commit()
        db.refresh(record)

        return {
            "id": record.id,
            "name": record.name,
            "framework": record.framework,
            "format": record.format,
            "file_size": record.file_size,
            "source": f"huggingface:{repo_id}/{filename}",
            "message": f"Downloaded {filename} from {repo_id}",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Download failed: {str(e)}")
