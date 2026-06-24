"""Datasets router — upload, scan folder, HF search, and manage datasets."""

import os
import shutil
import zipfile
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from database import get_db

router = APIRouter(prefix="/api/datasets", tags=["datasets"])

# Physical folder for datasets — defaults to repo root datasets/
DATASETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "datasets")
os.makedirs(DATASETS_DIR, exist_ok=True)

# Also support backend/data/datasets for training cache
TRAINING_DATASETS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "datasets")
os.makedirs(TRAINING_DATASETS_DIR, exist_ok=True)

# ── Built-in sample datasets catalog ──────────────────────────────────
SAMPLE_DATASETS = [
    {"id": "magneto-sft", "name": "Magneto SFT v1", "type": "jsonl", "size": "186 KB", "entries": 250,
     "description": "Magneto system-training conversations — dual-turn Human/Assistant format",
     "path": "datasets/train.jsonl", "source": "local",
     "icon": "🧲", "tags": ["sft", "conversation", "magneto"]},
    {"id": "alpaca-cleaned", "name": "Alpaca Cleaned", "type": "jsonl", "size": "~50 MB", "entries": 51760,
     "description": "Cleaned Alpaca instruction-following dataset (unsloth/alpaca-cleaned)",
     "path": "", "source": "huggingface", "hf_repo": "unsloth/alpaca-cleaned",
     "icon": "🦙", "tags": ["instruction", "alpaca", "general"]},
    {"id": "ultrachat-200k", "name": "UltraChat 200k", "type": "jsonl", "size": "~200 MB", "entries": 200000,
     "description": "High-quality multi-turn chat conversations (HuggingFaceH4/ultrachat_200k)",
     "path": "", "source": "huggingface", "hf_repo": "HuggingFaceH4/ultrachat_200k",
     "icon": "💬", "tags": ["chat", "multi-turn", "general"]},
    {"id": "open-orca", "name": "OpenOrca", "type": "parquet", "size": "~1 GB", "entries": 1000000,
     "description": "OpenOrca instruction dataset — GPT-4 augmented FLAN (Open-Orca/OpenOrca)",
     "path": "", "source": "huggingface", "hf_repo": "Open-Orca/OpenOrca",
     "icon": "🐋", "tags": ["instruction", "orca", "general"]},
    {"id": "coding-instruct", "name": "Code Instructions", "type": "jsonl", "size": "~30 MB", "entries": 12000,
     "description": "Code generation and debugging instructions (iamtarun/python_code_instructions_18k_alpaca)",
     "path": "", "source": "huggingface", "hf_repo": "iamtarun/python_code_instructions_18k_alpaca",
     "icon": "💻", "tags": ["code", "instruction", "python"]},
    {"id": "math-reasoning", "name": "Math Reasoning", "type": "jsonl", "size": "~15 MB", "entries": 9000,
     "description": "Step-by-step math reasoning (unsloth/OpenMathReasoning-mini)",
     "path": "", "source": "huggingface", "hf_repo": "unsloth/OpenMathReasoning-mini",
     "icon": "🔢", "tags": ["math", "reasoning", "cot"]},
]


def _get_folder_info(path: str) -> dict:
    """Get info about a folder — file count, total size, file types."""
    total_size = 0
    file_count = 0
    extensions = {}

    for root, dirs, files in os.walk(path):
        for f in files:
            fp = os.path.join(root, f)
            try:
                sz = os.path.getsize(fp)
                total_size += sz
                file_count += 1
                ext = os.path.splitext(f)[1].lower() or ".none"
                extensions[ext] = extensions.get(ext, 0) + 1
            except OSError:
                pass

    return {
        "file_count": file_count,
        "total_size_bytes": total_size,
        "total_size_mb": round(total_size / (1024 * 1024), 2),
        "file_types": extensions,
    }


def _detect_dataset_type(path: str, extensions: dict) -> str:
    """Guess the dataset type based on file extensions."""
    img_exts = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tiff"}
    text_exts = {".txt", ".csv", ".tsv", ".json", ".jsonl", ".parquet"}

    img_count = sum(extensions.get(e, 0) for e in img_exts)
    text_count = sum(extensions.get(e, 0) for e in text_exts)

    if img_count > text_count:
        return "image"
    elif ".csv" in extensions or ".tsv" in extensions:
        return "tabular"
    elif ".json" in extensions or ".jsonl" in extensions:
        return "json"
    elif ".txt" in extensions:
        return "text"
    elif ".parquet" in extensions:
        return "parquet"
    return "mixed"


