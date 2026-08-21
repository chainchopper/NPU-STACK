"""Board Explorer Router — CRUD for supported NPU-STACK boards."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Body
from fastapi.responses import FileResponse

from services.board_scraper import (
    list_boards,
    get_board,
    save_board,
    delete_board,
    scrape_manufacturer_pages,
    related_devices,
    board_assets,
    BOARD_ASSETS_DIR,
    BOARDS_DIR,
)

router = APIRouter(prefix="/api/boards", tags=["boards"])


@router.get("")
def api_list_boards(manufacturer: Optional[str] = None, tag: Optional[str] = None):
    """List all supported boards, with optional manufacturer/tag filters."""
    boards = list_boards(manufacturer=manufacturer, tag=tag)
    return {"boards": boards, "count": len(boards)}


@router.get("/manufacturers")
def api_list_manufacturers():
    """List known board manufacturers with metadata."""
    from services.board_scraper import BOARD_MANUFACTURERS
    return {"manufacturers": list(BOARD_MANUFACTURERS.values()), "count": len(BOARD_MANUFACTURERS)}


@router.get("/{board_id}")
def api_get_board(board_id: str):
    """Get a single board by ID with full metadata + live fleet status."""
    board = get_board(board_id)
    if not board:
        raise HTTPException(404, f"Board '{board_id}' not found")

    devices = related_devices(board)
    paired = [d for d in devices if d.get("paired")]
    online = [d for d in devices if d.get("available")]
    return {
        "board": board,
        "devices": devices,
        "paired_devices": paired,
        "status": {
            "paired": bool(paired),
            "paired_count": len(paired),
            "online_count": len(online),
            "device_count": len(devices),
        },
        "assets": board_assets(board_id),
    }


@router.get("/{board_id}/assets/{path:path}")
def api_board_asset(board_id: str, path: str):
    """Serve a board reference asset (pinout image, PDF, STL, scraped photo...).

    Looks first under backend/data/boards/assets/<board_id>/ (organized
    downloads), then under backend/data/boards/<board_id>/ (legacy scraped
    screenshots/diagrams).
    """
    board = get_board(board_id)
    if not board:
        raise HTTPException(404, f"Board '{board_id}' not found")

    # Prevent path traversal.
    safe = Path(path)
    if safe.is_absolute() or ".." in safe.parts:
        raise HTTPException(400, "Invalid asset path")

    for root in (BOARD_ASSETS_DIR / board_id, BOARDS_DIR / board_id):
        try:
            candidate = (root / safe).resolve()
            candidate.relative_to(root.resolve())
        except ValueError:
            continue
        if candidate.is_file():
            return FileResponse(candidate)

    raise HTTPException(404, f"Asset '{path}' not found for board '{board_id}'")


@router.post("")
def api_save_board(payload: dict = Body(...)):
    """Create or update a board entry."""
    board = save_board(payload)
    return {"board": board, "created": "created_at" not in payload}


@router.delete("/{board_id}")
def api_delete_board(board_id: str):
    """Delete a board entry."""
    if not delete_board(board_id):
        raise HTTPException(404, f"Board '{board_id}' not found")
    return {"deleted": board_id}


@router.post("/scrape")
async def api_scrape(query: str = ""):
    """Trigger a lightweight scrape of manufacturer sites."""
    results = await scrape_manufacturer_pages(query)
    return {"results": results, "count": len(results)}
