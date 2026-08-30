"""System Agent Router — Nirvana bridge to the absorbed upstream agent + WebUI.

Endpoints:
    GET  /api/agent/status           — Check if the embedded Nirvana bridge is prepared/running
    GET  /api/agent/runtime          — Return upstream Nirvana bridge, onboarding, and path details
    POST /api/agent/init             — Prepare the isolated Nirvana runtime home/config
    POST /api/agent/start            — Launch the upstream Nirvana WebUI on localhost
    POST /api/agent/chat             — Proxy chat through the real upstream Nirvana WebUI session API
    POST /api/agent/generate-dataset — Generate npu_stack_knowledge.jsonl
"""

import os
import json
import shutil
import threading
import re
import uuid
import urllib.parse
from pathlib import Path
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel
from typing import Any, List, Dict, Optional
from sqlalchemy.orm import Session
from database import SessionLocal, ModelRecord, get_db
from services.fleet_orchestrator import build_tool_context as build_fleet_tool_context, create_command_job, execute_command_job, get_command_job, parse_command

router = APIRouter(prefix="/api/agent", tags=["agent"])

# Constants from environment or defaults
AGENT_REPO_ID = "microsoft/Phi-3-mini-4k-instruct-gguf"
AGENT_MODEL_FILENAME = "Phi-3-mini-4k-instruct-q4.gguf"
DATASET_FILENAME = "npu_stack_knowledge.jsonl"

# Thread-safe flag tracking whether a background download is in progress
_download_lock = threading.Lock()
_download_in_progress = False
_DOCS_CONTEXT_CACHE: Optional[str] = None

def _get_token():
    return os.getenv("HUGGINGFACE_TOKEN")

def _model_store():
    # Use the same MODEL_STORE as main.py/huggingface.py
    from main import MODEL_STORE
    return MODEL_STORE

def _model_path():
    return os.path.join(_model_store(), AGENT_MODEL_FILENAME)

def _dataset_path():
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "datasets", DATASET_FILENAME)


