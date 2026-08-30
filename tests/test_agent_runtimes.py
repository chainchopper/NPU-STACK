import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from main import app
import routers.agent as agent_router
import routers.orchestration as orchestration_router
import services.agent_runtime_registry as runtime_registry


class AgentRuntimeRegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.registry_path = Path(self.temp_dir.name) / "agent_runtimes.json"
        runtime_registry.reset_registry_for_tests(str(self.registry_path))

    def tearDown(self):
        runtime_registry.reset_registry_for_tests()
        self.temp_dir.cleanup()

    def test_resolution_precedence_and_legacy_modes(self):
        runtime_registry.register_runtime({
            "runtime_id": "openai-compatible:demo",
            "display_name": "Demo Runtime",
            "endpoint": "http://127.0.0.1:9999/v1",
        })

        request_binding = runtime_registry.resolve_runtime_id(
            request_runtime_id="openai-compatible:demo",
            legacy_runtime_mode="local",
        )
        self.assertEqual(request_binding["runtime"]["runtime_id"], "openai-compatible:demo")
        self.assertEqual(request_binding["binding_source"], "request")

        profile_binding = runtime_registry.resolve_runtime_id(
            profile_runtime_id="openai-compatible:demo",
            legacy_runtime_mode="local",
        )
        self.assertEqual(profile_binding["runtime"]["runtime_id"], "openai-compatible:demo")
        self.assertEqual(profile_binding["binding_source"], "profile")

        self.assertEqual(
            runtime_registry.resolve_runtime_id(legacy_runtime_mode="local")["runtime"]["runtime_id"],
            "nirvana-default",
        )
        self.assertEqual(
            runtime_registry.resolve_runtime_id(legacy_runtime_mode="external")["runtime"]["runtime_id"],
            "openai-compatible:legacy-external",
        )

        state = json.loads(self.registry_path.read_text(encoding="utf-8"))
        state["selected_runtime_id"] = "openai-compatible:demo"
        self.registry_path.write_text(json.dumps(state), encoding="utf-8")
        global_binding = runtime_registry.resolve_runtime_id(legacy_runtime_mode="auto")
        self.assertEqual(global_binding["runtime"]["runtime_id"], "openai-compatible:demo")
        self.assertEqual(global_binding["binding_source"], "global")

    def test_registration_redacts_credentials_and_rejects_unsafe_endpoints(self):
        registered = runtime_registry.register_runtime({
            "runtime_id": "openai-compatible:secure",
            "display_name": "Secure Runtime",
            "endpoint": "https://runtime.example.test/v1",
            "credential_env_var": "OPENAI_API_KEY",
        })
        self.assertEqual(registered["configuration"]["credential_source"], "env:OPENAI_API_KEY")
        self.assertNotIn("api_key", registered)

        raw_state = self.registry_path.read_text(encoding="utf-8")
        self.assertNotIn("OPENAI_API_KEY_VALUE", raw_state)

        with self.assertRaises(runtime_registry.RuntimeRegistryError):
            runtime_registry.register_runtime({
                "runtime_id": "openai-compatible:insecure",
                "display_name": "Insecure Remote",
                "endpoint": "http://runtime.example.test/v1",
            })
        with self.assertRaises(runtime_registry.RuntimeRegistryError):
            runtime_registry.register_runtime({
                "runtime_id": "openai-compatible:embedded-secret",
                "display_name": "Embedded Secret",
                "endpoint": "https://user:secret@runtime.example.test/v1",
            })
        with self.assertRaises(runtime_registry.RuntimeRegistryError):
            runtime_registry.register_runtime({
                "runtime_id": "openai-compatible:bad-credential",
                "display_name": "Bad Credential",
                "endpoint": "https://runtime.example.test/v1",
                "credential_env_var": "not-an-env-var",
            })

    def test_legacy_external_runtime_is_discoverable(self):
        orchestration_path = Path(self.temp_dir.name) / "orchestration_state.json"
        with patch.object(orchestration_router, "STATE_FILE", orchestration_path):
            state = orchestration_router._default_state()
            state["hermes"].update({
                "enabled": True,
                "api_base": "https://legacy.example.test/v1",
                "default_model": "legacy-model",
            })
            orchestration_path.write_text(json.dumps(state), encoding="utf-8")
            runtime = runtime_registry.get_runtime("openai-compatible:legacy-external")

        self.assertIsNotNone(runtime)
        self.assertEqual(runtime["adapter"], "openai-compatible")
        self.assertEqual(runtime["models"][0]["id"], "legacy-model")

    def test_api_catalog_registration_and_selection(self):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/agent-runtimes/register",
            json={
                "runtime_id": "openai-compatible:api-test",
                "display_name": "API Test Runtime",
                "endpoint": "http://127.0.0.1:9998/v1",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["runtime_id"], "openai-compatible:api-test")

        selection = client.put(
            "/api/agent-runtimes/selection",
            json={"runtime_id": "openai-compatible:api-test"},
        )
        self.assertEqual(selection.status_code, 200, selection.text)
        self.assertEqual(selection.json()["selected_runtime_id"], "openai-compatible:api-test")

        catalog = client.get("/api/agent-runtimes")
        self.assertEqual(catalog.status_code, 200, catalog.text)
        self.assertEqual(catalog.json()["selected_runtime_id"], "openai-compatible:api-test")


class AgentRuntimeRouterIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app, raise_server_exceptions=False)

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.registry_path = Path(self.temp_dir.name) / "agent_runtimes.json"
        runtime_registry.reset_registry_for_tests(str(self.registry_path))
        runtime_registry.register_runtime({
            "runtime_id": "openai-compatible:chat-test",
            "display_name": "Chat Test Runtime",
            "endpoint": "http://127.0.0.1:9997/v1",
        })

    def tearDown(self):
        runtime_registry.reset_registry_for_tests()
        self.temp_dir.cleanup()

    def test_unknown_explicit_runtime_request_returns_bad_request(self):
        response = self.client.post(
            "/api/agent/chat",
            json={
                "runtime_id": "openai-compatible:missing",
                "messages": [{"role": "user", "content": "hello"}],
            },
        )
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("Requested runtime was not found", response.text)

    def test_selected_runtime_failure_returns_bad_gateway_without_nirvana_fallback(self):
        with patch.object(
            agent_router,
            "_selected_runtime_api_chat",
            side_effect=RuntimeError("provider unavailable"),
        ), patch.object(
            agent_router,
            "_upstream_bridge_chat_with_recovery",
            side_effect=AssertionError("selected runtime must not invoke Nirvana"),
        ):
            response = self.client.post(
                "/api/agent/chat",
                json={
                    "runtime_id": "openai-compatible:chat-test",
                    "messages": [{"role": "user", "content": "hello"}],
                },
            )

        self.assertEqual(response.status_code, 502, response.text)
        self.assertIn("Selected runtime openai-compatible:chat-test failed", response.text)

    def test_profile_runtime_validation_rejects_unknown_runtime(self):
        orchestration_path = Path(self.temp_dir.name) / "orchestration_state.json"
        with patch.object(orchestration_router, "STATE_FILE", orchestration_path):
            orchestration_path.write_text(
                json.dumps(orchestration_router._default_state()),
                encoding="utf-8",
            )
            response = self.client.post(
                "/api/orchestration/agent-profiles",
                json={
                    "name": "Invalid Runtime Profile",
                    "runtime_id": "openai-compatible:missing",
                },
            )

        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("Unknown agent runtime", response.text)


if __name__ == "__main__":
    unittest.main()
