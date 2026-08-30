"""Managed Home Assistant audio profiles and endpoint enrollment.

This module deliberately separates public endpoint metadata from credentials.
HA tokens are encrypted at rest when ``NPU_STACK_AUDIO_ENCRYPTION_KEY`` is a
valid Fernet key. Pairing records persist only SHA-256 hashes of credentials.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from cryptography.fernet import Fernet, InvalidToken

from services.remote_audio import _bounded_text, _normalise_capabilities, _normalise_endpoint_type, _normalise_id, utc_now


BACKEND_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DEFAULT_PROFILES_PATH = BACKEND_DATA_DIR / "audio-profiles.json"
DEFAULT_PAIRINGS_PATH = BACKEND_DATA_DIR / "audio-pairings.json"
ENROLLMENT_CONTRACT = "nirvana.audio.enrollment/v1"


class CredentialUnavailable(RuntimeError):
    """Raised when encrypted credentials cannot be decrypted safely."""


class ManagedAudioStore:
    """Thread-safe encrypted store for managed Home Assistant profiles."""

    def __init__(self, state_path: str | os.PathLike[str] | None = None, encryption_key: str | bytes | None = None):
        self.state_path = Path(state_path or os.getenv("NPU_STACK_AUDIO_PROFILES_PATH", DEFAULT_PROFILES_PATH))
        self._provided_key = encryption_key
        self._lock = threading.RLock()
        self._profiles: dict[str, dict[str, Any]] = {}
        self._load()

    def _key(self) -> bytes:
        raw = self._provided_key
        if raw is None:
            raw = os.getenv("NPU_STACK_AUDIO_ENCRYPTION_KEY", "")
        if isinstance(raw, str):
            raw = raw.encode("ascii", errors="ignore")
        if not raw:
            raise CredentialUnavailable(
                "NPU_STACK_AUDIO_ENCRYPTION_KEY is required for managed Home Assistant credentials"
            )
        try:
            Fernet(raw)
        except (ValueError, TypeError) as exc:
            raise CredentialUnavailable("NPU_STACK_AUDIO_ENCRYPTION_KEY must be a valid Fernet key") from exc
        return raw

    def _cipher(self) -> Fernet:
        return Fernet(self._key())

    def _load(self) -> None:
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
            profiles = payload.get("profiles", []) if isinstance(payload, dict) else []
        except (OSError, ValueError, TypeError):
            profiles = []
        for raw in profiles[:200]:
            if not isinstance(raw, dict):
                continue
            try:
                profile_id = _normalise_id(raw.get("id"), field="profile_id")
                name = _bounded_text(raw.get("name"), field="name", max_length=100)
                base_url = self._validate_base_url(raw.get("base_url"))
            except (ValueError, TypeError):
                continue
            self._profiles[profile_id] = {
                "id": profile_id,
                "name": name,
                "base_url": base_url,
                "entity_id": _bounded_text(raw.get("entity_id"), field="entity_id", max_length=160),
                "engine": _bounded_text(raw.get("engine"), field="engine", default="speak", max_length=80),
                "enabled": bool(raw.get("enabled", True)),
                "health": raw.get("health") if raw.get("health") in {"unknown", "online", "offline", "auth_error"} else "unknown",
                "created_at": raw.get("created_at") or utc_now(),
                "updated_at": raw.get("updated_at") or utc_now(),
                "credential": raw.get("credential", ""),
            }

    @staticmethod
    def _validate_base_url(value: Any) -> str:
        base_url = _bounded_text(value, field="base_url", max_length=300).rstrip("/")
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("base_url must be an http(s) URL without credentials or query parameters")
        return base_url

    def _persist(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        public_profiles = list(self._profiles.values())
        payload = {"version": 1, "profiles": public_profiles}
        temp_path = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temp_path.replace(self.state_path)

    @staticmethod
    def _public(profile: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": profile["id"],
            "name": profile["name"],
            "base_url": profile["base_url"],
            "entity_id": profile.get("entity_id", ""),
            "engine": profile.get("engine", "speak"),
            "enabled": profile.get("enabled", True),
            "health": profile.get("health", "unknown"),
            "configured": bool(profile.get("credential")),
            "created_at": profile.get("created_at"),
            "updated_at": profile.get("updated_at"),
        }

    def list_profiles(self) -> list[dict[str, Any]]:
        with self._lock:
            return [self._public(profile) for profile in self._profiles.values()]

    def get_profile(self, profile_id: str) -> dict[str, Any] | None:
        profile_id = _normalise_id(profile_id, field="profile_id")
        with self._lock:
            profile = self._profiles.get(profile_id)
            return self._public(profile) if profile else None

    def _get_raw(self, profile_id: str) -> dict[str, Any]:
        profile_id = _normalise_id(profile_id, field="profile_id")
        profile = self._profiles.get(profile_id)
        if not profile:
            raise KeyError(profile_id)
        if not profile.get("credential"):
            raise CredentialUnavailable(f"No credential is configured for Home Assistant profile '{profile_id}'")
        try:
            token = self._cipher().decrypt(profile["credential"].encode()).decode()
        except (InvalidToken, UnicodeDecodeError, ValueError, TypeError) as exc:
            raise CredentialUnavailable(f"Credential for Home Assistant profile '{profile_id}' is unavailable") from exc
        return {**profile, "token": token}

    def _upsert(self, profile_id: str, *, name: str, base_url: str, entity_id: str, engine: str, token: str | None, enabled: bool = True) -> dict[str, Any]:
        safe_name = _bounded_text(name, field="name", max_length=100)
        if not safe_name:
            raise ValueError("name is required")
        safe_base = self._validate_base_url(base_url)
        safe_entity = _bounded_text(entity_id, field="entity_id", max_length=160)
        if safe_entity and not safe_entity.startswith("media_player."):
            raise ValueError("entity_id must be a media_player entity")
        safe_engine = _bounded_text(engine, field="engine", default="speak", max_length=80)
        if not safe_engine.replace("_", "").replace(".", "").isalnum():
            raise ValueError("engine contains unsupported characters")
        with self._lock:
            existing = self._profiles.get(profile_id)
            encrypted = existing.get("credential", "") if existing else ""
            if token is not None:
                if not token.strip():
                    raise ValueError("token cannot be empty when supplied")
                encrypted = self._cipher().encrypt(token.strip().encode()).decode()
            elif not encrypted:
                raise CredentialUnavailable("A Home Assistant token is required")
            now = utc_now()
            profile = {
                "id": profile_id,
                "name": safe_name,
                "base_url": safe_base,
                "entity_id": safe_entity,
                "engine": safe_engine,
                "enabled": enabled,
                "health": existing.get("health", "unknown") if existing else "unknown",
                "created_at": existing.get("created_at", now) if existing else now,
                "updated_at": now,
                "credential": encrypted,
            }
            self._profiles[profile_id] = profile
            self._persist()
            return self._public(profile)

    def create_profile(self, *, name: str, base_url: str, entity_id: str = "", engine: str = "speak", token: str) -> dict[str, Any]:
        profile_id = f"ha-{uuid.uuid4().hex[:16]}"
        return self._upsert(profile_id, name=name, base_url=base_url, entity_id=entity_id, engine=engine, token=token)

    def update_profile(self, profile_id: str, *, name: str, base_url: str, entity_id: str = "", engine: str = "speak", token: str | None = None, enabled: bool = True) -> dict[str, Any]:
        return self._upsert(_normalise_id(profile_id, field="profile_id"), name=name, base_url=base_url, entity_id=entity_id, engine=engine, token=token, enabled=enabled)

    def delete_profile(self, profile_id: str) -> None:
        profile_id = _normalise_id(profile_id, field="profile_id")
        with self._lock:
            if profile_id not in self._profiles:
                raise KeyError(profile_id)
            del self._profiles[profile_id]
            self._persist()

    def set_health(self, profile_id: str, health: str) -> None:
        if health not in {"unknown", "online", "offline", "auth_error"}:
            return
        with self._lock:
            if profile_id in self._profiles:
                self._profiles[profile_id]["health"] = health
                self._profiles[profile_id]["updated_at"] = utc_now()
                self._persist()

    def endpoints(self) -> list[dict[str, Any]]:
        with self._lock:
            profiles = [self._public(profile) for profile in self._profiles.values() if profile.get("enabled", True)]
        return [
            {
                "endpoint_id": profile["id"],
                "name": f"{profile['name']}" + (f" · {profile['entity_id']}" if profile.get("entity_id") else ""),
                "endpoint_type": "home_assistant",
                "capabilities": ["speech", "tts", "stop"],
                "client": {"adapter": "home_assistant", "engine": profile.get("engine", "speak")},
                "online": profile.get("health") == "online",
                "health": profile.get("health", "unknown"),
                "profile_id": profile["id"],
                "entity_id": profile.get("entity_id", ""),
                "configured": profile.get("configured", False),
                "last_seen": profile.get("updated_at"),
            }
            for profile in profiles
        ]

    def _request(self, method: str, profile_id: str, path: str, *, payload: dict | None = None, timeout: float = 15) -> httpx.Response:
        profile = self._get_raw(profile_id)
        url = profile["base_url"] + path
        headers = {"Authorization": f"Bearer {profile['token']}", "Content-Type": "application/json"}
        try:
            response = httpx.request(method, url, headers=headers, json=payload, timeout=timeout)
        except httpx.HTTPError as exc:
            self.set_health(profile_id, "offline")
            raise RuntimeError("Home Assistant is unreachable") from exc
        if response.status_code in {401, 403}:
            self.set_health(profile_id, "auth_error")
            raise RuntimeError("Home Assistant authentication failed")
        if response.status_code >= 400:
            self.set_health(profile_id, "offline")
            raise RuntimeError(f"Home Assistant returned HTTP {response.status_code}")
        self.set_health(profile_id, "online")
        return response

    def discover_entities(self, profile_id: str) -> list[dict[str, str]]:
        response = self._request("GET", profile_id, "/api/states")
        try:
            states = response.json()
        except ValueError as exc:
            raise RuntimeError("Home Assistant returned invalid state data") from exc
        entities = []
        for state in states if isinstance(states, list) else []:
            if not isinstance(state, dict) or not str(state.get("entity_id", "")).startswith("media_player."):
                continue
            attributes = state.get("attributes") if isinstance(state.get("attributes"), dict) else {}
            entities.append({
                "entity_id": str(state["entity_id"]),
                "name": str(attributes.get("friendly_name") or state["entity_id"]),
            })
        return sorted(entities, key=lambda item: item["name"].lower())

    def speak(self, profile_id: str, *, text: str, voice: str = "", rate: float = 1.0, volume: float = 1.0) -> dict[str, Any]:
        profile = self._get_raw(profile_id)
        payload: dict[str, Any] = {"message": text}
        entity_id = profile.get("entity_id")
        if entity_id:
            payload["media_player_entity_id"] = entity_id
        if voice:
            payload["options"] = {"voice": voice}
        response = self._request("POST", profile_id, f"/api/services/tts.{profile.get('engine', 'speak')}", payload=payload, timeout=30)
        return {"status": "delivered", "ha_status": response.status_code, "entity_id": entity_id or "(default)"}

    def stop(self, profile_id: str) -> dict[str, Any]:
        profile = self._get_raw(profile_id)
        entity_id = profile.get("entity_id")
        if not entity_id:
            return {"status": "unsupported", "error": "Home Assistant stop requires a media_player entity"}
        response = self._request("POST", profile_id, "/api/services/media_player/media_stop", payload={"entity_id": entity_id})
        return {"status": "delivered", "ha_status": response.status_code, "entity_id": entity_id}


class PairingManager:
    """Persistent hash-only endpoint credential and one-time challenge manager."""

    def __init__(self, state_path: str | os.PathLike[str] | None = None, challenge_ttl_seconds: int = 300):
        self.state_path = Path(state_path or os.getenv("NPU_STACK_AUDIO_PAIRINGS_PATH", DEFAULT_PAIRINGS_PATH))
        self.challenge_ttl_seconds = max(60, int(challenge_ttl_seconds))
        self._lock = threading.RLock()
        self._credentials: dict[str, dict[str, Any]] = {}
        self._challenges: dict[str, dict[str, Any]] = {}
        self._load()

    @staticmethod
    def _hash(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _load(self) -> None:
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
            credentials = payload.get("credentials", []) if isinstance(payload, dict) else []
        except (OSError, ValueError, TypeError):
            credentials = []
        for record in credentials[:1000]:
            if isinstance(record, dict) and record.get("token_hash") and record.get("endpoint_id"):
                self._credentials[record["token_hash"]] = dict(record)

    def _persist(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "credentials": list(self._credentials.values())}
        temp_path = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temp_path.replace(self.state_path)

    def create_challenge(self, *, endpoint_id: str = "", endpoint_type: str = "browser") -> dict[str, Any]:
        challenge_id = f"pair-{uuid.uuid4().hex}"
        code = f"{secrets.randbelow(1000000):06d}"
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=self.challenge_ttl_seconds)).isoformat()
        normalized_endpoint_id = _normalise_id(endpoint_id) if endpoint_id else ""
        normalized_endpoint_type = _normalise_endpoint_type(endpoint_type)
        with self._lock:
            self._challenges[challenge_id] = {
                "code_hash": self._hash(code),
                "endpoint_id": normalized_endpoint_id,
                "endpoint_type": normalized_endpoint_type,
                "expires_at": expires_at,
                "used": False,
            }
        return {"challenge_id": challenge_id, "pairing_code": code, "expires_at": expires_at, "endpoint_id": normalized_endpoint_id, "endpoint_type": normalized_endpoint_type}

    def issue_credential(self, *, endpoint_id: str, endpoint_type: str, capabilities: list[str] | None = None, ttl_seconds: int = 30 * 24 * 3600) -> tuple[str, dict[str, Any]]:
        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        normalized_endpoint_id = _normalise_id(endpoint_id)
        normalized_endpoint_type = _normalise_endpoint_type(endpoint_type)
        record = {
            "endpoint_id": normalized_endpoint_id,
            "endpoint_type": normalized_endpoint_type,
            "capabilities": _normalise_capabilities(capabilities),
            "token_hash": self._hash(token),
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(seconds=max(60, ttl_seconds))).isoformat(),
            "revoked": False,
        }
        with self._lock:
            self._credentials[record["token_hash"]] = record
            self._persist()
        return token, {key: value for key, value in record.items() if key != "token_hash"}

    def claim(self, *, challenge_id: str, pairing_code: str, endpoint_id: str, endpoint_type: str, capabilities: list[str] | None = None) -> tuple[str, dict[str, Any]]:
        normalized_endpoint_id = _normalise_id(endpoint_id)
        normalized_endpoint_type = _normalise_endpoint_type(endpoint_type)
        with self._lock:
            challenge = self._challenges.get(challenge_id)
            if not challenge or challenge.get("used"):
                raise ValueError("pairing challenge is invalid or already used")
            try:
                expired = datetime.fromisoformat(challenge["expires_at"]).timestamp() <= datetime.now(timezone.utc).timestamp()
            except (KeyError, ValueError, TypeError):
                expired = True
            if expired or not secrets.compare_digest(challenge["code_hash"], self._hash(pairing_code)):
                raise ValueError("pairing code is invalid or expired")
            if challenge.get("endpoint_id") and challenge["endpoint_id"] != normalized_endpoint_id:
                raise ValueError("endpoint does not match pairing challenge")
            if challenge.get("endpoint_type") != normalized_endpoint_type:
                raise ValueError("endpoint type does not match pairing challenge")
            challenge["used"] = True
        return self.issue_credential(endpoint_id=normalized_endpoint_id, endpoint_type=normalized_endpoint_type, capabilities=capabilities)

    def validate(self, endpoint_id: str, token: str) -> bool:
        if not token:
            return False
        with self._lock:
            record = self._credentials.get(self._hash(token))
            if not record or record.get("revoked") or record.get("endpoint_id") != endpoint_id:
                return False
            try:
                if datetime.fromisoformat(record["expires_at"]).timestamp() <= datetime.now(timezone.utc).timestamp():
                    return False
            except (KeyError, ValueError, TypeError):
                return False
            return True

    def revoke(self, endpoint_id: str) -> int:
        changed = 0
        with self._lock:
            for record in self._credentials.values():
                if record.get("endpoint_id") == endpoint_id and not record.get("revoked"):
                    record["revoked"] = True
                    changed += 1
            if changed:
                self._persist()
        return changed


managed_audio = ManagedAudioStore()
pairing = PairingManager()


__all__ = [
    "CredentialUnavailable",
    "ENROLLMENT_CONTRACT",
    "ManagedAudioStore",
    "PairingManager",
    "managed_audio",
    "pairing",
]
