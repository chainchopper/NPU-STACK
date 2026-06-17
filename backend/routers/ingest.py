"""Data Ingestion router — upload files, extract data, build training datasets."""

import os
import shutil
import uuid
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query
from fastapi.responses import JSONResponse

from services.data_extractor import extract_file, extract_folder, get_supported_types, SUPPORTED_EXTENSIONS
from services.dataset_builder import build_dataset, get_available_formats

router = APIRouter(prefix="/api/ingest", tags=["ingestion"])


def _detect_docling() -> dict:
    """Check if Docling (IBM document AI toolkit) is available."""
    try:
        import docling  # noqa: F401
        return {"available": True, "message": "Docling is installed — high-quality PDF/DOCX/PPTX/image parsing available."}
    except ImportError:
        return {
            "available": False,
            "message": "Docling not installed. Run: pip install docling",
            "install_hint": "pip install docling",
            "description": "Docling (IBM) provides high-quality PDF, DOCX, PPTX, and image parsing with table extraction, OCR, and structured Markdown/JSON output.",
        }

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
DATASET_DIR = os.path.join(DATA_DIR, "datasets")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(DATASET_DIR, exist_ok=True)


@router.get("/supported-types")
def list_supported_types():
    """List supported file types for data extraction."""
    return {
        "types": get_supported_types(),
        "all_extensions": sorted(SUPPORTED_EXTENSIONS),
        "total": len(SUPPORTED_EXTENSIONS),
        "tools": {
            "docling": _detect_docling(),
        },
    }


@router.get("/dataset-formats")
def list_dataset_formats():
    """List available dataset output formats."""
    return {
        "formats": get_available_formats(),
        "tools": {
            "docling": _detect_docling(),
        },
    }


@router.post("/upload")
async def upload_and_extract(
    files: list[UploadFile] = File(...),
    ocr: bool = Form(False),
):
    """Upload one or more files, extract content from each."""
    results = []
    for file in files:
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in SUPPORTED_EXTENSIONS:
            results.append({
                "success": False,
                "file_name": file.filename,
                "error": f"Unsupported file type: {ext}",
            })
            continue

        # Save to upload dir
        safe_name = f"{uuid.uuid4().hex[:8]}_{file.filename}"
        save_path = os.path.join(UPLOAD_DIR, safe_name)
        with open(save_path, "wb") as f:
            content = await file.read()
            f.write(content)

        # Extract
        result = extract_file(save_path, ocr=ocr)
        result["uploaded_path"] = save_path
        results.append(result)

    success_count = sum(1 for r in results if r.get("success"))
    return {
        "files": results,
        "total": len(results),
        "success_count": success_count,
        "error_count": len(results) - success_count,
    }


@router.post("/extract-folder")
def extract_from_folder(
    path: str = Form(...),
    recursive: bool = Form(True),
    ocr: bool = Form(False),
):
    """Extract data from all supported files in a folder."""
    if not os.path.isdir(path):
        raise HTTPException(404, f"Directory not found: {path}")

    result = extract_folder(path, recursive=recursive, ocr=ocr)
    return result


@router.post("/extract-file")
def extract_single_file(
    path: str = Form(...),
    ocr: bool = Form(False),
):
    """Extract data from a single file by path."""
    if not os.path.isfile(path):
        raise HTTPException(404, f"File not found: {path}")

    result = extract_file(path, ocr=ocr)
    return result


@router.post("/preview")
async def preview_extraction(
    file: UploadFile = File(...),
    ocr: bool = Form(False),
    max_chars: int = Form(2000),
):
    """Upload a file and preview extracted content (truncated)."""
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type: {ext}")

    safe_name = f"preview_{uuid.uuid4().hex[:8]}_{file.filename}"
    save_path = os.path.join(UPLOAD_DIR, safe_name)
    with open(save_path, "wb") as f:
        content = await file.read()
        f.write(content)

    result = extract_file(save_path, ocr=ocr)

    # Truncate for preview
    if result.get("text"):
        result["text_preview"] = result["text"][:max_chars]
        result["text_truncated"] = len(result["text"]) > max_chars
        result["text_full_length"] = len(result["text"])
    if "data" in result and isinstance(result["data"], list):
        result["data"] = result["data"][:10]  # Limit preview records

    # Clean up preview file
    try:
        os.remove(save_path)
    except OSError:
        pass

    return result


@router.post("/build-dataset")
def build_training_dataset(
    source_folder: Optional[str] = Form(None),
    uploaded_files: Optional[str] = Form(None),  # JSON list of file paths
    output_format: str = Form("raw_text"),
    dataset_name: str = Form("my_dataset"),
    chunk_size: int = Form(512),
    chunk_overlap: int = Form(64),
    deduplicate: bool = Form(True),
    min_length: int = Form(10),
    output_type: str = Form("jsonl"),
    ocr: bool = Form(False),
):
    """Build a training dataset from a folder or list of uploaded files."""
    extractions = []

    # Extract from folder
    if source_folder:
        if not os.path.isdir(source_folder):
            raise HTTPException(404, f"Directory not found: {source_folder}")
        folder_result = extract_folder(source_folder, recursive=True, ocr=ocr)
        extractions.extend(folder_result.get("files", []))

    # Extract from specific file paths
    if uploaded_files:
        try:
            file_paths = eval(uploaded_files) if isinstance(uploaded_files, str) else uploaded_files
        except Exception:
            file_paths = []

        for fpath in file_paths:
            if os.path.isfile(fpath):
                extractions.append(extract_file(fpath, ocr=ocr))

    # Also process any files already in the uploads dir if nothing else provided
    if not extractions:
        upload_result = extract_folder(UPLOAD_DIR, recursive=False, ocr=ocr)
        extractions.extend(upload_result.get("files", []))

    if not extractions:
        raise HTTPException(400, "No files to process. Upload files or specify a source folder.")

    result = build_dataset(
        extractions=extractions,
        output_format=output_format,
        output_dir=DATASET_DIR,
        dataset_name=dataset_name,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        deduplicate=deduplicate,
        min_length=min_length,
        output_type=output_type,
    )

    return result


@router.get("/uploads")
def list_uploads():
    """List files in the upload staging area."""
    files = []
    if os.path.isdir(UPLOAD_DIR):
        for fname in os.listdir(UPLOAD_DIR):
            fpath = os.path.join(UPLOAD_DIR, fname)
            if os.path.isfile(fpath):
                files.append({
                    "name": fname,
                    "path": fpath,
                    "size": os.path.getsize(fpath),
                    "extension": os.path.splitext(fname)[1].lower(),
                })
    return {"files": files, "total": len(files), "upload_dir": UPLOAD_DIR}


@router.delete("/uploads/clear")
def clear_uploads():
    """Clear all files from the upload staging area."""
    count = 0
    if os.path.isdir(UPLOAD_DIR):
        for fname in os.listdir(UPLOAD_DIR):
            fpath = os.path.join(UPLOAD_DIR, fname)
            if os.path.isfile(fpath):
                os.remove(fpath)
                count += 1
    return {"cleared": count, "message": f"Cleared {count} files from upload staging"}
