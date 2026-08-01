"""Fleet OTA — Firmware upload and distribution endpoint.

POST /api/fleet/ota/upload — upload compiled .bin firmware
GET  /api/fleet/ota/{device_type}-latest.bin — serve latest binary for device
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

router = APIRouter(prefix="/api/fleet/ota", tags=["fleet-ota"])

# ── Storage ──
OTA_DIR = Path(__file__).resolve().parent.parent / "data" / "fleet-ota"
OTA_DIR.mkdir(parents=True, exist_ok=True)


def _save_manifest(device_type: str, info: dict):
    """Save device firmware manifest JSON."""
    mf = OTA_DIR / f"{device_type}-manifest.json"
    mf.write_text(json.dumps(info, indent=2))


def _load_manifest(device_type: str) -> dict:
    """Load device firmware manifest."""
    mf = OTA_DIR / f"{device_type}-manifest.json"
    if not mf.exists():
        return {}
    return json.loads(mf.read_text())


@router.post("/upload")
async def ota_upload(
    device_type: str = "npu-amb82",
    version: str = "",
    firmware: UploadFile = File(...),
):
    """Upload a firmware binary for OTA distribution."""
    if not firmware.filename or not firmware.filename.endswith(".bin"):
        raise HTTPException(400, "Firmware must be a .bin file")

    # Determine version from filename or param
    fname = firmware.filename
    if not version:
        version = fname.replace(".ino.bin", "").replace(".bin", "")
        version = version or f"auto-{int(time.time())}"

    # Read and hash binary
    data = await firmware.read()
    sha = hashlib.sha256(data).hexdigest()[:12]
    size_kb = len(data) / 1024.0

    # Save as latest + versioned
    latest_path = OTA_DIR / f"{device_type}-latest.bin"
    versioned_path = OTA_DIR / f"{device_type}-{version}.bin"
    latest_path.write_bytes(data)
    versioned_path.write_bytes(data)

    # Update manifest
    manifest = {
        "device_type": device_type,
        "version": version,
        "sha256_short": sha,
        "size_kb": round(size_kb, 1),
        "timestamp": int(time.time()),
        "filename": fname,
    }
    _save_manifest(device_type, manifest)

    return {
        "status": "ok",
        "device_type": device_type,
        "version": version,
        "sha256": sha,
        "size_kb": manifest["size_kb"],
        "url": f"/api/fleet/ota/{device_type}-latest.bin",
    }


@router.get("/{device_type}-latest.bin")
async def ota_download(device_type: str):
    """Serve the latest firmware binary for a device."""
    path = OTA_DIR / f"{device_type}-latest.bin"
    if not path.exists():
        raise HTTPException(404, f"No firmware available for {device_type}. Upload via POST /api/fleet/ota/upload")
    return FileResponse(path, media_type="application/octet-stream",
                        filename=f"{device_type}-latest.bin")


@router.get("/manifest/{device_type}")
async def ota_manifest(device_type: str):
    """Get the current firmware manifest for a device type."""
    m = _load_manifest(device_type)
    if not m:
        return {"device_type": device_type, "available": False}
    return {"device_type": device_type, "available": True, **m}


@router.get("/list")
async def ota_list():
    """List all available firmware binaries."""
    files = []
    for f in sorted(OTA_DIR.glob("*-latest.bin")):
        dt = f.stem.replace("-latest", "")
        m = _load_manifest(dt)
        files.append({"device_type": dt, "version": m.get("version", "?"),
                      "size_kb": m.get("size_kb", 0)})
    return {"firmware": files, "count": len(files)}
