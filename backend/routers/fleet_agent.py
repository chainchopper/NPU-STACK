"""Fleet mobile-agent callback router for registration, heartbeats, and polled jobs."""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from services.fleet_orchestrator import (
    AGENT_SHARED_SECRET,
    claim_mobile_agent_job,
    heartbeat_mobile_agent,
    register_mobile_agent,
    report_mobile_agent_job_result,
)

router = APIRouter(prefix="/api/fleet/agent", tags=["fleet-agent"])


def _validate_secret(secret: Optional[str]) -> None:
    if AGENT_SHARED_SECRET and secret != AGENT_SHARED_SECRET:
        raise HTTPException(401, "Invalid or missing agent secret")


class AgentRegistrationRequest(BaseModel):
    device_id: Optional[str] = None
    device_name: str
    family: Optional[str] = None
    chip: Optional[str] = None
    machine: Optional[str] = None
    host: Optional[str] = None
    ip: Optional[str] = None
    agent_port: int = 9200
    agent_endpoint: Optional[str] = None
    agent_version: Optional[str] = None
    status: str = "online"
    connection: str = "wifi"
    description: Optional[str] = None
    capabilities: Dict[str, Any] = Field(default_factory=dict)
    telemetry: Dict[str, Any] = Field(default_factory=dict)
    agent_transport: str = "polling"
    transport_preference: str = "agent-poll"


class AgentHeartbeatRequest(BaseModel):
    device_id: str
    host: Optional[str] = None
    ip: Optional[str] = None
    status: str = "online"
    agent_port: int = 9200
    agent_endpoint: Optional[str] = None
    agent_version: Optional[str] = None
    firmware_version: Optional[str] = None
    description: Optional[str] = None
    telemetry: Dict[str, Any] = Field(default_factory=dict)


class AgentJobResultRequest(BaseModel):
    status: str
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    exit_code: Optional[int] = None
    transport: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)


@router.post("/register")
def register_agent(req: AgentRegistrationRequest, x_npu_agent_secret: Optional[str] = Header(default=None)):
    _validate_secret(x_npu_agent_secret)
    return register_mobile_agent(req.model_dump(exclude_none=True))


@router.post("/heartbeat")
def agent_heartbeat(req: AgentHeartbeatRequest, x_npu_agent_secret: Optional[str] = Header(default=None)):
    _validate_secret(x_npu_agent_secret)
    try:
        return heartbeat_mobile_agent(req.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/jobs/claim")
def claim_job(device_id: str = Query(...), x_npu_agent_secret: Optional[str] = Header(default=None)):
    _validate_secret(x_npu_agent_secret)
    return claim_mobile_agent_job(device_id)


@router.post("/jobs/{job_id}/result")
def report_job_result(job_id: str, req: AgentJobResultRequest, device_id: str = Query(...), x_npu_agent_secret: Optional[str] = Header(default=None)):
    _validate_secret(x_npu_agent_secret)
    payload = req.model_dump(exclude_none=True)
    payload.update(payload.pop("details", {}))
    try:
        return report_mobile_agent_job_result(device_id, job_id, payload)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc