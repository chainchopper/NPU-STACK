import asyncio
import json
import os
import sys
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import httpx
from cryptography.fernet import Fernet

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from main import app
from routers import agent as agent_router
from routers import nirvana_audio
from services.remote_audio import RemoteAudioRegistry
from services.managed_audio import ManagedAudioStore, PairingManager


class FakeWebSocket:
    def __init__(self, *, fail=False):
        self.messages = []
        self.fail = fail

    async def send_json(self, payload):
        if self.fail:
            raise RuntimeError("client disconnected")
        self.messages.append(payload)


class RemoteAudioRegistryTests(unittest.TestCase):
    def test_registration_heartbeat_delivery_and_stale_expiry(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = RemoteAudioRegistry(Path(temp_dir) / "groups.json", heartbeat_timeout_seconds=10)
            websocket = FakeWebSocket()
            endpoint = registry.register({"endpoint_id": "room-pc", "name": "Room PC"}, websocket)

            self.assertTrue(endpoint["online"])
            self.assertEqual(registry.heartbeat("room-pc")["endpoint_id"], "room-pc")
            result = asyncio.run(registry.deliver(["room-pc"], {"type": "speak", "text": "hello"}))
            self.assertEqual(result[0]["status"], "delivered")
            self.assertEqual(websocket.messages[0]["text"], "hello")

            registry._endpoints["room-pc"]["last_seen"] = (
                datetime.now(timezone.utc) - timedelta(seconds=20)
            ).isoformat()
            self.assertEqual(registry.expire_stale(), ["room-pc"])
            self.assertEqual(registry.list_endpoints(online=True), [])

    def test_group_broadcast_persists_and_generator_targets_are_not_consumed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "groups.json"
            registry = RemoteAudioRegistry(state_path)
            first = FakeWebSocket()
            second = FakeWebSocket()
            registry.register({"endpoint_id": "pc-1", "name": "PC 1"}, first)
            registry.register({"endpoint_id": "phone-1", "name": "Phone"}, second)
            group = registry.create_group("Downstairs", ["pc-1", "phone-1"])

            targets, selected_group = registry.resolve_targets(
                group_id=group["id"], endpoint_ids=(item for item in ["pc-1"])
            )
            self.assertEqual(selected_group, group["id"])
            self.assertEqual(targets, ["pc-1", "phone-1"])
            result = asyncio.run(registry.deliver(targets, {"type": "speak", "text": "broadcast"}))
            self.assertEqual([item["status"] for item in result], ["delivered", "delivered"])

            reloaded = RemoteAudioRegistry(state_path)
            self.assertEqual(reloaded.list_groups()[0]["name"], "Downstairs")
            self.assertEqual(json.loads(state_path.read_text())["version"], 1)

    def test_failed_endpoint_is_marked_offline_without_breaking_delivery(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = RemoteAudioRegistry(Path(temp_dir) / "groups.json")
            failed = FakeWebSocket(fail=True)
            healthy = FakeWebSocket()
            registry.register({"endpoint_id": "bad", "name": "Bad"}, failed)
            registry.register({"endpoint_id": "good", "name": "Good"}, healthy)

            result = asyncio.run(registry.deliver(["bad", "good"], {"type": "speak", "text": "hello"}))
            self.assertEqual([item["status"] for item in result], ["failed", "delivered"])
            endpoints = {item["endpoint_id"]: item for item in registry.list_endpoints()}
            self.assertFalse(endpoints["bad"]["online"])


class NirvanaAudioRouterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app, raise_server_exceptions=False)

    def test_audio_routes_list_groups_and_validate_missing_target(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = RemoteAudioRegistry(Path(temp_dir) / "groups.json")
            with patch.object(nirvana_audio, "registry", registry):
                groups = self.client.get("/api/nirvana/audio/groups")
                self.assertEqual(groups.status_code, 200)
                self.assertEqual(groups.json(), {"groups": []})

                missing = self.client.post("/api/nirvana/audio/speak", json={"text": "hello"})
                self.assertEqual(missing.status_code, 400)

                created = self.client.post(
                    "/api/nirvana/audio/groups",
                    json={"name": "Office", "endpoint_ids": ["room-pc"]},
                )
                self.assertEqual(created.status_code, 200)
                self.assertEqual(created.json()["group"]["name"], "Office")

    def test_audio_websocket_registers_and_accepts_heartbeat_and_ack(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = RemoteAudioRegistry(Path(temp_dir) / "groups.json")
            with patch.object(nirvana_audio, "registry", registry):
                with self.client.websocket_connect("/api/nirvana/audio/ws") as websocket:
                    websocket.send_json({
                        "type": "register",
                        "endpoint_id": "test-browser",
                        "name": "Test Browser",
                        "endpoint_type": "browser",
                    })
                    registered = websocket.receive_json()
                    self.assertEqual(registered["type"], "registered")
                    websocket.send_json({"type": "heartbeat"})
                    self.assertEqual(websocket.receive_json()["type"], "heartbeat_ack")
                    websocket.send_json({
                        "type": "playback_ack",
                        "message_id": "audio-1",
                        "status": "ended",
                    })
                    self.assertEqual(websocket.receive_json()["type"], "playback_ack_received")

    def test_chat_audio_is_opt_in_and_non_fatal(self):
        request = agent_router.ChatRequest(
            messages=[{"role": "user", "content": "say hello"}],
            speak_response=True,
            audio_endpoint_id="room-pc",
        )
        fake_registry = Mock()
        fake_registry.resolve_targets.return_value = (["room-pc"], None)
        fake_registry.deliver_sync.return_value = [{"endpoint_id": "room-pc", "status": "delivered"}]
        with patch("services.remote_audio.registry", fake_registry):
            result = agent_router._deliver_chat_audio(request, "Hello from Nirvana")
        self.assertTrue(result["ok"])
        self.assertEqual(result["target_count"], 1)

        disabled = agent_router.ChatRequest(messages=[], speak_response=False)
        self.assertIsNone(agent_router._deliver_chat_audio(disabled, "ignored"))


class ManagedAudioSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app, raise_server_exceptions=False)

    def test_ha_token_is_encrypted_and_never_returned_in_public_profile(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            token = "super-secret-ha-token"
            store = ManagedAudioStore(Path(temp_dir) / "profiles.json", Fernet.generate_key())
            profile = store.create_profile(
                name="Home",
                base_url="http://homeassistant.local:8123",
                entity_id="media_player.kitchen",
                token=token,
            )
            self.assertNotIn("token", profile)
            self.assertTrue(profile["configured"])
            raw = Path(temp_dir, "profiles.json").read_text(encoding="utf-8")
            self.assertNotIn(token, raw)
            self.assertIn("credential", raw)

    def test_pairing_challenge_is_single_use_and_revocable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = PairingManager(Path(temp_dir) / "pairings.json", challenge_ttl_seconds=300)
            challenge = manager.create_challenge(endpoint_id="fleet-one", endpoint_type="fleet")
            token, record = manager.claim(
                challenge_id=challenge["challenge_id"],
                pairing_code=challenge["pairing_code"],
                endpoint_id="fleet-one",
                endpoint_type="fleet",
            )
            self.assertTrue(manager.validate("fleet-one", token))
            self.assertEqual(record["endpoint_type"], "fleet")
            with self.assertRaises(ValueError):
                manager.claim(
                    challenge_id=challenge["challenge_id"],
                    pairing_code=challenge["pairing_code"],
                    endpoint_id="fleet-one",
                    endpoint_type="fleet",
                )
            self.assertEqual(manager.revoke("fleet-one"), 1)
            self.assertFalse(manager.validate("fleet-one", token))

    def test_pairing_rejects_endpoint_type_mismatch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = PairingManager(Path(temp_dir) / "pairings.json")
            challenge = manager.create_challenge(endpoint_id="browser-one", endpoint_type="browser")
            with self.assertRaisesRegex(ValueError, "endpoint type"):
                manager.claim(
                    challenge_id=challenge["challenge_id"],
                    pairing_code=challenge["pairing_code"],
                    endpoint_id="browser-one",
                    endpoint_type="fleet",
                )

    def test_expired_endpoint_credential_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = PairingManager(Path(temp_dir) / "pairings.json")
            token, record = manager.issue_credential(
                endpoint_id="browser-expired",
                endpoint_type="browser",
                ttl_seconds=60,
            )
            manager._credentials[manager._hash(token)]["expires_at"] = (
                datetime.now(timezone.utc) - timedelta(seconds=1)
            ).isoformat()
            self.assertFalse(manager.validate(record["endpoint_id"], token))

    def test_profile_update_without_token_rotation_keeps_encrypted_credential(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ManagedAudioStore(Path(temp_dir) / "profiles.json", Fernet.generate_key())
            profile = store.create_profile(
                name="Home",
                base_url="http://homeassistant.local:8123",
                token="original-token",
            )
            store.update_profile(
                profile["id"],
                name="Updated Home",
                base_url="http://homeassistant.local:8123",
                token=None,
            )
            self.assertEqual(store._get_raw(profile["id"])["token"], "original-token")

    def test_ha_auth_and_timeout_failures_update_health(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ManagedAudioStore(Path(temp_dir) / "profiles.json", Fernet.generate_key())
            profile = store.create_profile(
                name="Home",
                base_url="http://homeassistant.local:8123",
                token="ha-token-value",
            )
            with patch("services.managed_audio.httpx.request", return_value=Mock(status_code=401)):
                with self.assertRaisesRegex(RuntimeError, "authentication"):
                    store.discover_entities(profile["id"])
            self.assertEqual(store.get_profile(profile["id"])["health"], "auth_error")

            with patch("services.managed_audio.httpx.request", side_effect=httpx.ConnectTimeout("timeout")):
                with self.assertRaisesRegex(RuntimeError, "unreachable"):
                    store.discover_entities(profile["id"])
            self.assertEqual(store.get_profile(profile["id"])["health"], "offline")

    def test_mixed_browser_and_home_assistant_group_routes_independently(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = RemoteAudioRegistry(Path(temp_dir) / "groups.json")
            browser_socket = FakeWebSocket()
            registry.register({"endpoint_id": "browser-one", "name": "Browser"}, browser_socket)
            store = ManagedAudioStore(Path(temp_dir) / "profiles.json", Fernet.generate_key())
            profile = store.create_profile(
                name="Kitchen HA",
                base_url="http://homeassistant.local:8123",
                entity_id="media_player.kitchen",
                token="ha-token-value",
            )
            group = registry.create_group("Mixed Room", ["browser-one", profile["id"]])
            with patch.object(nirvana_audio, "registry", registry), patch.object(nirvana_audio, "managed_audio", store), patch(
                "services.managed_audio.httpx.request", return_value=Mock(status_code=200)
            ):
                response = self.client.post(
                    "/api/nirvana/audio/speak",
                    json={"text": "hello", "group_id": group["id"]},
                )
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual([item["status"] for item in response.json()["results"]], ["delivered", "delivered"])
            self.assertEqual(browser_socket.messages[0]["text"], "hello")

    def test_websocket_rejects_invalid_endpoint_credential(self):
        manager = PairingManager(Path(tempfile.gettempdir()) / "npu-stack-invalid-pairing-test.json")
        with patch.object(nirvana_audio, "pairing", manager):
            with self.client.websocket_connect("/api/nirvana/audio/ws") as websocket:
                websocket.send_json({
                    "type": "register",
                    "endpoint_id": "browser-invalid",
                    "auth_token": "invalid-token",
                })
                self.assertIn("invalid or expired", websocket.receive_json()["error"])

    def test_websocket_requires_paired_credential_when_enabled(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = PairingManager(Path(temp_dir) / "pairings.json")
            with patch.object(nirvana_audio, "pairing", manager), patch.dict(
                os.environ, {"NPU_STACK_AUDIO_REQUIRE_AUTH": "true"}
            ):
                with self.client.websocket_connect("/api/nirvana/audio/ws") as websocket:
                    websocket.send_json({"type": "register", "endpoint_id": "browser-unpaired"})
                    self.assertIn("paired endpoint credential required", websocket.receive_json()["error"])

    def test_managed_ha_endpoint_routes_without_exposing_token(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ManagedAudioStore(Path(temp_dir) / "profiles.json", Fernet.generate_key())
            profile = store.create_profile(
                name="Kitchen HA",
                base_url="http://homeassistant.local:8123",
                entity_id="media_player.kitchen",
                token="ha-token-value",
            )
            response = Mock(status_code=200)
            with patch.object(nirvana_audio, "managed_audio", store), patch(
                "services.managed_audio.httpx.request", return_value=response
            ):
                listed = self.client.get("/api/nirvana/audio/endpoints")
                self.assertEqual(listed.status_code, 200)
                endpoint = next(item for item in listed.json()["endpoints"] if item["profile_id"] == profile["id"])
                self.assertEqual(endpoint["endpoint_type"], "home_assistant")
                self.assertNotIn("token", endpoint)

                delivered = self.client.post(
                    "/api/nirvana/audio/speak",
                    json={"text": "hello", "endpoint_id": profile["id"]},
                )
                self.assertEqual(delivered.status_code, 200)
                self.assertEqual(delivered.json()["results"][0]["status"], "delivered")


class FirmwareEnrollmentTests(unittest.TestCase):
    def test_audio_manifest_is_opt_in_and_contains_no_ha_token(self):
        from services import edge_discovery

        with tempfile.TemporaryDirectory() as temp_dir:
            manager = PairingManager(Path(temp_dir) / "pairings.json")
            with patch.object(edge_discovery, "pairing", manager):
                manifest_info = edge_discovery._write_audio_enrollment_manifest(
                    Path(temp_dir),
                    {"id": "nirvana-board", "board_id": "board-1"},
                    {
                        "include_audio_enrollment": True,
                        "command_center_url": "http://127.0.0.1:8010",
                        "ha_token": "must-never-be-exported",
                    },
                )
            manifest = json.loads(Path(temp_dir, "audio-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest_info["contract"], "nirvana.audio.enrollment/v1")
            self.assertEqual(manifest["endpoint_type"], "fleet")
            self.assertNotIn("ha_token", manifest)
            self.assertNotIn("must-never-be-exported", Path(temp_dir, "audio-manifest.json").read_text())
            archive_path = Path(temp_dir, "bundle.zip")
            edge_discovery._zip_bundle(Path(temp_dir), archive_path)
            with zipfile.ZipFile(archive_path) as archive:
                archived_manifest = archive.read("audio-manifest.json").decode("utf-8")
            self.assertIn('"auth_token"', archived_manifest)
            self.assertNotIn("must-never-be-exported", archived_manifest)
            redacted = edge_discovery._redact_bundle_config({
                "ha_token": "hidden",
                "wifi_password": "hidden",
                "safe_value": "kept",
            })
            self.assertEqual(redacted, {"safe_value": "kept"})
            self.assertIsNone(edge_discovery._write_audio_enrollment_manifest(Path(temp_dir), {}, {}))


if __name__ == "__main__":
    unittest.main()
