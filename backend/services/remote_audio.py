"""Room-wide remote audio endpoint registry.

The first audio fabric speaks text to browser endpoints over WebSocket.  The
browser owns playback (currently Web Speech API), while this service owns
endpoint identity, liveness, room membership, and delivery accounting.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Dict, Iterable, Optional


DEFAULT_HEARTBEAT_TIMEOUT_SECONDS = 45
MAX_GROUPS = 200
MAX_ENDPOINTS_PER_GROUP = 100
MAX_TEXT_LENGTH = 8000


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bounded_text(value: Any, *, field: str, default: str = "", max_length: int = 160) -> str:
    text = str(value or "").strip()
    if not text:
        return default
    if len(text) > max_length:
        raise ValueError(f"{field} must be at most {max_length} characters")
    return text


def _normalise_id(value: Any, *, field: str = "endpoint_id") -> str:
    text = _bounded_text(value, field=field, max_length=120)
    if not text:
        raise ValueError(f"{field} is required")
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:-")
    if any(char not in allowed for char in text):
        raise ValueError(f"{field} contains unsupported characters")
    return text


def _normalise_endpoint_type(value: Any) -> str:
    endpoint_type = _bounded_text(value, field="endpoint_type", default="browser", max_length=32).lower()
    if endpoint_type not in {"browser", "computer", "phone", "monitor", "speaker", "fleet", "home_assistant"}:
        raise ValueError("endpoint_type must be browser, computer, phone, monitor, speaker, fleet, or home_assistant")
    return endpoint_type


def _normalise_capabilities(value: Any) -> list[str]:
    values = value if isinstance(value, (list, tuple, set)) else ["speech"]
    capabilities: list[str] = []
    for item in values:
        capability = _bounded_text(item, field="capability", max_length=40).lower()
        if capability and capability not in capabilities:
            capabilities.append(capability)
    return capabilities[:20] or ["speech"]


def _normalise_metadata(value: Any, *, max_items: int = 20) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, str] = {}
    for key, item in list(value.items())[:max_items]:
        safe_key = _bounded_text(key, field="metadata key", max_length=40)
        safe_value = _bounded_text(item, field=f"metadata[{safe_key}]", max_length=160)
        if safe_key and safe_value:
            result[safe_key] = safe_value
    return result


class RemoteAudioRegistry:
    """Thread-safe endpoint and room registry with async WebSocket delivery."""

    def __init__(self, state_path: str | os.PathLike[str] | None = None, heartbeat_timeout_seconds: int = DEFAULT_HEARTBEAT_TIMEOUT_SECONDS):
        self.state_path = Path(state_path or os.getenv(
            "NPU_STACK_AUDIO_GROUPS_PATH",
            Path(__file__).resolve().parents[1] / "data" / "audio-groups.json",
        ))
        self.heartbeat_timeout_seconds = max(10, int(heartbeat_timeout_seconds))
        self._lock = threading.RLock()
        self._endpoints: dict[str, dict[str, Any]] = {}
        self._connections: dict[str, Any] = {}
        self._groups: dict[str, dict[str, Any]] = {}
        self._load_groups()

    def _load_groups(self) -> None:
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
            groups = payload.get("groups", []) if isinstance(payload, dict) else []
        except (OSError, ValueError, TypeError):
            groups = []
        for raw in groups[:MAX_GROUPS]:
            try:
                group_id = _normalise_id(raw.get("id"), field="group_id")
                name = _bounded_text(raw.get("name"), field="name", default="Room", max_length=100)
                endpoint_ids = self._normalise_endpoint_ids(raw.get("endpoint_ids", []))
            except (AttributeError, ValueError):
                continue
            self._groups[group_id] = {
                "id": group_id,
                "name": name,
                "endpoint_ids": endpoint_ids,
                "created_at": raw.get("created_at") or utc_now(),
                "updated_at": raw.get("updated_at") or utc_now(),
            }

    def _persist_groups(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "groups": list(self._groups.values())}
        temp_path = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temp_path.replace(self.state_path)

    @staticmethod
    def _normalise_endpoint_ids(values: Any) -> list[str]:
        if not isinstance(values, (list, tuple, set)):
            raise ValueError("endpoint_ids must be a list")
        result: list[str] = []
        for value in values:
            endpoint_id = _normalise_id(value)
            if endpoint_id not in result:
                result.append(endpoint_id)
        if len(result) > MAX_ENDPOINTS_PER_GROUP:
            raise ValueError(f"endpoint_ids must contain at most {MAX_ENDPOINTS_PER_GROUP} endpoints")
        return result

    def expire_stale(self) -> list[str]:
        now = datetime.now(timezone.utc).timestamp()
        expired: list[str] = []
        with self._lock:
            for endpoint_id, endpoint in self._endpoints.items():
                last_seen = endpoint.get("last_seen")
                try:
                    age = now - datetime.fromisoformat(str(last_seen)).timestamp()
                except (TypeError, ValueError):
                    age = self.heartbeat_timeout_seconds + 1
                if endpoint.get("online") and age > self.heartbeat_timeout_seconds:
                    endpoint["online"] = False
                    self._connections.pop(endpoint_id, None)
                    expired.append(endpoint_id)
        return expired

    def register(self, payload: dict[str, Any], websocket: Any, *, authenticated: bool = False) -> dict[str, Any]:
        endpoint_id = _normalise_id(payload.get("endpoint_id") or f"browser-{uuid.uuid4().hex}")
        now = utc_now()
        with self._lock:
            previous = self._endpoints.get(endpoint_id, {})
            endpoint = {
                "endpoint_id": endpoint_id,
                "name": _bounded_text(payload.get("name"), field="name", default="Browser Endpoint", max_length=100),
                "endpoint_type": _normalise_endpoint_type(payload.get("endpoint_type")),
                "capabilities": _normalise_capabilities(payload.get("capabilities")),
                "client": _normalise_metadata(payload.get("client")),
                "online": True,
                "paired": bool(authenticated),
                "authenticated": bool(authenticated),
                "connected_at": now,
                "last_seen": now,
                "last_playback": previous.get("last_playback"),
            }
            self._endpoints[endpoint_id] = endpoint
            self._connections[endpoint_id] = websocket
            return dict(endpoint)

    def heartbeat(self, endpoint_id: str) -> dict[str, Any]:
        endpoint_id = _normalise_id(endpoint_id)
        with self._lock:
            endpoint = self._endpoints.get(endpoint_id)
            if not endpoint:
                raise KeyError(endpoint_id)
            endpoint["last_seen"] = utc_now()
            endpoint["online"] = endpoint_id in self._connections
            return dict(endpoint)

    def unregister(self, endpoint_id: str, websocket: Any | None = None) -> None:
        if not endpoint_id:
            return
        with self._lock:
            if websocket is not None and self._connections.get(endpoint_id) is not websocket:
                return
            self._connections.pop(endpoint_id, None)
            if endpoint_id in self._endpoints:
                self._endpoints[endpoint_id]["online"] = False
                self._endpoints[endpoint_id]["last_seen"] = utc_now()

    def record_playback_ack(self, endpoint_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            endpoint = self._endpoints.get(endpoint_id)
            if not endpoint:
                raise KeyError(endpoint_id)
            endpoint["last_seen"] = utc_now()
            endpoint["last_playback"] = {
                "message_id": _bounded_text(payload.get("message_id"), field="message_id", max_length=120),
                "status": _bounded_text(payload.get("status"), field="status", max_length=32),
                "error": _bounded_text(payload.get("error"), field="error", max_length=300),
                "recorded_at": utc_now(),
            }
            return dict(endpoint["last_playback"])

    def list_endpoints(self, *, online: bool | None = None, endpoint_type: str | None = None) -> list[dict[str, Any]]:
        self.expire_stale()
        with self._lock:
            values = list(self._endpoints.values())
        if online is not None:
            values = [endpoint for endpoint in values if endpoint.get("online") is online]
        if endpoint_type:
            values = [endpoint for endpoint in values if endpoint.get("endpoint_type") == endpoint_type]
        return sorted((dict(endpoint) for endpoint in values), key=lambda item: (not item.get("online"), item.get("name", "").lower()))

    def get_group(self, group_id: str) -> dict[str, Any] | None:
        with self._lock:
            group = self._groups.get(group_id)
            return dict(group) if group else None

    def list_groups(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(group) for group in self._groups.values()]

    def create_group(self, name: str, endpoint_ids: Iterable[str]) -> dict[str, Any]:
        safe_name = _bounded_text(name, field="name", max_length=100)
        if not safe_name:
            raise ValueError("name is required")
        ids = self._normalise_endpoint_ids(list(endpoint_ids))
        with self._lock:
            if len(self._groups) >= MAX_GROUPS:
                raise ValueError("maximum number of audio rooms reached")
            now = utc_now()
            group = {"id": f"room-{uuid.uuid4().hex[:12]}", "name": safe_name, "endpoint_ids": ids, "created_at": now, "updated_at": now}
            self._groups[group["id"]] = group
            self._persist_groups()
            return dict(group)

    def update_group(self, group_id: str, name: str, endpoint_ids: Iterable[str]) -> dict[str, Any]:
        group_id = _normalise_id(group_id, field="group_id")
        safe_name = _bounded_text(name, field="name", max_length=100)
        if not safe_name:
            raise ValueError("name is required")
        ids = self._normalise_endpoint_ids(list(endpoint_ids))
        with self._lock:
            if group_id not in self._groups:
                raise KeyError(group_id)
            group = self._groups[group_id]
            group.update({"name": safe_name, "endpoint_ids": ids, "updated_at": utc_now()})
            self._persist_groups()
            return dict(group)

    def delete_group(self, group_id: str) -> None:
        group_id = _normalise_id(group_id, field="group_id")
        with self._lock:
            if group_id not in self._groups:
                raise KeyError(group_id)
            del self._groups[group_id]
            self._persist_groups()

    def resolve_targets(self, *, endpoint_id: str = "", group_id: str = "", endpoint_ids: Iterable[str] = ()) -> tuple[list[str], str | None]:
        requested_endpoint_ids = list(endpoint_ids)
        selectors = [bool(endpoint_id), bool(group_id), bool(requested_endpoint_ids)]
        if sum(selectors) == 0:
            raise ValueError("select at least one endpoint, room, or endpoint list")
        target_ids: list[str] = []
        if endpoint_id:
            target_ids.append(_normalise_id(endpoint_id))
        if requested_endpoint_ids:
            for item in self._normalise_endpoint_ids(requested_endpoint_ids):
                if item not in target_ids:
                    target_ids.append(item)
        if group_id:
            group = self.get_group(_normalise_id(group_id, field="group_id"))
            if not group:
                raise KeyError(group_id)
            for item in group["endpoint_ids"]:
                if item not in target_ids:
                    target_ids.append(item)
        return target_ids, group_id or None

    async def deliver(self, target_ids: Iterable[str], message: dict[str, Any]) -> list[dict[str, Any]]:
        self.expire_stale()
        results: list[dict[str, Any]] = []
        for endpoint_id in target_ids:
            with self._lock:
                endpoint = self._endpoints.get(endpoint_id)
                websocket = self._connections.get(endpoint_id) if endpoint else None
                summary = {"endpoint_id": endpoint_id, "name": endpoint.get("name") if endpoint else endpoint_id}
            if not endpoint or not websocket or not endpoint.get("online"):
                results.append({**summary, "status": "offline"})
                continue
            try:
                await websocket.send_json(message)
                results.append({**summary, "status": "delivered"})
            except Exception as exc:  # noqa: BLE001 - a dead client must not break group delivery
                self.unregister(endpoint_id, websocket)
                results.append({**summary, "status": "failed", "error": str(exc)[:300]})
        return results

    def deliver_sync(self, target_ids: Iterable[str], message: dict[str, Any]) -> list[dict[str, Any]]:
        """Deliver from a synchronous route without nesting ``asyncio.run``.

        Most callers are synchronous FastAPI handlers running in a worker
        thread.  The thread fallback also keeps this helper usable from code
        that happens to already be inside an event loop (for example tests or
        an embedding application).
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.deliver(target_ids, message))

        result: list[list[dict[str, Any]]] = []

        def run_delivery() -> None:
            result.append(asyncio.run(self.deliver(target_ids, message)))

        worker = threading.Thread(target=run_delivery, daemon=True)
        worker.start()
        worker.join()
        return result[0] if result else []


registry = RemoteAudioRegistry()


__all__ = ["MAX_TEXT_LENGTH", "RemoteAudioRegistry", "registry", "utc_now"]
