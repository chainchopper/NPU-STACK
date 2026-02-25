"""File browser router — browse directories and drives for the frontend folder picker."""

import os
import string
import platform
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/browse", tags=["filebrowser"])

# Directories to hide from listing (Windows system folders)
HIDDEN_DIRS = {
    "$recycle.bin", "system volume information", "$winrepackage",
    "windows", "recovery", "config.msi", "msocache",
}


def _is_hidden(name: str) -> bool:
    """Check if a file/folder should be hidden from browsing."""
    return name.lower() in HIDDEN_DIRS or name.startswith("$") or name.startswith(".")


@router.get("/drives")
def list_drives():
    """List available drives (Windows) or mount points (Linux/macOS)."""
    drives = []
    if platform.system() == "Windows":
        for letter in string.ascii_uppercase:
            drive_path = f"{letter}:\\"
            if os.path.exists(drive_path):
                try:
                    total = os.statvfs(drive_path).f_frsize * os.statvfs(drive_path).f_blocks if hasattr(os, 'statvfs') else 0
                except Exception:
                    total = 0
                
                # Use ctypes on Windows for disk space
                try:
                    import ctypes
                    free_bytes = ctypes.c_ulonglong(0)
                    total_bytes = ctypes.c_ulonglong(0)
                    ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                        drive_path, None, ctypes.pointer(total_bytes), ctypes.pointer(free_bytes)
                    )
                    total = total_bytes.value
                    free = free_bytes.value
                except Exception:
                    total = 0
                    free = 0

                drives.append({
                    "path": drive_path,
                    "label": f"{letter}:",
                    "total_gb": round(total / (1024 ** 3), 1) if total else 0,
                    "free_gb": round(free / (1024 ** 3), 1) if free else 0,
                })
    else:
        # Linux/macOS — list common mount points
        for mount in ["/", "/home", "/mnt", "/media", "/opt"]:
            if os.path.isdir(mount):
                try:
                    st = os.statvfs(mount)
                    total = st.f_frsize * st.f_blocks
                    free = st.f_frsize * st.f_bavail
                except Exception:
                    total = free = 0
                drives.append({
                    "path": mount,
                    "label": mount,
                    "total_gb": round(total / (1024 ** 3), 1),
                    "free_gb": round(free / (1024 ** 3), 1),
                })

    return {"drives": drives}


@router.get("")
def browse_directory(
    path: str = Query("", description="Directory path to browse. Empty = list drives."),
):
    """Browse a directory, returning folders and model files."""
    if not path:
        return list_drives()

    # Normalize path
    path = os.path.normpath(path)

    if not os.path.exists(path):
        raise HTTPException(404, f"Path not found: {path}")
    if not os.path.isdir(path):
        raise HTTPException(400, f"Not a directory: {path}")

    # Model file extensions we care about
    MODEL_EXTS = {
        ".gguf", ".safetensors", ".ckpt", ".onnx", ".bin", ".pt", ".pth",
        ".tflite", ".xml", ".engine", ".mlmodel", ".mlpackage", ".pb",
    }

    folders = []
    files = []

    try:
        entries = os.listdir(path)
    except PermissionError:
        raise HTTPException(403, f"Permission denied: {path}")
    except OSError as e:
        raise HTTPException(500, f"Cannot read directory: {e}")

    for entry in sorted(entries, key=str.lower):
        if _is_hidden(entry):
            continue

        full_path = os.path.join(path, entry)

        try:
            if os.path.isdir(full_path):
                folders.append({
                    "name": entry,
                    "path": full_path.replace("\\", "/"),
                })
            elif os.path.isfile(full_path):
                ext = os.path.splitext(entry)[1].lower()
                if ext in MODEL_EXTS:
                    try:
                        size = os.path.getsize(full_path)
                    except OSError:
                        size = 0
                    files.append({
                        "name": entry,
                        "path": full_path.replace("\\", "/"),
                        "extension": ext,
                        "size": size,
                        "size_human": _format_size(size),
                    })
        except (PermissionError, OSError):
            continue

    parent = os.path.dirname(path)
    if parent == path:
        parent = None  # We're at a root
    else:
        parent = parent.replace("\\", "/")

    return {
        "current": path.replace("\\", "/"),
        "parent": parent,
        "folders": folders,
        "files": files,
        "total_folders": len(folders),
        "total_files": len(files),
    }


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 ** 3:
        return f"{size_bytes / (1024 ** 2):.1f} MB"
    else:
        return f"{size_bytes / (1024 ** 3):.2f} GB"
