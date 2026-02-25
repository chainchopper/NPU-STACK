"""Datasets router — upload, scan folder, and manage datasets."""

import os
import shutil
import zipfile
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db

router = APIRouter(prefix="/api/datasets", tags=["datasets"])

# Physical folder users can drop datasets into
DATASETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "datasets")
os.makedirs(DATASETS_DIR, exist_ok=True)

# Also support backend/data/datasets for training
TRAINING_DATASETS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "datasets")
os.makedirs(TRAINING_DATASETS_DIR, exist_ok=True)


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
                datasets.append({
                    "name": item,
                    "path": item_path,
                    "source": "local_folder",
                    "type": "archive" if ext in (".zip", ".tar", ".gz", ".tar.gz") else ext.lstrip("."),
                    "file_count": 1,
                    "total_size_bytes": sz,
                    "total_size_mb": round(sz / (1024 * 1024), 2),
                    "file_types": {ext: 1},
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
