"""Fleet Command Orchestrator — natural-language fleet parsing, execution, and templates."""

from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field

from services.edge_discovery import list_registry_devices
from services.fleet_orchestrator import (
        create_command_job,
        execute_command_job,
    get_command_history as get_command_history_service,
        get_command_job,
        get_command_template,
        list_command_templates,
        parse_command as parse_fleet_command,
)

router = APIRouter(prefix="/api/fleet/command", tags=["fleet-command"])


# ── Models ────────────────────────────────────────────────────

class ParseCommandRequest(BaseModel):
    command: str
    context: Optional[Dict] = None  # e.g., user preferences, defaults
    use_agent: bool = True


class ParsedCommand(BaseModel):
    command_text: str
    intent: str  # e.g., "provision", "update_firmware", "get_status", "execute_shell"
    target_devices: List[str]  # device IDs
    action_params: Dict  # action-specific parameters
    confidence: float
    alternatives: List[Dict] = []
    template_id: Optional[str] = None
    reasoning_summary: Optional[str] = None
    tool_context: Dict[str, Any] = Field(default_factory=dict)


class ExecuteCommandRequest(BaseModel):
    parsed_command: ParsedCommand
    dry_run: bool = False


class CommandResult(BaseModel):
    job_id: str
    status: str  # "queued", "executing", "complete", "failed"
    command_text: str
    intent: str
    target_count: int
    results_by_device: Dict[str, Dict]
    created_at: str
    completed_at: Optional[str] = None
    reasoning_summary: Optional[str] = None
    template_id: Optional[str] = None
    tool_context: Dict[str, Any] = Field(default_factory=dict)


@router.post("/parse", response_model=ParsedCommand)
def parse_command(req: ParseCommandRequest):
    """Parse natural language into structured fleet intent, targets, and action params."""
    try:
        parsed = parse_fleet_command(req.command, use_agent=req.use_agent, context=req.context)
        return ParsedCommand(**parsed)
    except Exception as e:
        raise HTTPException(400, f"Failed to parse command: {str(e)}")


@router.post("/execute", response_model=CommandResult)
def execute_command(req: ExecuteCommandRequest, bg_tasks: BackgroundTasks):
    """Queue a parsed fleet command and execute it in the background."""
    parsed_payload = req.parsed_command.model_dump()
    job = create_command_job(parsed_payload, dry_run=req.dry_run)
    bg_tasks.add_task(execute_command_job, job["job_id"], parsed_payload, req.dry_run)
    return CommandResult(**job)


@router.get("/jobs/{job_id}", response_model=CommandResult)
def get_job_status(job_id: str):
    """Poll status of a command job."""
    job = get_command_job(job_id)
    if not job:
        raise HTTPException(404, f"Job '{job_id}' not found")
    return CommandResult(**job)


@router.get("/history")
def get_command_history(limit: int = Query(50, ge=1, le=500)):
    """List recent command execution history."""
    return get_command_history_service(limit)


@router.get("/templates")
def list_templates():
    """Return pre-built fleet recipes/templates for common operations."""
    templates = list_command_templates()
    return {"templates": templates, "count": len(templates)}


@router.post("/templates/{template_id}/parse", response_model=ParsedCommand)
def parse_template(template_id: str, context: Optional[Dict[str, Any]] = None):
    """Instantiate a command template as a parsed fleet command."""
    template = get_command_template(template_id)
    if not template:
        raise HTTPException(404, f"Template '{template_id}' not found")

    selector = template.get("target_selector") or "all"
    prompt = context.get("prompt") if context else template.get("example") or template["label"]
    parsed = parse_fleet_command(str(prompt), use_agent=False, context=context)
    parsed["intent"] = template["intent"]
    parsed["template_id"] = template["id"]
    parsed["action_params"] = {**template.get("action_params", {}), **parsed.get("action_params", {})}
    devices = list_registry_devices(include_low_confidence=False).get("devices", [])
    if selector == "all":
        parsed["target_devices"] = [device.get("id") for device in devices]
    elif selector == "linux":
        parsed["target_devices"] = [
            device.get("id")
            for device in devices
            if str(device.get("tier", "")).lower() == "sbc"
        ]
    return ParsedCommand(**parsed)
