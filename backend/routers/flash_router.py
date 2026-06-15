"""POST /api/devices/{id}/flash — read, write, or detect flash via USB tools."""

import logging
from fastapi import APIRouter
from pydantic import BaseModel
from backend.services import flash_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/devices", tags=["devices-flash"])


class FlashReadRequest(BaseModel):
    offset_sectors: int = 0
    sector_count: int = 1


class FlashWriteRequest(BaseModel):
    offset_sectors: int = 0
    input_file: str  # path to firmware image


@router.get("/{device_id}/flash/tools")
async def get_flash_tools(device_id: str):
    """Check which flash tools are available."""
    return flash_service.flash_tools_available()


@router.post("/{device_id}/flash/detect")
async def flash_detect(device_id: str):
    """Detect connected Rockchip device."""
    return flash_service.rk_detect_device()


@router.get("/{device_id}/flash/read-id")
async def flash_read_id(device_id: str):
    """Read flash ID from device."""
    return flash_service.rk_read_flash_id()


@router.post("/{device_id}/flash/read")
async def flash_read(device_id: str, req: FlashReadRequest):
    """Read raw flash sectors."""
    return flash_service.rk_read_flash(req.offset_sectors, req.sector_count)


@router.post("/{device_id}/flash/write")
async def flash_write(device_id: str, req: FlashWriteRequest):
    """Write firmware to flash."""
    return flash_service.rk_write_flash(req.offset_sectors, req.input_file)


@router.post("/{device_id}/flash/reset")
async def flash_reset(device_id: str):
    """Reset device out of Loader mode."""
    return flash_service.rk_reset_device()