@router.get("")
def list_datasets():
    """List all datasets by scanning the datasets folder and data/datasets folder."""
    datasets = []

    # Scan root datasets/ folder
    if os.path.exists(DATASETS_DIR):
        for item in os.listdir(DATASETS_DIR):
            item_path = os.path.join(DATASETS_DIR, item)
            if os.path.isdir(item_path):
                info = _get_folder_info(item_path)
                dtype = _detect_dataset_type(item_path, info["file_types"])
                datasets.append({
                    "name": item,
                    "path": item_path,
                    "source": "local_folder",
                    "type": dtype,
                    **info,
                    "modified": datetime.fromtimestamp(os.path.getmtime(item_path)).isoformat(),
                })
            elif os.path.isfile(item_path):
                ext = os.path.splitext(item)[1].lower()
                sz = os.path.getsize(item_path)
                # Count lines for JSONL/text files
                line_count = 0
                if ext in (".jsonl", ".json", ".csv", ".txt", ".tsv"):
                    try:
                        with open(item_path, "r", encoding="utf-8") as lf:
                            line_count = sum(1 for _ in lf)
                    except: pass
                datasets.append({
                    "name": item,
                    "path": item_path,
                    "source": "local_folder",
                    "type": "archive" if ext in (".zip", ".tar", ".gz", ".tar.gz") else ext.lstrip("."),
                    "file_count": 1,
                    "total_size_bytes": sz,
                    "total_size_mb": round(sz / (1024 * 1024), 2),
                    "file_types": {ext: 1},
                    "entries": line_count,
                    "modified": datetime.fromtimestamp(os.path.getmtime(item_path)).isoformat(),
                })

    # Scan backend/data/datasets for cached training datasets
    if os.path.exists(TRAINING_DATASETS_DIR):
        for item in os.listdir(TRAINING_DATASETS_DIR):
            item_path = os.path.join(TRAINING_DATASETS_DIR, item)
            if os.path.isdir(item_path):
                info = _get_folder_info(item_path)
                dtype = _detect_dataset_type(item_path, info["file_types"])
                datasets.append({
                    "name": f"{item} (cached)",
                    "path": item_path,
                    "source": "training_cache",
                    "type": dtype,
                    **info,
                    "modified": datetime.fromtimestamp(os.path.getmtime(item_path)).isoformat(),
                })

    return {
        "datasets_folder": DATASETS_DIR,
        "count": len(datasets),
        "datasets": datasets,
    }


@router.post("/upload")
async def upload_dataset(
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
):
    """Upload a dataset file (zip, csv, images, etc.) to the datasets folder.

    Zip files are automatically extracted into a named subfolder.
    """
    if not file.filename:
        raise HTTPException(400, "No filename provided")

    dataset_name = name or os.path.splitext(file.filename)[0]
    safe_name = dataset_name.replace(" ", "_").replace("/", "_")
    ext = os.path.splitext(file.filename)[1].lower()

    try:
        if ext == ".zip":
            # Extract zip into named folder
            dest_dir = os.path.join(DATASETS_DIR, safe_name)
            os.makedirs(dest_dir, exist_ok=True)

            # Save zip temporarily
            zip_path = os.path.join(DATASETS_DIR, f"_temp_{file.filename}")
            with open(zip_path, "wb") as f:
                shutil.copyfileobj(file.file, f)

            # Extract
            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(dest_dir)

            os.remove(zip_path)

            info = _get_folder_info(dest_dir)
            return {
                "name": safe_name,
                "type": "extracted_zip",
                "path": dest_dir,
                **info,
                "message": f"Extracted {file.filename} to datasets/{safe_name}/",
            }
        else:
            # Save single file directly
            dest_path = os.path.join(DATASETS_DIR, file.filename.replace(" ", "_"))
            with open(dest_path, "wb") as f:
                shutil.copyfileobj(file.file, f)

            sz = os.path.getsize(dest_path)
            return {
                "name": file.filename,
                "type": ext.lstrip("."),
                "path": dest_path,
                "file_count": 1,
                "total_size_mb": round(sz / (1024 * 1024), 2),
                "message": f"Uploaded {file.filename} to datasets/",
            }

    except Exception as e:
        raise HTTPException(500, f"Upload failed: {str(e)}")


