"""Nirvana audio routing — Home Assistant plus the room-wide browser fabric.

The XIAO has no DAC, so the agent "speaks" by routing TTS to a device that can
play it: Home Assistant's `tts` service (Piper / Google / Cloud — cheap/local,
NOT ElevenLabs in production), played on any media_player / ESPHome speaker.

Config (env or .env):
    HA_BASE_URL   e.g. http://homeassistant.local:8123
    HA_TOKEN      long-lived access token

Endpoints:
    GET  /api/nirvana/say/status   -> HA config + available TTS engines
    POST /api/nirvana/say          -> {text, entity_id?} -> HA tts.speak
    WS   /api/nirvana/audio/ws     -> browser endpoint registration/playback
    POST /api/nirvana/audio/speak  -> direct or room broadcast text delivery
"""
import asyncio
import os
import uuid

import httpx
from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from services.managed_audio import (
    ENROLLMENT_CONTRACT,
    CredentialUnavailable,
    managed_audio,
    pairing,
)
from services.remote_audio import MAX_TEXT_LENGTH, registry, utc_now

router = APIRouter(prefix="/api/nirvana", tags=["nirvana-audio"])


def _ha_base() -> str:
    return os.getenv("HA_BASE_URL", "http://homeassistant.local:8123").rstrip("/")


def _ha_token() -> str:
    return os.getenv("HA_TOKEN", "").strip()


class SayRequest(BaseModel):
    text: str
    entity_id: str = ""          # optional media_player entity to target
    engine: str = ""             # e.g. "piper" — blank = HA default TTS


class AudioGroupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    endpoint_ids: list[str] = Field(default_factory=list, max_length=100)


class AudioSpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT_LENGTH)
    endpoint_id: str = ""
    group_id: str = ""
    endpoint_ids: list[str] = Field(default_factory=list, max_length=100)
    source: str = Field(default="nirvana", max_length=80)
    voice: str = Field(default="", max_length=120)
    rate: float = Field(default=1.0, ge=0.1, le=4.0)
    volume: float = Field(default=1.0, ge=0.0, le=1.0)


class AudioStopRequest(BaseModel):
    endpoint_id: str = ""
    group_id: str = ""
    endpoint_ids: list[str] = Field(default_factory=list, max_length=100)
    message_id: str = Field(default="", max_length=120)


class ManagedHAProfileRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    base_url: str = Field(min_length=1, max_length=300)
    token: str | None = Field(default=None, min_length=1, max_length=1000)
    entity_id: str = Field(default="", max_length=160)
    engine: str = Field(default="speak", max_length=80)
    enabled: bool = True


class PairingChallengeRequest(BaseModel):
    endpoint_id: str = Field(default="", max_length=120)
    endpoint_type: str = Field(default="browser", max_length=32)


class PairingClaimRequest(BaseModel):
    challenge_id: str = Field(min_length=1, max_length=160)
    pairing_code: str = Field(min_length=6, max_length=6)
    endpoint_id: str = Field(min_length=1, max_length=120)
    endpoint_type: str = Field(default="browser", max_length=32)
    capabilities: list[str] = Field(default_factory=lambda: ["speech"], max_length=20)


def _target_error(exc: Exception) -> HTTPException:
    if isinstance(exc, KeyError):
        return HTTPException(404, f"Audio room or endpoint not found: {exc.args[0]}")
    return HTTPException(400, str(exc))


def _all_audio_endpoints() -> list[dict]:
    browser_endpoints = registry.list_endpoints()
    managed_endpoints = managed_audio.endpoints()
    return sorted(
        [*browser_endpoints, *managed_endpoints],
        key=lambda item: (not item.get("online"), item.get("name", "").lower()),
    )


@router.get("/audio/endpoints")
def list_audio_endpoints(
    online: bool | None = Query(default=None),
    endpoint_type: str | None = Query(default=None),
):
    """List browser/audio endpoints known to the room fabric."""
    endpoints = _all_audio_endpoints()
    if online is not None:
        endpoints = [endpoint for endpoint in endpoints if endpoint.get("online") is online]
    if endpoint_type:
        endpoints = [endpoint for endpoint in endpoints if endpoint.get("endpoint_type") == endpoint_type]
    return {"endpoints": endpoints}