def _build_docs_context() -> str:
    """Build a lightweight docs index for immediate in-agent grounding."""
    global _DOCS_CONTEXT_CACHE
    if _DOCS_CONTEXT_CACHE:
        return _DOCS_CONTEXT_CACHE

    project_root = Path(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    doc_roots = [
        project_root / "docs",
        project_root / "gitbook-npu-stack",
        project_root / "gitbook-clone",
        project_root / "frontend",
        project_root / "backend",
    ]

    lines: List[str] = []
    for root in doc_roots:
        if not root.exists() or not root.is_dir():
            continue
        lines.append(f"- {root.name}/")
        files = sorted(
            [
                p
                for p in root.rglob("*")
                if p.is_file() and p.suffix.lower() in {".md", ".txt", ".json", ".yaml", ".yml"}
            ],
            key=lambda p: str(p).lower(),
        )
        for p in files[:15]:
            rel = p.relative_to(project_root).as_posix()
            lines.append(f"  - {rel}")

    lines.append("- External runtime docs: https://docs.nirvanalabs.ai/docs/llms.txt")
    lines.append("- External runtime docs (full): https://docs.nirvanalabs.ai/docs/llms-full.txt")

    _DOCS_CONTEXT_CACHE = "\n".join(lines[:120])
    return _DOCS_CONTEXT_CACHE


def _build_docs_query_context(query: str) -> str:
    """Retrieve query-specific docs context from the unified docs index."""
    try:
        from services.docs_index_service import ensure_docs_index
        from services.docs_index_service import format_docs_context

        ensure_docs_index(max_age_seconds=6 * 3600)
        contextual = format_docs_context(query=query, top_k=5, max_chars=4500)
        if contextual:
            return contextual
    except Exception:
        pass

    # Safe fallback if index is unavailable.
    return _build_docs_context()


# ── Status ──────────────────────────────────────────────


class AgentState(BaseModel):
    is_downloaded: bool
    is_running: bool
    dataset_ready: bool
    download_in_progress: bool = False
    webui_url: Optional[str] = None
    bridge_ready: bool = False
    onboarding_completed: bool = False
    provider_ready: bool = False
    chat_ready: bool = False


@router.get("/runtime")
def get_agent_runtime_details():
    """Return explicit runtime/provenance data for the real upstream Nirvana bridge."""
    from services.nirvana_service import get_bridge_status

    status = get_bridge_status()
    summary = status.get("summary") or {}
    paths = status.get("paths") or {}

    return {
        "agent_name": "Nirvana",
        "engine": "nirvana-webui" if status.get("webui_running") else "nirvana-bridge",
        "bridge_mode": "upstream-webui-sync-proxy",
        "model_file": summary.get("current_model") or "upstream-managed",
        "model_path": summary.get("config_path") or paths.get("config_path"),
        "model_exists": bool(status.get("prepared")),
        "model_loaded": bool(status.get("webui_running")),
        "uses_mock_responses": False,
        "webui_running": bool(status.get("webui_running")),
        "webui_url": status.get("webui_url"),
        "agent_repo_present": bool(status.get("agent_repo_present")),
        "webui_repo_present": bool(status.get("webui_repo_present")),
        "start_script_present": bool(status.get("start_script_present")),
        "prepared": bool(status.get("prepared")),
        "nirvana_home": paths.get("nirvana_home"),
        "webui_state_dir": paths.get("webui_state_dir"),
        "config_path": summary.get("config_path") or paths.get("config_path"),
        "env_path": summary.get("env_path") or paths.get("env_path"),
        "setup_state": summary.get("setup_state") or "not_started",
        "completed": bool(summary.get("completed")),
        "nirvana_found": bool(summary.get("hermes_found")),
        "imports_ok": bool(summary.get("imports_ok")),
        "provider_configured": bool(summary.get("provider_configured")),
        "provider_ready": bool(summary.get("provider_ready")),
        "chat_ready": bool(summary.get("chat_ready")),
        "current_provider": summary.get("current_provider"),
        "current_model": summary.get("current_model"),
        "current_base_url": summary.get("current_base_url"),
        "health": status.get("health"),
        "process": status.get("process"),
        "recommended_commands": status.get("recommended_commands") or [],
        "log_excerpt": status.get("log_excerpt") or "",
    }


@router.get("/status", response_model=AgentState)
def get_agent_status():
    """Check if the embedded upstream Nirvana bridge is prepared and reachable."""
    from services.nirvana_service import get_bridge_status

    status = get_bridge_status()
    summary = status.get("summary") or {}

    return AgentState(
        is_downloaded=bool(status.get("prepared") and status.get("agent_repo_present") and status.get("webui_repo_present")),
        is_running=bool(status.get("webui_running")),
        dataset_ready=bool(summary.get("provider_configured") or summary.get("completed") or status.get("prepared")),
        download_in_progress=False,
        webui_url=status.get("webui_url"),
        bridge_ready=bool(status.get("prepared") and status.get("start_script_present")),
        onboarding_completed=bool(summary.get("completed")),
        provider_ready=bool(summary.get("provider_ready")),
        chat_ready=bool(summary.get("chat_ready")),
    )


# ── Init (Download) ────────────────────────────────────


def _download_model_task():
    global _download_in_progress

    model_path = _model_path()
    model_store = _model_store()
    os.makedirs(model_store, exist_ok=True)

    if not os.path.exists(model_path):
        # Guard against concurrent downloads
        with _download_lock:
            if _download_in_progress:
                return
            _download_in_progress = True

        temp_path = model_path + ".downloading"
        try:
            # Clean up any orphaned partial download from a previous run
            if os.path.exists(temp_path):
                os.remove(temp_path)

            print(f"[Agent] Downloading {AGENT_MODEL_FILENAME} from {AGENT_REPO_ID} via HTTP streaming...")
            import requests

            token = _get_token()
            url = f"https://huggingface.co/{AGENT_REPO_ID}/resolve/main/{AGENT_MODEL_FILENAME}"

            headers = {}
            if token:
                headers["Authorization"] = f"Bearer {token}"

            with requests.get(url, headers=headers, stream=True) as r:
                r.raise_for_status()
                total_size = int(r.headers.get('content-length', 0))
                downloaded = 0

                with open(temp_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192 * 1024):  # 8 MB chunks
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0 and downloaded % (100 * 1024 * 1024) < (8192 * 1024):
                                # Print progress ~ every 100 MB
                                print(f"[Agent] Download progress: {downloaded / (1024*1024):.1f}MB / {total_size / (1024*1024):.1f}MB ({(downloaded/total_size)*100:.1f}%)")

            if os.path.exists(model_path):
                os.remove(model_path)
            shutil.move(temp_path, model_path)

            db = SessionLocal()
            try:
                existing = db.query(ModelRecord).filter(ModelRecord.file_path == model_path).first()
                if not existing:
                    new_model = ModelRecord(
                        name="NPU-STACK System Agent (Phi-3-mini)",
                        framework="llama.cpp",
                        architecture="phi3",
                        format="gguf",
                        file_size=os.path.getsize(model_path),
                        size_mb=os.path.getsize(model_path) / (1024 * 1024),
                        file_path=model_path,
                        quant_type="Q4",
                        description=f"System Agent model: {AGENT_REPO_ID}/{AGENT_MODEL_FILENAME}"
                    )
                    db.add(new_model)
                    db.commit()
            finally:
                db.close()

            print("[Agent] Download complete.")
        except Exception as e:
            print(f"[Agent] Download failed: {e}")
            # Remove incomplete temp file so the next attempt starts fresh
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
        finally:
            with _download_lock:
                _download_in_progress = False


@router.post("/init")
def initialize_agent(background_tasks: BackgroundTasks):
    """Prepare the isolated Nirvana runtime home/config without touching the user's real runtime home."""
    del background_tasks
    from services.nirvana_service import prepare_runtime

    prepared = prepare_runtime()
    return {
        "message": "Prepared isolated Nirvana runtime for NPU-STACK.",
        **prepared,
    }


# ── Start (Load into memory) ───────────────────────────


@router.post("/start")
def start_agent(background_tasks: BackgroundTasks):
    """Launch the real upstream Nirvana WebUI bridge on localhost."""
    del background_tasks
    from services.nirvana_service import NirvanaServiceError, start_webui

    try:
        result = start_webui()
    except NirvanaServiceError as exc:
        raise HTTPException(500, str(exc)) from exc

    if not result.get("success"):
        raise HTTPException(502, result.get("startup_error") or result.get("message") or "Nirvana WebUI failed to start")

    return {
        "success": True,
        "status": "running",
        "message": result.get("message") or "Nirvana WebUI started.",
        "webui_url": result.get("webui_url"),
        "process": result.get("process"),
    }


# ── Chat ────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "You are Nirvana, the built-in system orchestration assistant for NPU-STACK. "
    "Your name is always Nirvana. You help users navigate the NPU-STACK AI Factory, "
    "explaining how to convert models to GGUF, RKNN, or ONNX, how to fine-tune using Unsloth, "
    "and how to deploy to edge hardware like Vitis DPU and NVIDIA NIM. Be concise, technical, and helpful."
)