@router.post("/scan")
def scan_folder():
    """Re-scan the datasets folder and return updated listing."""
    return list_datasets()


@router.get("/catalog")
def get_sample_catalog():
    """Return curated sample dataset catalog with local availability info."""
    enriched = []
    for ds in SAMPLE_DATASETS:
        d = dict(ds)
        if ds.get("path"):
            full_path = os.path.join(DATASETS_DIR, ds["path"].replace("datasets/", ""))
            d["available_local"] = os.path.exists(full_path)
            d["local_path"] = full_path if d["available_local"] else None
        else:
            d["available_local"] = False
        enriched.append(d)
    return {"catalog": enriched, "datasets_folder": DATASETS_DIR}


@router.get("/search/huggingface")
def search_huggingface(q: str = "", limit: int = 10):
    """Search HuggingFace datasets by keyword."""
    if not q.strip():
        return {"results": []}
    try:
        from huggingface_hub import list_datasets as hf_list
        results = []
        for ds in hf_list(search=q, limit=limit):
            results.append({
                "id": ds.id,
                "author": ds.author,
                "downloads": getattr(ds, "downloads", 0),
                "likes": getattr(ds, "likes", 0),
                "tags": getattr(ds, "tags", []),
                "last_modified": str(getattr(ds, "last_modified", "")) if getattr(ds, "last_modified", None) else "",
            })
        return {"results": results, "query": q}
    except Exception as e:
        return {"results": [], "error": str(e)}


@router.post("/huggingface/download")
async def download_hf_dataset(repo_id: str = Form(...)):
    """Download a HuggingFace dataset to the local datasets folder."""
    try:
        from datasets import load_dataset as hf_load, get_dataset_config_names
        safe_name = repo_id.replace("/", "--")
        dest = os.path.join(DATASETS_DIR, safe_name)
        os.makedirs(dest, exist_ok=True)

        # Try loading with streaming, save first 1K rows as sample
        ds = hf_load(repo_id, split="train", streaming=True, trust_remote_code=True)
        rows = []
        for i, row in enumerate(ds):
            rows.append(row)
            if i >= 5000:
                break
        if not rows:
            raise ValueError("No rows returned from dataset")

        out_path = os.path.join(dest, "data.jsonl")
        import json
        with open(out_path, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, default=str) + "\n")

        sz = os.path.getsize(out_path)
        return {
            "name": safe_name, "type": "jsonl", "path": out_path,
            "file_count": 1, "total_size_mb": round(sz / (1024 * 1024), 2),
            "entries": len(rows),
            "message": f"Downloaded {len(rows)} rows from {repo_id} to datasets/{safe_name}/"
        }
    except Exception as e:
        raise HTTPException(500, f"HF download failed: {str(e)}")


@router.delete("/{dataset_name}")
def delete_dataset(dataset_name: str):
    """Delete a dataset by name from the datasets folder."""
    # Check in root datasets/ folder
    target = os.path.join(DATASETS_DIR, dataset_name)

    if os.path.isdir(target):
        shutil.rmtree(target)
        return {"message": f"Deleted dataset folder: {dataset_name}"}
    elif os.path.isfile(target):
        os.remove(target)
        return {"message": f"Deleted dataset file: {dataset_name}"}
    else:
        raise HTTPException(404, f"Dataset '{dataset_name}' not found in {DATASETS_DIR}")


@router.get("/info")
def datasets_info():
    """Get info about dataset storage locations."""
    return {
        "datasets_folder": DATASETS_DIR,
        "training_cache_folder": TRAINING_DATASETS_DIR,
        "datasets_folder_exists": os.path.exists(DATASETS_DIR),
        "hint": "Place dataset folders or files in the 'datasets/' folder at the project root.",
    }