@router.get("/audio/home-assistant/profiles")
def list_home_assistant_profiles():
    return {"profiles": managed_audio.list_profiles()}


@router.post("/audio/home-assistant/profiles")
def create_home_assistant_profile(req: ManagedHAProfileRequest):
    if not req.token:
        raise HTTPException(400, "token is required when creating a Home Assistant profile")
    try:
        profile = managed_audio.create_profile(
            name=req.name,
            base_url=req.base_url,
            entity_id=req.entity_id,
            engine=req.engine,
            token=req.token,
        )
    except (ValueError, CredentialUnavailable) as exc:
        raise _target_error(exc) from exc
    return {"profile": profile}


@router.put("/audio/home-assistant/profiles/{profile_id}")
def update_home_assistant_profile(profile_id: str, req: ManagedHAProfileRequest):
    try:
        profile = managed_audio.update_profile(
            profile_id,
            name=req.name,
            base_url=req.base_url,
            entity_id=req.entity_id,
            engine=req.engine,
            token=req.token,
            enabled=req.enabled,
        )
    except (KeyError, ValueError, CredentialUnavailable) as exc:
        raise _target_error(exc) from exc
    return {"profile": profile}


@router.delete("/audio/home-assistant/profiles/{profile_id}")
def delete_home_assistant_profile(profile_id: str):
    try:
        managed_audio.delete_profile(profile_id)
    except (KeyError, ValueError) as exc:
        raise _target_error(exc) from exc
    return {"ok": True, "profile_id": profile_id}


@router.get("/audio/home-assistant/profiles/{profile_id}/entities")
def list_home_assistant_entities(profile_id: str):
    try:
        return {"entities": managed_audio.discover_entities(profile_id)}
    except (KeyError, ValueError, CredentialUnavailable, RuntimeError) as exc:
        raise _target_error(exc) from exc


@router.post("/audio/home-assistant/profiles/{profile_id}/test")
def test_home_assistant_profile(profile_id: str, req: AudioSpeakRequest):
    try:
        result = managed_audio.speak(profile_id, text=req.text, voice=req.voice, rate=req.rate, volume=req.volume)
    except (KeyError, ValueError, CredentialUnavailable, RuntimeError) as exc:
        raise _target_error(exc) from exc
    return {"ok": result.get("status") == "delivered", "profile_id": profile_id, **result}


@router.post("/audio/pairing/challenge")
def create_audio_pairing_challenge(req: PairingChallengeRequest):
    if req.endpoint_type not in {"browser", "computer", "phone", "monitor", "speaker", "fleet"}:
        raise HTTPException(400, "unsupported endpoint_type")
    return pairing.create_challenge(endpoint_id=req.endpoint_id, endpoint_type=req.endpoint_type)


@router.post("/audio/pairing/claim")
def claim_audio_pairing(req: PairingClaimRequest):
    if req.endpoint_type not in {"browser", "computer", "phone", "monitor", "speaker", "fleet"}:
        raise HTTPException(400, "unsupported endpoint_type")
    try:
        token, record = pairing.claim(
            challenge_id=req.challenge_id,
            pairing_code=req.pairing_code,
            endpoint_id=req.endpoint_id,
            endpoint_type=req.endpoint_type,
            capabilities=req.capabilities,
        )
    except (ValueError, KeyError) as exc:
        raise _target_error(exc) from exc
    return {"contract": ENROLLMENT_CONTRACT, "auth_token": token, "credential": record}


@router.post("/audio/pairing/{endpoint_id}/revoke")
def revoke_audio_pairing(endpoint_id: str):
    return {"ok": True, "endpoint_id": endpoint_id, "revoked": pairing.revoke(endpoint_id)}


