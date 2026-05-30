"""Edge Device Fleet — API router for discovery, management, and firmware ops.

Endpoints:
  GET   /api/devices/scan          — Run discovery (USB + mDNS + optional BLE/subnet)
  GET   /api/devices               — List all registered devices
  GET   /api/devices/backups       — List firmware backups on disk

  POST  /api/devices/esp/detect    — Detect ESP chip on a serial port
  POST  /api/devices/esp/backup    — Backup ESP firmware to disk
  POST  /api/devices/esp/flash     — Flash firmware to ESP device

  GET   /api/devices/rp2040/detect — Detect RP2040 in BOOTSEL mode
  POST  /api/devices/rp2040/flash  — Flash UF2 to RP2040

  GET   /api/devices/{device_id}   — Get single device detail  (MUST be last)
  PUT   /api/devices/{device_id}   — Update device metadata
  DELETE /api/devices/{device_id}  — Remove device from registry
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
import os

from services.edge_discovery import (
    run_full_discovery,
    load_registry,
    save_registry,
    get_device_from_registry,
    list_registry_devices,
    list_firmware_profiles,
    list_prepared_bundles,
    get_prepared_bundle,
    prepare_firmware_bundle,
    install_prepared_bundle,
    detect_chip_for_device,
    esp_detect_chip,
    esp_backup_firmware,
    esp_flash_firmware,
    rp2040_detect,
    rp2040_flash_uf2,
    FIRMWARE_DIR,
)

router = APIRouter(prefix="/api/devices", tags=["edge-fleet"])


# ── Models ────────────────────────────────────────────────────────

class DeviceUpdate(BaseModel):
    nickname: Optional[str] = None
    notes: Optional[str] = None
    firmware_version: Optional[str] = None
    agent_installed: Optional[bool] = None


class ESPDetectRequest(BaseModel):
    port: str  # e.g., "COM3" or "/dev/ttyUSB0"


class ESPBackupRequest(BaseModel):
    port: str
    flash_size_mb: int = 4
    name: str = ""


class ESPFlashRequest(BaseModel):
    port: str
    firmware_path: str
    flash_offset: str = "0x0"


class RP2040FlashRequest(BaseModel):
    drive: str  # e.g., "E:\\"
    uf2_path: str


class PrepareFirmwareRequest(BaseModel):
    profile_id: Optional[str] = None
    device_name: Optional[str] = None
    wifi_ssid: Optional[str] = None
    wifi_password: Optional[str] = None
    mqtt_broker: Optional[str] = None
    command_center_url: Optional[str] = None
    agent_port: Optional[int] = 9200
    shared_secret: Optional[str] = None


class InstallPreparedRequest(BaseModel):
    bundle_id: Optional[str] = None


# ── Discovery ─────────────────────────────────────────────────────

@router.get("/scan")
async def scan_devices(
    usb: bool = Query(True, description="Scan USB serial ports"),
    mdns: bool = Query(True, description="Scan mDNS services on WiFi"),
    ble: bool = Query(False, description="Scan Bluetooth Low Energy (slower)"),
    subnet: bool = Query(False, description="Ping sweep local subnet (slow)"),
    known_only: bool = Query(False, description="When subnet scan is enabled, probe only known edge hosts instead of the full subnet"),
    known_hosts: Optional[str] = Query(None, description="Optional comma-separated known IPs/hosts for targeted edge probing"),
    mdns_timeout: float = Query(5.0, description="mDNS scan duration in seconds"),
    ble_timeout: float = Query(10.0, description="BLE scan duration in seconds"),
):
    """
    Run device discovery across all enabled methods.
    Returns the full device registry after merging new discoveries.
    """
    result = await run_full_discovery(
        usb=usb,
        mdns=mdns,
        ble=ble,
        subnet=subnet,
        known_only=known_only,
        known_hosts=known_hosts,
        mdns_timeout=mdns_timeout,
        ble_timeout=ble_timeout,
    )
    return result


@router.get("")
def list_devices(
    include_low_confidence: bool = Query(False, description="Include low-confidence generic subnet hits"),
):
    """List all devices in the registry."""
    return list_registry_devices(include_low_confidence=include_low_confidence)


@router.get("/profiles")
def list_profiles(device_id: Optional[str] = Query(None, description="Optional device to filter compatible profiles")):
    """List supported firmware preparation profiles."""
    device = get_device_from_registry(device_id) if device_id else None
    return {
        "profiles": list_firmware_profiles(device),
        "count": len(list_firmware_profiles(device)),
        "device_id": device_id,
    }


@router.get("/prepared")
def list_prepared(device_id: Optional[str] = Query(None, description="Optional device to filter prepared bundles")):
    """List prepared firmware bundles staged by NPU-STACK."""
    bundles = list_prepared_bundles(device_id=device_id)
    return {"bundles": bundles, "count": len(bundles)}


@router.get("/prepared/{bundle_id}/download")
def download_prepared(bundle_id: str):
    """Download a prepared firmware bundle archive."""
    bundle = get_prepared_bundle(bundle_id)
    if not bundle:
        raise HTTPException(404, f"Prepared bundle '{bundle_id}' not found")

    archive_path = bundle.get("archive_path")
    if not archive_path or not os.path.exists(archive_path):
        raise HTTPException(404, f"Prepared bundle archive missing for '{bundle_id}'")

    return FileResponse(archive_path, filename=os.path.basename(archive_path), media_type="application/zip")


# ── Firmware Backups (BEFORE /{device_id} to avoid path conflict) ─

@router.get("/backups")
def list_backups():
    """List all firmware backups stored on disk."""
    backups = []
    if FIRMWARE_DIR.exists():
        for f in FIRMWARE_DIR.iterdir():
            if f.is_file():
                backups.append({
                    "filename": f.name,
                    "path": str(f),
                    "size_bytes": f.stat().st_size,
                    "size_mb": round(f.stat().st_size / (1024 * 1024), 2),
                    "created_at": f.stat().st_mtime,
                })
    backups.sort(key=lambda x: x["created_at"], reverse=True)
    return {"backups": backups, "count": len(backups), "directory": str(FIRMWARE_DIR)}


# ── ESP32 Operations (BEFORE /{device_id}) ────────────────────────

@router.post("/esp/detect")
def detect_esp(req: ESPDetectRequest):
    """
    Detect ESP chip details on a serial port.
    The device must be in bootloader mode (hold BOOT button).
    """
    return esp_detect_chip(req.port)


@router.post("/{device_id}/detect-chip")
def detect_device_chip(device_id: str):
    """Probe a registered USB/serial device and persist richer chip identity in the registry."""
    result = detect_chip_for_device(device_id)
    if result.get("status") == "failed":
        raise HTTPException(400, result.get("error", "Chip detect failed"))
    return result


@router.post("/esp/backup")
def backup_esp_firmware(req: ESPBackupRequest):
    """
    Read the full flash from an ESP device and save to disk.
    Device must be in bootloader mode. This can take 30-60s for 4MB.
    """
    return esp_backup_firmware(
        port=req.port,
        flash_size_mb=req.flash_size_mb,
        output_name=req.name,
    )


@router.post("/esp/flash")
def flash_esp_firmware(req: ESPFlashRequest):
    """
    Flash a firmware binary to an ESP device.
    Device must be in bootloader mode.
    """
    return esp_flash_firmware(
        port=req.port,
        firmware_path=req.firmware_path,
        flash_offset=req.flash_offset,
    )


# ── RP2040 Operations (BEFORE /{device_id}) ──────────────────────

@router.get("/rp2040/detect")
def detect_rp2040():
    """Detect RP2040 devices in BOOTSEL (USB mass storage) mode."""
    devices = rp2040_detect()
    return {"devices": devices, "count": len(devices)}


@router.post("/rp2040/flash")
def flash_rp2040(req: RP2040FlashRequest):
    """Flash a UF2 file to an RP2040 in BOOTSEL mode."""
    return rp2040_flash_uf2(req.drive, req.uf2_path)


@router.post("/{device_id}/pair")
def pair_device(device_id: str):
    """Mark a discovered device as paired/managed in the local registry."""
    registry = load_registry()
    devices = registry.get("devices", {})
    if device_id not in devices:
        raise HTTPException(404, f"Device '{device_id}' not found")

    devices[device_id]["paired"] = True
    devices[device_id]["management_state"] = "paired"
    save_registry(registry)
    return get_device_from_registry(device_id)


@router.post("/{device_id}/unpair")
def unpair_device(device_id: str):
    """Clear paired state for a managed device."""
    registry = load_registry()
    devices = registry.get("devices", {})
    if device_id not in devices:
        raise HTTPException(404, f"Device '{device_id}' not found")

    devices[device_id]["paired"] = False
    devices[device_id]["management_state"] = "detected"
    save_registry(registry)
    return get_device_from_registry(device_id)


@router.post("/{device_id}/prepare")
def prepare_device(device_id: str, req: PrepareFirmwareRequest):
    """Prepare a board-specific firmware bundle using repo-native firmware assets."""
    result = prepare_firmware_bundle(device_id=device_id, profile_id=req.profile_id, config=req.model_dump(exclude_none=True))
    if result.get("error"):
        raise HTTPException(400, result["error"])
    return result


@router.post("/{device_id}/install")
def install_device_bundle(device_id: str, req: InstallPreparedRequest):
    """Install a prepared bundle directly when the device supports live install."""
    result = install_prepared_bundle(device_id=device_id, bundle_id=req.bundle_id)
    if result.get("status") == "failed":
        raise HTTPException(400, result.get("error", "Install failed"))
    return result


# ── Individual device CRUD (MUST BE LAST — /{device_id} is greedy) ─

@router.get("/{device_id}")
def get_device(device_id: str):
    """Get a single device by ID."""
    device = get_device_from_registry(device_id)
    if not device:
        raise HTTPException(404, f"Device '{device_id}' not found")
    return device


@router.put("/{device_id}")
def update_device(device_id: str, update: DeviceUpdate):
    """Update device metadata (nickname, notes, etc.)."""
    registry = load_registry()
    devices = registry.get("devices", {})
    if device_id not in devices:
        raise HTTPException(404, f"Device '{device_id}' not found")

    for field, value in update.model_dump(exclude_none=True).items():
        devices[device_id][field] = value

    save_registry(registry)
    return devices[device_id]


@router.delete("/{device_id}")
def remove_device(device_id: str):
    """Remove a device from the registry."""
    registry = load_registry()
    devices = registry.get("devices", {})
    if device_id not in devices:
        raise HTTPException(404, f"Device '{device_id}' not found")

    removed = devices.pop(device_id)
    save_registry(registry)
    return {"removed": removed}
