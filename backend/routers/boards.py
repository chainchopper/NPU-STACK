"""Board Explorer Router — CRUD for supported NPU-STACK boards."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Body

from services.board_scraper import (
    list_boards,
    get_board,
    save_board,
    delete_board,
    scrape_manufacturer_pages,
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
    """Get a single board by ID with full metadata."""
    board = get_board(board_id)
    if not board:
        raise HTTPException(404, f"Board '{board_id}' not found")
    return {"board": board}


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