@router.get("/audio/groups")
def list_audio_groups():
    return {"groups": registry.list_groups()}


@router.post("/audio/groups")
def create_audio_group(req: AudioGroupRequest):
    try:
        group = registry.create_group(req.name, req.endpoint_ids)
    except ValueError as exc:
        raise _target_error(exc) from exc
    return {"group": group}


@router.put("/audio/groups/{group_id}")
def update_audio_group(group_id: str, req: AudioGroupRequest):
    try:
        group = registry.update_group(group_id, req.name, req.endpoint_ids)
    except (KeyError, ValueError) as exc:
        raise _target_error(exc) from exc
    return {"group": group}


@router.delete("/audio/groups/{group_id}")
def delete_audio_group(group_id: str):
    try:
        registry.delete_group(group_id)
    except (KeyError, ValueError) as exc:
        raise _target_error(exc) from exc
    return {"ok": True, "group_id": group_id}


async def _deliver_audio(target_ids: list[str], payload: dict) -> dict:
    message_id = payload.setdefault("message_id", f"audio-{uuid.uuid4().hex}")
    managed_by_id = {endpoint["endpoint_id"]: endpoint for endpoint in managed_audio.endpoints()}
    results = []
    for endpoint_id in target_ids:
        managed_endpoint = managed_by_id.get(endpoint_id)
        if not managed_endpoint:
            results.extend(await registry.deliver([endpoint_id], payload))
            continue
        try:
            if payload.get("type") == "stop":
                adapter_result = await asyncio.to_thread(managed_audio.stop, managed_endpoint["profile_id"])
            else:
                adapter_result = await asyncio.to_thread(
                    managed_audio.speak,
                    managed_endpoint["profile_id"],
                    text=payload["text"],
                    voice=payload.get("voice") or "",
                    rate=payload.get("rate", 1.0),
                    volume=payload.get("volume", 1.0),
                )
            results.append({
                "endpoint_id": endpoint_id,
                "name": managed_endpoint.get("name", endpoint_id),
                **adapter_result,
            })
        except (KeyError, CredentialUnavailable, RuntimeError) as exc:
            results.append({
                "endpoint_id": endpoint_id,
                "name": managed_endpoint.get("name", endpoint_id),
                "status": "failed",
                "error": str(exc)[:300],
            })
    return {
        "ok": any(result["status"] == "delivered" for result in results),
        "message_id": message_id,
        "target_count": len(target_ids),
        "results": results,
    }


@router.post("/audio/speak")
@router.post("/audio/route", include_in_schema=False)
async def speak_audio(req: AudioSpeakRequest):
    """Deliver text to one endpoint, an endpoint list, or a saved room."""
    try:
        target_ids, selected_group_id = registry.resolve_targets(
            endpoint_id=req.endpoint_id,
            group_id=req.group_id,
            endpoint_ids=req.endpoint_ids,
        )
    except (KeyError, ValueError) as exc:
        raise _target_error(exc) from exc

    payload = {
        "type": "speak",
        "text": req.text,
        "source": req.source,
        "created_at": utc_now(),
        "audio_format": "text",
        "voice": req.voice or None,
        "rate": req.rate,
        "volume": req.volume,
        "group_id": selected_group_id,
    }
    return await _deliver_audio(target_ids, payload)


@router.post("/audio/stop")
async def stop_audio(req: AudioStopRequest):
    try:
        target_ids, _ = registry.resolve_targets(
            endpoint_id=req.endpoint_id,
            group_id=req.group_id,
            endpoint_ids=req.endpoint_ids,
        )
    except (KeyError, ValueError) as exc:
        raise _target_error(exc) from exc
    return await _deliver_audio(target_ids, {"type": "stop", "message_id": req.message_id or None, "created_at": utc_now()})