class ChatRequest(BaseModel):
    messages: List[Dict[str, str]]
    temperature: float = 0.7
    max_tokens: int = 512
    use_fleet_tools: Optional[bool] = None
    use_orchestration_context: Optional[bool] = None
    profile_id: Optional[str] = None
    session_id: Optional[str] = None
    runtime_id: Optional[str] = None
    runtime_mode: Optional[str] = None
    preferred_model: Optional[str] = None
    speak_response: bool = False
    audio_endpoint_id: Optional[str] = None
    audio_group_id: Optional[str] = None


def _deliver_chat_audio(req: ChatRequest, response_text: str) -> Optional[Dict[str, Any]]:
    """Speak a completed response through selected room endpoints, if enabled."""
    if not req.speak_response:
        return None
    try:
        from services.remote_audio import registry, utc_now

        target_ids, selected_group_id = registry.resolve_targets(
            endpoint_id=req.audio_endpoint_id or "",
            group_id=req.audio_group_id or "",
        )
        message_id = f"audio-{uuid.uuid4().hex}"
        results = registry.deliver_sync(
            target_ids,
            {
                "type": "speak",
                "message_id": message_id,
                "text": response_text,
                "source": "nirvana-chat",
                "created_at": utc_now(),
                "audio_format": "text",
                "group_id": selected_group_id,
            },
        )
        return {
            "ok": any(item.get("status") == "delivered" for item in results),
            "message_id": message_id,
            "target_count": len(target_ids),
            "results": results,
        }
    except Exception as exc:  # Audio failure should not discard a valid chat response.
        return {"ok": False, "error": str(exc)[:300], "target_count": 0, "results": []}


def _resolve_chat_profile(profile_id: Optional[str]) -> Dict[str, Any]:
    if not profile_id:
        return {}
    try:
        from routers.orchestration import _load_state as _orch_state

        state = _orch_state()
        profiles = state.get("agent_profiles", [])
        profile = next((p for p in profiles if p.get("id") == profile_id), None)
        return profile or {}
    except Exception:
        return {}


def _profile_system_message(profile: Dict[str, Any]) -> Optional[Dict[str, str]]:
    if not profile:
        return None
    prompt = str(profile.get("system_prompt") or "").strip()
    if not prompt:
        return None
    name = str(profile.get("name") or "Agent Profile").strip()
    return {
        "role": "system",
        "content": f"Active profile ({name}):\n{prompt}",
    }


def _effective_runtime_mode(req: ChatRequest, profile: Dict[str, Any]) -> str:
    requested = str(req.runtime_mode or profile.get("runtime_mode") or "auto").strip().lower()
    if requested in {"local", "external"}:
        return requested
    return "auto"


