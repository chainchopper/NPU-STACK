"""Nirvana WebUI — native FastAPI routes that read/write the shared state
directly, bypassing the separate WebUI process.

These replace the proxy for management endpoints so NPU-STACK has native
control over Nirvana settings, sessions, skills, and cron state.
The absorbed WebUI at :8789 still handles chat/streaming until Phase 3.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

REPO_ROOT = Path(__file__).resolve().parents[2]
NIRVANA_DATA_DIR = REPO_ROOT / "backend" / "data" / "nirvana-runtime"
HERMES_HOME = NIRVANA_DATA_DIR / ".hermes"
WEBUI_STATE_DIR = NIRVANA_DATA_DIR / "webui"
SETTINGS_PATH = WEBUI_STATE_DIR / "settings.json"
SESSIONS_INDEX = WEBUI_STATE_DIR / "sessions" / "_index.json"
SKILLS_USAGE_PATH = HERMES_HOME / "skills" / ".usage.json"
SKILLS_DIR = HERMES_HOME / "skills"
CRON_DIR = HERMES_HOME / "cron"
CONFIG_PATH = HERMES_HOME / "config.yaml"

router = APIRouter(prefix="/api/nirvana", tags=["nirvana-native"])


# ── Helpers ──────────────────────────────────────────────────────────────

def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise HTTPException(404, f"State file not found: {path.name}")
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise HTTPException(500, f"Invalid JSON in {path.name}: {exc}")


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


# ── Settings ─────────────────────────────────────────────────────────────

class SettingsUpdate(BaseModel):
    theme: Optional[str] = None
    skin: Optional[str] = None
    font_size: Optional[str] = None
    bot_name: Optional[str] = None
    language: Optional[str] = None
    default_model_provider: Optional[str] = None


@router.get("/settings")
def get_settings() -> Dict[str, Any]:
    """Read all Nirvana settings directly from the shared state file."""
    return _read_json(SETTINGS_PATH)


@router.patch("/settings")
def update_settings(body: SettingsUpdate) -> Dict[str, Any]:
    """Update one or more Nirvana settings in-place."""
    settings = _read_json(SETTINGS_PATH)
    updates = body.model_dump(exclude_none=True)

    if "bot_name" in updates and updates["bot_name"].lower() in ("hermes", "hermes agent"):
        raise HTTPException(400, "The agent name is Nirvana, not Hermes.")

    for key, value in updates.items():
        if key in settings:
            settings[key] = value

    _write_json(SETTINGS_PATH, settings)
    return settings


# ── Sessions ─────────────────────────────────────────────────────────────

@router.get("/sessions")
def list_sessions(
    limit: int = 50,
    pinned_only: bool = False,
) -> List[Dict[str, Any]]:
    """List Nirvana sessions from the shared index."""
    sessions: list = json.loads(
        SESSIONS_INDEX.read_text(encoding="utf-8", errors="replace")
    ) if SESSIONS_INDEX.exists() else []

    if pinned_only:
        sessions = [s for s in sessions if s.get("pinned")]

    return sessions[:limit]


@router.get("/sessions/{session_id}")
def get_session(session_id: str) -> Dict[str, Any]:
    """Get a single Nirvana session by ID."""
    session_file = WEBUI_STATE_DIR / "sessions" / f"{session_id}.json"
    if not session_file.exists():
        raise HTTPException(404, f"Session not found: {session_id}")
    return _read_json(session_file)


# ── Skills ───────────────────────────────────────────────────────────────

@router.get("/skills")
def list_skills() -> Dict[str, Any]:
    """List all Nirvana skills with usage metadata."""
    usage = _read_json(SKILLS_USAGE_PATH) if SKILLS_USAGE_PATH.exists() else {}

    skills = []
    for category_dir in SKILLS_DIR.iterdir():
        if not category_dir.is_dir() or category_dir.name.startswith("."):
            continue
        for skill_dir in category_dir.iterdir():
            if not skill_dir.is_dir() or skill_dir.name.startswith("."):
                continue
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue

            name = skill_dir.name
            meta = usage.get(name, {})
            skills.append({
                "name": name,
                "category": category_dir.name,
                "state": meta.get("state", "active"),
                "pinned": meta.get("pinned", False),
                "use_count": meta.get("use_count", 0),
                "created_by": meta.get("created_by", "unknown"),
                "path": str(skill_md.relative_to(HERMES_HOME)),
            })

    return {"skills": skills, "count": len(skills)}


@router.get("/skills/{skill_name}")
def get_skill(skill_name: str) -> Dict[str, Any]:
    """Read a single skill's SKILL.md content."""
    for category_dir in SKILLS_DIR.iterdir():
        if not category_dir.is_dir() or category_dir.name.startswith("."):
            continue
        skill_md = category_dir / skill_name / "SKILL.md"
        if skill_md.exists():
            return {
                "name": skill_name,
                "category": category_dir.name,
                "path": str(skill_md.relative_to(HERMES_HOME)),
                "content": skill_md.read_text(encoding="utf-8", errors="replace"),
            }
    raise HTTPException(404, f"Skill not found: {skill_name}")


# ── Config ───────────────────────────────────────────────────────────────

@router.get("/config")
def get_config() -> Dict[str, Any]:
    """Read the Nirvana runtime config (model provider, terminal, browser)."""
    if not CONFIG_PATH.exists():
        raise HTTPException(404, "Nirvana config not found")

    import yaml
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except Exception as exc:
        raise HTTPException(500, f"Failed to read config: {exc}")


# ── Health ───────────────────────────────────────────────────────────────

@router.get("/health")
def nirvana_health() -> Dict[str, Any]:
    """Quick health check for native Nirvana state accessibility."""
    return {
        "ok": True,
        "settings_exists": SETTINGS_PATH.exists(),
        "sessions_index_exists": SESSIONS_INDEX.exists(),
        "skills_usage_exists": SKILLS_USAGE_PATH.exists(),
        "config_exists": CONFIG_PATH.exists(),
        "bot_name": _read_json(SETTINGS_PATH).get("bot_name", "unknown"),
        "theme": _read_json(SETTINGS_PATH).get("theme", "unknown"),
    }


# ── Cron ─────────────────────────────────────────────────────────────────

@router.get("/cron")
def list_cron_jobs() -> Dict[str, Any]:
    """List Nirvana cron jobs and recent output files."""
    jobs = []
    output_dir = CRON_DIR / "output"
    for f in sorted(output_dir.glob("*.json"), reverse=True) if output_dir.exists() else []:
        try:
            data = _read_json(f)
            data["_file"] = f.name
            jobs.append(data)
        except Exception:
            jobs.append({"_file": f.name, "error": "unreadable"})

    return {"jobs": jobs, "count": len(jobs), "output_dir": str(output_dir)}


# ── Overview ─────────────────────────────────────────────────────────────

@router.get("/overview")
def nirvana_overview() -> Dict[str, Any]:
    """Aggregated Nirvana summary for the dashboard."""
    settings = _read_json(SETTINGS_PATH) if SETTINGS_PATH.exists() else {}
    sessions: list = json.loads(
        SESSIONS_INDEX.read_text(encoding="utf-8", errors="replace")
    ) if SESSIONS_INDEX.exists() else []
    skills = list_skills()

    return {
        "agent": {
            "name": settings.get("bot_name", "Nirvana"),
            "provider": settings.get("default_model_provider", "unknown"),
            "theme": settings.get("theme", "dark"),
            "onboarding_completed": settings.get("onboarding_completed", False),
        },
        "config": get_config() if CONFIG_PATH.exists() else {},
        "sessions": {
            "total": len(sessions),
            "pinned": sum(1 for s in sessions if s.get("pinned")),
            "recent": [{
                "id": s.get("session_id"),
                "title": (s.get("title") or "Untitled").split("\n")[0][:60],
                "model": s.get("model"),
                "message_count": s.get("message_count", 0),
            } for s in sessions[:5]],
        },
        "skills": {
            "count": skills["count"],
            "names": [s["name"] for s in skills["skills"]],
        },
    }
