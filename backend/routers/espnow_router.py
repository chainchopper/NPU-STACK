"""ESP-NOW REST router — browse, build, and flash ESP-NOW firmware.

Provides /api/espnow endpoints for Nirvana's fleet operations.
The ESP-NOW library is baked at libraries/esp-now-lib/.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from services.espnow_service import (
    espnow_available,
    list_modules,
    list_examples,
    get_example_detail,
    build_command,
    get_firmware_binaries,
    idf_available,
)

router = APIRouter(prefix="/api/espnow", tags=["espnow"])


@router.get("/status")
def espnow_status():
    """Check ESP-NOW library availability and toolchain status."""
    return {
        "library_available": espnow_available(),
        "idf_available": idf_available(),
        "library_path": "libraries/esp-now-lib/",
    }


@router.get("/modules")
def get_modules():
    """List all ESP-NOW source modules (control, OTA, security, etc.)."""
    if not espnow_available():
        raise HTTPException(404, "ESP-NOW library not found in libraries/esp-now-lib/")
    return list_modules()


@router.get("/examples")
def get_examples():
    """List all ESP-NOW example projects."""
    if not espnow_available():
        raise HTTPException(404, "ESP-NOW library not found")
    return list_examples()


@router.get("/examples/{name}")
def get_example(name: str):
    """Get details for a specific ESP-NOW example."""
    detail = get_example_detail(name)
    if detail is None:
        raise HTTPException(404, f"Example not found: {name}")
    return detail


@router.get("/examples/{name}/build")
def get_build_info(name: str, target: str = "esp32", port: str = ""):
    """Get build commands for an ESP-NOW example."""
    result = build_command(name, target=target, port=port)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


@router.get("/examples/{name}/binaries")
def get_binaries(name: str):
    """List built firmware binaries for an example."""
    return get_firmware_binaries(name)