def _resolve_runtime_binding(req: ChatRequest, profile: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve the selected runtime while retaining legacy runtime_mode callers."""
    from services.agent_runtime_registry import RuntimeRegistryError, resolve_runtime_id

    try:
        return resolve_runtime_id(
            request_runtime_id=req.runtime_id,
            profile_runtime_id=profile.get("runtime_id"),
            legacy_runtime_mode=req.runtime_mode or profile.get("runtime_mode"),
        )
    except RuntimeRegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _effective_preferred_model(req: ChatRequest, profile: Dict[str, Any]) -> str:
    return str(req.preferred_model or profile.get("preferred_model") or "").strip()


def _latest_user_message(messages: List[Dict[str, str]]) -> Dict[str, str]:
    for message in reversed(messages or []):
        if str(message.get("role") or "").strip().lower() == "user":
            return {
                "role": "user",
                "content": str(message.get("content") or ""),
            }
    return {
        "role": "user",
        "content": "",
    }


def _linked_nirvana_session_id(session_id: Optional[str]) -> str:
    if not session_id:
        return ""
    try:
        from routers.orchestration import _load_state as _orch_state

        state = _orch_state()
        sessions = state.get("agent_sessions", [])
        session = next((item for item in sessions if item.get("id") == session_id), None)
        return str((session or {}).get("nirvana_session_id") or "").strip()
    except Exception:
        return ""


def _compose_nirvana_bridge_message(
    user_text: str,
    profile: Dict[str, Any],
    req: ChatRequest,
    *,
    use_fleet_tools: bool,
    use_orchestration_context: bool,
    preferred_model: str,
    fleet_action: Optional[Dict[str, Any]] = None,
) -> str:
    sections: List[str] = []
    profile_name = str(profile.get("name") or "Nirvana Profile").strip()
    profile_prompt = str(profile.get("system_prompt") or "").strip()

    if profile_prompt:
        sections.append(
            f"Profile instructions ({profile_name}):\n{profile_prompt}"
        )

    if use_orchestration_context:
        try:
            from routers.orchestration import _capabilities_catalog, _load_state

            state = _load_state()
            nirvana = state.get("nirvana", {})
            capabilities = _capabilities_catalog(state)
            sections.append(
                "NPU-STACK orchestration context:\n"
                + json.dumps(
                    {
                        "identity": {
                            "agent_name": nirvana.get("agent_name"),
                            "mission": nirvana.get("mission"),
                            "identity_statement": nirvana.get("identity_statement"),
                        },
                        "capability_labels": [tool.get("label") for tool in capabilities.get("tools", [])],
                    },
                    indent=2,
                )
            )
        except Exception as exc:
            sections.append(f"Orchestration context unavailable: {exc}")

    if use_fleet_tools:
        sections.append(
            "Fleet-aware mode is enabled for this turn. Prioritize OTA, discovery, registry, deployment, and remote execution workflows when relevant."
        )
        try:
            sections.append(
                "Fleet tool context:\n"
                + json.dumps(build_fleet_tool_context(include_jobs=True), indent=2)
            )
        except Exception as exc:
            sections.append(f"Fleet tool context unavailable: {exc}")

    if fleet_action:
        sections.append(
            "Fleet action already executed by NPU-STACK for this turn:\n"
            + json.dumps(fleet_action, indent=2)
        )

    if preferred_model:
        sections.append(f"Preferred model hint from NPU-STACK UI: {preferred_model}")
    if req.runtime_mode:
        sections.append(f"Runtime preference from NPU-STACK UI: {req.runtime_mode}")

    if not sections:
        return user_text

    return "\n\n".join(
        [
            "NPU-STACK Nirvana control-plane instructions for this turn:",
            *sections,
            f"User request:\n{user_text}",
        ]
    )


def _compact_fallback_prompt(user_text: str, fleet_action: Optional[Dict[str, Any]] = None) -> str:
    if not fleet_action:
        return user_text

    compact_action = {
        "intent": fleet_action.get("intent"),
        "status": fleet_action.get("status"),
        "target_count": fleet_action.get("target_count"),
        "targets": fleet_action.get("targets"),
        "job_id": fleet_action.get("job_id"),
    }
    return "\n\n".join(
        [
            "NPU-STACK already executed the relevant fleet action for this turn.",
            json.dumps(compact_action, indent=2),
            "Respond concisely to the user, acknowledging the completed action when useful.",
            f"User request:\n{user_text}",
        ]
    )


def _chat_messages_with_bridge_prompt(
    req: ChatRequest,
    profile: Dict[str, Any],
    prompt_text: str,
) -> List[Dict[str, str]]:
    prepared: List[Dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    profile_message = _profile_system_message(profile)
    if profile_message:
        prepared.append(profile_message)

    prior_messages = (req.messages[:-1] if req.messages else [])[-4:]
    for message in prior_messages:
        role = str(message.get("role") or "").strip().lower()
        if role not in {"system", "user", "assistant"}:
            continue
        content = str(message.get("content") or "")
        if not content.strip():
            continue
        prepared.append({"role": role, "content": content})

    prepared.append({"role": "user", "content": prompt_text})
    return prepared


def _response_text_from_result(result: Optional[Dict[str, Any]]) -> str:
    if not isinstance(result, dict):
        return ""
    return (
        str(result.get("response") or "")
        or str(result.get("answer") or "")
        or str((result.get("result") or {}).get("final_response") or "")
    ).strip()


def _upstream_result_needs_recovery(result: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(result, dict):
        return True

    status = str(result.get("status") or result.get("state") or "").strip().lower()
    response_text = _response_text_from_result(result)

    if status in {"error", "partial", "failed"}:
        return True
    if not response_text and status and status != "done":
        return True
    return False


def _upstream_bridge_chat_with_recovery(
    *,
    request_session_id: Optional[str],
    bridged_prompt: str,
    preferred_model: str,
    ensure_webui_running,
    create_webui_session,
    send_sync_chat,
    get_bridge_status,
) -> tuple[Dict[str, Any], str, Optional[Dict[str, Any]], List[str], bool]:
    from services.nirvana_service import NirvanaServiceError

    ensure_webui_running()
    recovery_notes: List[str] = []
    recovered_session = False
    upstream_session_id = _linked_nirvana_session_id(request_session_id)

    if upstream_session_id:
        try:
            existing_result = send_sync_chat(upstream_session_id, bridged_prompt, preferred_model=preferred_model)
            if not _upstream_result_needs_recovery(existing_result):
                return existing_result, upstream_session_id, get_bridge_status(), recovery_notes, recovered_session
            recovery_notes.append(
                f"Stale Nirvana session {upstream_session_id} returned incomplete upstream status"
            )
        except NirvanaServiceError as exc:
            recovery_notes.append(
                f"Stale Nirvana session {upstream_session_id} failed: {exc}"
            )

    created = create_webui_session(preferred_model=preferred_model)
    upstream_session_id = str(created.get("session_id") or "").strip()
    if not upstream_session_id:
        raise NirvanaServiceError("Nirvana WebUI did not return a replacement session during recovery")

    refreshed_result = send_sync_chat(upstream_session_id, bridged_prompt, preferred_model=preferred_model)
    status = get_bridge_status()
    recovered_session = bool(recovery_notes)
    if _upstream_result_needs_recovery(refreshed_result):
        detail = "Replacement Nirvana session still returned incomplete upstream status"
        if recovery_notes:
            detail = " ; ".join([*recovery_notes, detail])
        raise NirvanaServiceError(detail)

    return refreshed_result, upstream_session_id, status, recovery_notes, recovered_session


def _local_agent_chat(
    req: ChatRequest,
    profile: Dict[str, Any],
    fallback_prompt: str,
    runtime_mode: str,
) -> Dict[str, Any]:
    from services.gguf_service import chat_completion as gguf_chat_completion
    from services.gguf_service import is_available as gguf_available
    from services.gguf_service import load_model as gguf_load_model

    model_path = _model_path()
    if not os.path.exists(model_path):
        raise RuntimeError(f"Local Nirvana fallback model not found at {model_path}")
    if not gguf_available():
        raise RuntimeError("llama-cpp-python is not available for local Nirvana fallback")

    load_errors: List[str] = []
    for n_ctx in (4096, 3072, 2048, 1024):
        try:
            gguf_load_model(model_path, n_ctx=n_ctx, n_gpu_layers=0)
            break
        except Exception as exc:
            load_errors.append(f"n_ctx={n_ctx}: {exc}")
    else:
        raise RuntimeError(" ; ".join(load_errors) or "Failed to load local GGUF fallback model")

    response = gguf_chat_completion(
        model_path=model_path,
        messages=_chat_messages_with_bridge_prompt(req, profile, fallback_prompt),
        temperature=req.temperature,
        max_tokens=req.max_tokens,
        top_p=1.0,
        stream=False,
    )

    return {
        "response": (((response or {}).get("choices") or [{}])[0].get("message") or {}).get("content", "") or "No response from local Nirvana fallback.",
        "tool_calls": [],
        "reasoning": None,
        "nirvana_runtime": {
            "agent_name": "Nirvana",
            "engine": "llama-cpp-python",
            "model_file": os.path.basename(model_path),
            "model_loaded": True,
            "uses_mock_responses": False,
            "via": "local-gguf-fallback",
            "profile_id": req.profile_id,
            "profile_name": profile.get("name") if profile else None,
            "runtime_mode": runtime_mode,
            "requested_model": os.path.basename(model_path),
        },
        "raw": response,
    }


def _external_runtime_chat(
    req: ChatRequest,
    profile: Dict[str, Any],
    fallback_prompt: str,
    runtime_mode: str,
) -> Dict[str, Any]:
    try:
        from routers.orchestration import _load_state as _orch_state

        runtime_cfg = (_orch_state().get("hermes") or {})
    except Exception as exc:
        raise RuntimeError(f"Unable to load Nirvana runtime config: {exc}") from exc

    if not runtime_cfg.get("enabled"):
        raise RuntimeError("External Nirvana runtime is disabled")
    if not str(runtime_cfg.get("api_base") or "").strip():
        raise RuntimeError("External Nirvana runtime api_base is not configured")

    return _nirvana_api_chat(
        runtime_cfg,
        req,
        messages=_chat_messages_with_bridge_prompt(req, profile, fallback_prompt),
        profile=profile,
        runtime_mode=runtime_mode,
    )


def _selected_runtime_api_chat(
    runtime: Dict[str, Any],
    req: ChatRequest,
    profile: Dict[str, Any],
    fallback_prompt: str,
) -> Dict[str, Any]:
    """Chat with a selected OpenAI-compatible runtime without Nirvana branding."""
    import requests as _req_lib

    from services.agent_runtime_registry import runtime_endpoint

    runtime_id = str(runtime.get("runtime_id") or "")
    api_base = runtime_endpoint(runtime_id)
    if not api_base:
        raise RuntimeError(f"Runtime {runtime_id} has no chat endpoint")

    model = _effective_preferred_model(req, profile)
    if not model:
        models = runtime.get("models") or []
        model = str((models[0] or {}).get("id") or "") if models else ""
    if not model:
        model = "default"

    messages = _chat_messages_with_bridge_prompt(req, profile, fallback_prompt)
    payload = {
        "model": model,
        "messages": messages,
        "temperature": req.temperature,
        "max_tokens": req.max_tokens,
    }
    base_url = api_base.rstrip("/")
    base_path = urllib.parse.urlsplit(base_url).path.rstrip("/").lower()
    candidate_urls = [f"{base_url}/chat/completions"]
    if not base_path.endswith("/v1"):
        candidate_urls.append(f"{base_url}/v1/chat/completions")
    credential_source = ((runtime.get("configuration") or {}).get("credential_source") or "")
    headers: Dict[str, str] = {"Content-Type": "application/json"}
    if str(credential_source).startswith("env:"):
        credential = os.getenv(str(credential_source)[4:])
        if credential:
            headers["Authorization"] = f"Bearer {credential}"
    else:
        from services.agent_runtime_registry import runtime_credential

        credential = runtime_credential(runtime_id)
        if credential:
            headers["Authorization"] = f"Bearer {credential}"

    data = None
    final_url = candidate_urls[0]
    last_error: Optional[Exception] = None
    for url in candidate_urls:
        try:
            response = _req_lib.post(url, json=payload, headers=headers, timeout=120)
            response.raise_for_status()
            data = response.json()
            final_url = url
            break
        except Exception as exc:  # noqa: PERF203
            last_error = exc
    if not isinstance(data, dict):
        raise RuntimeError(f"Runtime {runtime_id} request failed: {last_error}")

    choice = ((data.get("choices") or [{}])[0] or {}).get("message") or {}
    response_text = str(choice.get("content") or "")
    return {
        "response": response_text,
        "tool_calls": choice.get("tool_calls") or [],
        "reasoning": None,
        "nirvana_runtime": {
            "agent_name": "Nirvana",
            "engine": runtime.get("adapter") or "openai-compatible",
            "runtime_id": runtime_id,
            "runtime_display_name": runtime.get("display_name"),
            "model_file": model,
            "model_loaded": True,
            "uses_mock_responses": False,
            "via": "selected-runtime-openai-compatible",
            "api_base": api_base,
            "request_url": final_url,
            "profile_id": req.profile_id,
            "profile_name": profile.get("name") if profile else None,
            "runtime_mode": "selected",
            "requested_model": model,
        },
        "usage": data.get("usage", {}),
    }


FLEET_ACTION_KEYWORDS = [
    "telemetry",
    "metrics",
    "sensor",
    "monitor",
    "status",
    "health",
    "audit",
    "run ",
    "execute ",
    "shell",
    "reboot",
    "restart",
    "reset",
    "prepare",
    "provision",
    "install",
    "deploy",
    "flash",
    "firmware",
    "backup",
    "pair",
    "unpair",
]

FLEET_EXECUTION_INTENTS = {"status", "telemetry", "shell", "reboot", "provision", "firmware"}


def _looks_like_fleet_instruction(user_text: str) -> bool:
    lowered = str(user_text or "").strip().lower()
    if not lowered:
        return False
    if any(keyword in lowered for keyword in FLEET_ACTION_KEYWORDS):
        return True
    return bool(re.search(r"\b(device|fleet|board|esp32|rp2040|linux-edge|edge node|usb|serial)\b", lowered))


def _compact_result_payload(result: Any) -> Any:
    if isinstance(result, dict):
        compact: Dict[str, Any] = {}
        preferred_keys = [
            "status",
            "transport",
            "source",
            "message",
            "note",
            "error",
            "queued_at",
            "history_count",
            "recorded_at",
            "latest",
            "stdout",
            "stderr",
        ]
        for key in preferred_keys:
            if key in result and result.get(key) not in (None, "", [], {}):
                compact[key] = result.get(key)
        if "latest" in compact and isinstance(compact["latest"], dict):
            latest = compact["latest"]
            compact["latest"] = {
                "source": latest.get("source"),
                "recorded_at": latest.get("recorded_at"),
                "telemetry": latest.get("telemetry"),
            }
        return compact or {k: v for k, v in result.items() if k in {"status", "error"}}
    return result


def _summarize_fleet_action(job: Dict[str, Any], parsed_command: Dict[str, Any]) -> Dict[str, Any]:
    results = job.get("results_by_device") or {}
    devices = []
    for device_id, result in results.items():
        devices.append(
            {
                "device_id": device_id,
                "summary": _compact_result_payload(result),
            }
        )

    return {
        "job_id": job.get("job_id"),
        "intent": job.get("intent") or parsed_command.get("intent"),
        "status": job.get("status"),
        "target_count": job.get("target_count") or len(parsed_command.get("target_devices") or []),
        "targets": [target for target in (parsed_command.get("target_devices") or []) if target != "_no_match"],
        "reasoning_summary": parsed_command.get("reasoning_summary"),
        "results": devices,
    }


def _format_fleet_action_text(fleet_action: Dict[str, Any]) -> str:
    header = (
        f"Fleet action executed: {str(fleet_action.get('intent') or 'unknown').upper()} "
        f"on {fleet_action.get('target_count') or 0} device(s) · status {fleet_action.get('status') or 'unknown'}"
    )
    device_lines = []
    for item in fleet_action.get("results") or []:
        summary = item.get("summary") or {}
        summary_bits = []
        for key in ("status", "transport", "message", "note", "error", "history_count"):
            if summary.get(key) not in (None, "", [], {}):
                summary_bits.append(f"{key}={summary.get(key)}")
        if isinstance(summary.get("latest"), dict) and summary["latest"].get("telemetry"):
            telemetry_keys = sorted(list((summary["latest"].get("telemetry") or {}).keys()))[:6]
            if telemetry_keys:
                summary_bits.append(f"telemetry_keys={','.join(telemetry_keys)}")
        device_lines.append(f"- {item.get('device_id')}: {'; '.join(summary_bits) or 'result captured'}")
    return "\n".join([header, *device_lines])


def _maybe_execute_fleet_action(user_text: str, *, enabled: bool) -> Optional[Dict[str, Any]]:
    if not enabled or not _looks_like_fleet_instruction(user_text):
        return None

    parsed_command = parse_command(user_text, use_agent=False)
    targets = [target for target in (parsed_command.get("target_devices") or []) if target != "_no_match"]
    if parsed_command.get("intent") not in FLEET_EXECUTION_INTENTS:
        return None
    if not targets:
        return None
    if float(parsed_command.get("confidence") or 0.0) < 0.45:
        return None

    job = create_command_job(parsed_command, dry_run=False)
    execute_command_job(job["job_id"], parsed_command, dry_run=False)
    final_job = get_command_job(job["job_id"]) or job
    return _summarize_fleet_action(final_job, parsed_command)


def _persist_session_turn(
    req: ChatRequest,
    profile: Dict[str, Any],
    response_text: str,
    runtime_meta: Optional[Dict[str, Any]] = None,
    fleet_action: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    if not req.session_id or not req.profile_id:
        return None
    try:
        from routers.orchestration import record_agent_session_turn

        return record_agent_session_turn(
            session_id=req.session_id,
            profile_id=req.profile_id,
            user_message=_latest_user_message(req.messages),
            assistant_message={
                "role": "assistant",
                "content": response_text or "",
                "fleet_action": fleet_action,
            },
            runtime_meta=runtime_meta,
        )
    except Exception:
        return None


@router.post("/chat")
def agent_chat(req: ChatRequest):
    """Chat with the real upstream Nirvana WebUI session API."""
    profile = _resolve_chat_profile(req.profile_id)
    use_fleet_tools = req.use_fleet_tools if req.use_fleet_tools is not None else bool(profile.get("use_fleet_tools"))
    use_orchestration_context = (
        req.use_orchestration_context
        if req.use_orchestration_context is not None
        else bool(profile.get("use_orchestration_context", True))
    )
    runtime_binding = _resolve_runtime_binding(req, profile)
    selected_runtime = runtime_binding["runtime"]
    selected_runtime_id = str(selected_runtime.get("runtime_id") or "nirvana-default")
    runtime_mode = _effective_runtime_mode(req, profile)
    preferred_model = _effective_preferred_model(req, profile)
    from services.nirvana_service import (
        NirvanaServiceError,
        create_webui_session,
        ensure_webui_running,
        get_bridge_status,
        send_sync_chat,
    )

    user_message = _latest_user_message(req.messages)
    user_text = str(user_message.get("content") or "")
    fleet_action = _maybe_execute_fleet_action(
        user_text,
        enabled=bool(use_fleet_tools),
    )
    bridged_prompt = _compose_nirvana_bridge_message(
        user_text,
        profile,
        req,
        use_fleet_tools=use_fleet_tools,
        use_orchestration_context=use_orchestration_context,
        preferred_model=preferred_model,
        fleet_action=fleet_action,
    )
    compact_fallback_prompt = _compact_fallback_prompt(user_text, fleet_action)

    upstream_session_id = ""
    status: Optional[Dict[str, Any]] = None
    chat_result: Optional[Dict[str, Any]] = None
    fallback_errors: List[str] = []
    recovered_session = False

    if selected_runtime_id == "nirvana-default" and runtime_mode == "local":
        try:
            chat_result = _local_agent_chat(req, profile, compact_fallback_prompt, runtime_mode)
        except Exception as exc:
            raise HTTPException(502, f"Local Nirvana runtime failed: {exc}") from exc
    elif selected_runtime_id == "nirvana-default" and runtime_mode == "external":
        try:
            chat_result = _external_runtime_chat(req, profile, compact_fallback_prompt, runtime_mode)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(502, f"External Nirvana runtime failed: {exc}") from exc
    elif selected_runtime_id != "nirvana-default":
        try:
            chat_result = _selected_runtime_api_chat(
                selected_runtime,
                req,
                profile,
                compact_fallback_prompt,
            )
        except Exception as exc:
            # Explicit runtime selection must fail loudly; do not silently route
            # a user's chosen runtime to Nirvana.
            raise HTTPException(502, f"Selected runtime {selected_runtime_id} failed: {exc}") from exc
    else:
        try:
            chat_result, upstream_session_id, status, recovery_notes, recovered_session = _upstream_bridge_chat_with_recovery(
                request_session_id=req.session_id,
                bridged_prompt=bridged_prompt,
                preferred_model=preferred_model,
                ensure_webui_running=ensure_webui_running,
                create_webui_session=create_webui_session,
                send_sync_chat=send_sync_chat,
                get_bridge_status=get_bridge_status,
            )
            fallback_errors.extend(recovery_notes)
        except NirvanaServiceError as exc:
            fallback_errors.append(str(exc))
            try:
                status = get_bridge_status()
            except Exception:
                status = None
        except Exception as exc:
            fallback_errors.append(f"Nirvana bridge failed: {exc}")

        if chat_result is None:
            try:
                chat_result = _local_agent_chat(req, profile, compact_fallback_prompt, runtime_mode)
            except Exception as exc:
                fallback_errors.append(str(exc))

        if chat_result is None:
            try:
                chat_result = _external_runtime_chat(req, profile, compact_fallback_prompt, runtime_mode)
            except HTTPException as exc:
                fallback_errors.append(str(exc.detail))
            except Exception as exc:
                fallback_errors.append(str(exc))

        if chat_result is None:
            raise HTTPException(502, " ; ".join(error for error in fallback_errors if error) or "Nirvana chat failed")

    response_text = (
        str(chat_result.get("response") or "")
        or str(chat_result.get("answer") or "")
        or str((chat_result.get("result") or {}).get("final_response") or "")
    )
    if fleet_action:
        fleet_prefix = _format_fleet_action_text(fleet_action)
        response_text = f"{fleet_prefix}\n\n{response_text}" if response_text else fleet_prefix
    audio_delivery = _deliver_chat_audio(req, response_text)
    runtime_meta = {
        **(chat_result.get("nirvana_runtime") or {
            "agent_name": "Nirvana",
            "engine": "nirvana-webui",
            "model_file": ((status or {}).get("summary") or {}).get("current_model") or preferred_model or "upstream-managed",
            "model_loaded": bool((status or {}).get("webui_running")),
            "uses_mock_responses": False,
            "via": "nirvana-webui-sync-chat",
            "runtime_mode": runtime_mode,
            "requested_model": preferred_model or None,
            "profile_id": req.profile_id,
            "profile_name": profile.get("name") if profile else None,
            "nirvana_session_id": upstream_session_id,
            "webui_url": (status or {}).get("webui_url"),
            "provider": (((status or {}).get("summary") or {}).get("current_provider")),
            "chat_ready": bool((((status or {}).get("summary") or {}).get("chat_ready"))),
            "onboarding_completed": bool((((status or {}).get("summary") or {}).get("completed"))),
        }),
        "runtime_mode": (chat_result.get("nirvana_runtime") or {}).get("runtime_mode") or runtime_mode,
        "runtime_id": selected_runtime_id,
        "runtime_binding_source": runtime_binding.get("binding_source"),
        "runtime_adapter": selected_runtime.get("adapter"),
        "runtime_status": selected_runtime.get("status"),
        "profile_id": req.profile_id,
        "profile_name": profile.get("name") if profile else None,
        "nirvana_session_id": upstream_session_id or (chat_result.get("nirvana_runtime") or {}).get("nirvana_session_id"),
        "webui_url": (chat_result.get("nirvana_runtime") or {}).get("webui_url") or ((status or {}).get("webui_url")),
        "fleet_action_job_id": fleet_action.get("job_id") if fleet_action else None,
        "fleet_action_intent": fleet_action.get("intent") if fleet_action else None,
        "session_recovered": bool((chat_result.get("nirvana_runtime") or {}).get("session_recovered")) or recovered_session,
        "fallback_errors": fallback_errors or None,
    }

    persisted_session = _persist_session_turn(
        req,
        profile,
        response_text,
        runtime_meta=runtime_meta,
        fleet_action=fleet_action,
    )

    result = {
        "response": response_text,
        "tool_calls": [],
        "reasoning": None,
        "nirvana_runtime": runtime_meta,
        "fleet_action": fleet_action,
        "audio_delivery": audio_delivery,
        "upstream": {
            "session_id": upstream_session_id or None,
            "status": chat_result.get("status") or chat_result.get("raw", {}).get("status"),
        },
    }
    if persisted_session:
        result["agent_session"] = {
            "id": persisted_session.get("id"),
            "title": persisted_session.get("title"),
            "updated_at": persisted_session.get("updated_at"),
            "message_count": persisted_session.get("message_count"),
        }

    return result


# ── External runtime API proxy ───────────────────────


def _nirvana_api_chat(
    runtime_cfg: dict,
    req: "ChatRequest",
    messages: Optional[List[Dict[str, str]]] = None,
    profile: Optional[Dict[str, Any]] = None,
    runtime_mode: str = "auto",
) -> dict:
    """Proxy a chat request to the external Nirvana OpenAI-compatible runtime API."""
    import requests as _req_lib  # local import to avoid polluting module scope

    api_base = (runtime_cfg.get("api_base") or "http://localhost:11437/v1").rstrip("/")
    model = runtime_cfg.get("default_model") or "default"

    payload = {
        "model": model,
        "messages": messages if messages is not None else req.messages,
        "temperature": req.temperature,
        "max_tokens": req.max_tokens,
    }

    candidate_bases = [api_base]
    if api_base.endswith("/v1"):
        candidate_bases.append(api_base[:-3])
    else:
        candidate_bases.append(f"{api_base}/v1")

    data = None
    final_base = api_base
    last_error: Optional[Exception] = None
    try:
        for base in candidate_bases:
            try:
                r = _req_lib.post(
                    f"{base.rstrip('/')}/chat/completions",
                    json=payload,
                    timeout=120,
                )
                r.raise_for_status()
                data = r.json()
                final_base = base.rstrip("/")
                break
            except Exception as exc:  # noqa: PERF203
                last_error = exc
        if data is None:
            raise last_error or RuntimeError("no successful runtime endpoint")
    except _req_lib.exceptions.ConnectionError:
        raise HTTPException(502, f"Cannot connect to Nirvana runtime API at {api_base}. Ensure the runtime is running.")
    except _req_lib.exceptions.Timeout:
        raise HTTPException(504, "Nirvana runtime API request timed out after 120 s.")
    except Exception as exc:
        raise HTTPException(502, f"Nirvana runtime API error: {exc}")

    choice = data["choices"][0]["message"]
    raw_tool_calls = choice.get("tool_calls") or []

    return {
        "response": choice.get("content") or "",
        "tool_calls": [
            {
                "name": tc["function"]["name"],
                "args": tc["function"].get("arguments", ""),
                "result": None,
            }
            for tc in raw_tool_calls
        ],
        "reasoning": None,
        "nirvana_runtime": {
            "agent_name": "Nirvana",
            "engine": "nirvana-runtime-proxy",
            "model_file": model,
            "model_loaded": True,
            "uses_mock_responses": False,
            "api_base": final_base,
            "via": "nirvana-proxy",
            "profile_id": req.profile_id,
            "profile_name": profile.get("name") if profile else None,
            "runtime_mode": runtime_mode,
            "requested_model": model,
        },
        "usage": data.get("usage", {}),
    }


# ── Generate Dataset ────────────────────────────────────


@router.post("/generate-dataset")
def generate_knowledge_dataset():
    """Generates the npu_stack_knowledge.jsonl dataset from local docs."""
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    dataset_dir = os.path.dirname(_dataset_path())
    os.makedirs(dataset_dir, exist_ok=True)

    readme_path = os.path.join(root_dir, "README.md")
    knowledge_items = []

    # 1. Base Identity
    knowledge_items.append({
        "instruction": "Who are you and what is your purpose?",
        "input": "",
        "output": (
            "I am the NPU-STACK System Assistant. My purpose is to guide users through the NPU-STACK platform, "
            "helping them train, convert, quantize, and deploy AI models across local CPUs, GPUs, and Neural "
            "Processing Units (NPUs)."
        ),
    })

    # 2. Extract from README
    if os.path.exists(readme_path):
        with open(readme_path, "r", encoding="utf-8") as f:
            content = f.read()
            chunks = [content[i : i + 1000] for i in range(0, len(content), 1000)]
            for i, chunk in enumerate(chunks):
                knowledge_items.append({
                    "instruction": "Tell me about NPU-STACK features.",
                    "input": f"Part {i + 1}",
                    "output": chunk,
                })

    dataset_path = _dataset_path()
    with open(dataset_path, "w", encoding="utf-8") as f:
        for item in knowledge_items:
            f.write(json.dumps(item) + "\n")

    return {"message": f"Generated {len(knowledge_items)} items.", "path": dataset_path}