@router.websocket("/audio/ws")
async def audio_endpoint_websocket(websocket: WebSocket):
    """Register a browser endpoint and keep it available for room delivery."""
    await websocket.accept()
    endpoint_id = ""
    try:
        first = await websocket.receive_json()
        if not isinstance(first, dict) or first.get("type") != "register":
            await websocket.send_json({"type": "error", "error": "first message must be register"})
            await websocket.close(code=1008)
            return

        supplied_token = str(first.get("auth_token") or "")
        authenticated = pairing.validate(first.get("endpoint_id", ""), supplied_token)
        if supplied_token and not authenticated:
            await websocket.send_json({"type": "error", "error": "invalid or expired endpoint credential"})
            await websocket.close(code=1008)
            return
        if os.getenv("NPU_STACK_AUDIO_REQUIRE_AUTH", "").strip().lower() in {"1", "true", "yes"} and not authenticated:
            await websocket.send_json({"type": "error", "error": "paired endpoint credential required"})
            await websocket.close(code=1008)
            return

        endpoint = registry.register(first, websocket, authenticated=authenticated)
        endpoint_id = endpoint["endpoint_id"]
        await websocket.send_json({
            "type": "registered",
            "endpoint": endpoint,
            "heartbeat_interval_seconds": registry.heartbeat_timeout_seconds // 3,
        })

        while True:
            message = await websocket.receive_json()
            if not isinstance(message, dict):
                await websocket.send_json({"type": "error", "error": "messages must be JSON objects"})
                continue
            message_type = message.get("type")
            if message_type == "heartbeat":
                try:
                    endpoint = registry.heartbeat(endpoint_id)
                except KeyError:
                    await websocket.send_json({"type": "error", "error": "endpoint is no longer registered"})
                    break
                await websocket.send_json({"type": "heartbeat_ack", "endpoint_id": endpoint["endpoint_id"], "last_seen": endpoint["last_seen"]})
            elif message_type == "playback_ack":
                try:
                    ack = registry.record_playback_ack(endpoint_id, message)
                    await websocket.send_json({"type": "playback_ack_received", "message_id": ack["message_id"], "status": ack["status"]})
                except (KeyError, ValueError) as exc:
                    await websocket.send_json({"type": "error", "error": str(exc)})
            elif message_type in {"unregister", "close"}:
                break
            else:
                await websocket.send_json({"type": "error", "error": f"unsupported message type: {message_type}"})
    except WebSocketDisconnect:
        pass
    finally:
        registry.unregister(endpoint_id, websocket)


@router.get("/say/status")
def say_status():
    """Show HA audio-routing config and what's available."""
    base = _ha_base()
    token = _ha_token()
    engines = []
    if token:
        try:
            r = httpx.get(base + "/api/states", headers={"Authorization": "Bearer " + token}, timeout=10)
            if r.status_code == 200:
                states = r.json()
                engines = sorted({
                    s["entity_id"] for s in states
                    if s["entity_id"].startswith("tts.")
                })
        except Exception:
            pass
    return {
        "ha_base_url": base,
        "configured": bool(token),
        "tts_engines": engines,
        "default_service": "tts.speak",
        "note": "Production TTS is Home Assistant (Piper/Google/Cloud) — ElevenLabs is test-only.",
    }


@router.post("/say")
def say(req: SayRequest):
    """Speak `text` through a Home Assistant TTS engine + media player."""
    token = _ha_token()
    if not token:
        raise HTTPException(400, "HA_TOKEN not configured — set it in .env")
    base = _ha_base()
    payload: dict = {"message": req.text}
    if req.entity_id:
        payload["media_player_entity_id"] = req.entity_id
    service = "tts." + (req.engine or "speak")
    try:
        r = httpx.post(
            base + "/api/services/" + service,
            headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
            json=payload,
            timeout=30,
        )
    except httpx.HTTPError as e:
        raise HTTPException(502, "Home Assistant unreachable: " + str(e))
    if r.status_code >= 400:
        raise HTTPException(r.status_code, "HA error: " + r.text[:300])
    return {
        "ok": True,
        "service": service,
        "text": req.text,
        "entity_id": req.entity_id or "(default)",
        "ha_status": r.status_code,
    }
