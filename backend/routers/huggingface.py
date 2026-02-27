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


def _detect_quant(filename: str) -> Optional[str]:
    """Detect quantization level from filename."""
    name_lower = filename.lower()
    quants = [
        "q2_k", "q3_k_s", "q3_k_m", "q3_k_l",
        "q4_0", "q4_1", "q4_k_s", "q4_k_m",
        "q5_0", "q5_1", "q5_k_s", "q5_k_m",
        "q6_k", "q8_0", "f16", "f32",
        "iq1_s", "iq2_xxs", "iq2_xs", "iq3_xxs", "iq4_nl",
    ]
    for q in quants:
        if q in name_lower:
            return q.upper()
    return None


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
    tags: Optional[str] = None,
    sort: str = "downloads",
    limit: int = 20,
):
    """Search HuggingFace Hub for models.

    Tasks: image-classification, object-detection, text-generation,
           text2text-generation, image-to-text, text-to-image,
           feature-extraction, automatic-speech-recognition, etc.
    Tags: onnx, gguf, loRA, etc.
    """
    api = _get_api()

    try:
        kwargs = {"limit": limit}
        if q:
            kwargs["search"] = q
        
        # Merge task and tags into filter if needed, or use them separately
        huggingface_filter = []
        if task:
            huggingface_filter.append(task)
        if tags:
            huggingface_filter.extend([t.strip() for t in tags.split(",")])
        
        if huggingface_filter:
            kwargs["filter"] = huggingface_filter
            
        if sort:
            kwargs["sort"] = sort

        models = api.list_models(**kwargs)

        results = []
        for m in models:
            results.append({
                "id": m.id,
                "author": m.author,
                "task": getattr(m, 'pipeline_tag', None),
                "downloads": getattr(m, 'downloads', 0),
                "likes": getattr(m, 'likes', 0),
                "tags": m.tags[:10] if hasattr(m, 'tags') and m.tags else [],
                "last_modified": str(m.last_modified) if hasattr(m, 'last_modified') and m.last_modified else None,
                "private": getattr(m, 'private', False),
            })

        return {"query": q, "task": task, "tags": tags, "count": len(results), "models": results}

    except Exception as e:
        raise HTTPException(500, f"HuggingFace search failed: {str(e)}")


@router.get("/model/{repo_id:path}")
def get_model_details(repo_id: str):
    """Get detailed info about a HuggingFace model including its files and README."""
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
                    "is_model": ext in (".onnx", ".pt", ".pth", ".bin", ".safetensors", ".xml", ".tflite", ".pb", ".gguf"),
                })
        except Exception:
            pass

        # Try to get README content
        readme_content = ""
        try:
            from huggingface_hub import hf_hub_download
            readme_path = hf_hub_download(repo_id=repo_id, filename="README.md", token=_get_token())
            with open(readme_path, "r", encoding="utf-8") as f:
                readme_content = f.read(5000) # Limit to 5000 chars
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
            "card_data": info.card_data,
            "readme": readme_content,
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
            # Priority: .gguf > .onnx > .safetensors > .pt > .pth > .bin
            for ext in [".gguf", ".onnx", ".safetensors", ".pt", ".pth", ".bin"]:
                matches = [f for f in files if f.endswith(ext)]
                if matches:
                    filename = matches[0]
                    break
            if not filename:
                raise HTTPException(400, f"No model files found in {repo_id}. Files: {files[:20]}")

        # Download directly to MODEL_STORE
        # Note: local_dir_use_symlinks is deprecated in newer huggingface_hub versions
        try:
            local_path = hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                revision=revision,
                token=token,
                local_dir=MODEL_STORE,
            )
        except Exception as dl_err:
            raise HTTPException(500, f"Download failed for {repo_id}/{filename}: {str(dl_err)}")

        safe_name = f"{repo_id.replace('/', '_')}_{os.path.basename(filename)}"
        dest_path = os.path.join(MODEL_STORE, safe_name)
        
        # Rename to our safe name if it differs
        if os.path.abspath(local_path) != os.path.abspath(dest_path):
            if os.path.exists(dest_path):
                os.remove(dest_path)
            try:
                shutil.move(local_path, dest_path)
            except Exception:
                # If move fails (e.g. cross-device), copy instead
                shutil.copy2(local_path, dest_path)

        # Clean up any nested directories hf_hub_download may have created
        hf_nested = os.path.join(MODEL_STORE, repo_id.split('/')[0] if '/' in repo_id else '')
        if hf_nested and os.path.isdir(hf_nested) and hf_nested != MODEL_STORE:
            try:
                shutil.rmtree(hf_nested, ignore_errors=True)
            except Exception:
                pass

        file_size = os.path.getsize(dest_path)

        # Detect framework
        ext = os.path.splitext(filename)[1].lower()
        fw_map = {
            ".gguf": ("llama.cpp", "gguf"),
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
            size_mb=file_size / (1024 * 1024),
            quant_type=(_detect_quant(filename) if fmt == "gguf" else None),
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
@router.post("/snapshot")
def download_snapshot(
    repo_id: str = Form(...),
    revision: str = Form("main"),
    db: Session = Depends(get_db),
):
    """Download an entire repository snapshot from HuggingFace Hub."""
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        raise HTTPException(500, "huggingface_hub not installed")

    token = _get_token()
    
    # Create a safe directory name for the model repo
    repo_slug = repo_id.replace("/", "--")
    dest_dir = os.path.join(MODEL_STORE, repo_slug)
    os.makedirs(dest_dir, exist_ok=True)

    try:
        local_dir = snapshot_download(
            repo_id=repo_id,
            revision=revision,
            token=token,
            local_dir=dest_dir,
            local_dir_use_symlinks=False,
        )

        # Register as a folder-based model if it's large/complex
        # For simplicity, we'll record the entry point if we can find one, or just the directory
        record = ModelRecord(
            name=repo_id.split("/")[-1],
            framework="huggingface",
            format="directory",
            file_path=local_dir,
            file_size=0, # Computed if needed
            description=f"Full repository snapshot of {repo_id}",
        )
        db.add(record)
        db.commit()
        db.refresh(record)

        return {
            "id": record.id,
            "name": record.name,
            "path": local_dir,
            "message": f"Successfully downloaded snapshot of {repo_id}",
        }
    except Exception as e:
        raise HTTPException(500, f"Snapshot download failed: {str(e)}")
