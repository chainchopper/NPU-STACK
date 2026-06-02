import os
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
from services.nirvana_service import NirvanaServiceError


class AgentRouterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app, raise_server_exceptions=False)

    def test_agent_chat_returns_fleet_action_for_explicit_fleet_prompt(self):
        with patch.object(agent_router, "parse_command", return_value={
            "command_text": "refresh telemetry for linux-edge-1",
            "intent": "telemetry",
            "target_devices": ["linux-edge-1"],
            "action_params": {"refresh": True, "limit": 20},
            "confidence": 0.92,
            "reasoning_summary": "telemetry prompt",
        }), patch.object(agent_router, "create_command_job", return_value={"job_id": "cmd-agent-test"}), patch.object(
            agent_router,
            "execute_command_job",
        ), patch.object(
            agent_router,
            "get_command_job",
            return_value={
                "job_id": "cmd-agent-test",
                "intent": "telemetry",
                "status": "complete",
                "target_count": 1,
                "results_by_device": {
                    "linux-edge-1": {
                        "status": "success",
                        "transport": "http-agent",
                        "history_count": 3,
                        "latest": {
                            "source": "http-agent-status",
                            "recorded_at": "2026-06-02T00:00:00Z",
                            "telemetry": {"cpu_percent": 11},
                        },
                    }
                },
            },
        ), patch("services.nirvana_service.ensure_webui_running"), patch(
            "services.nirvana_service.create_webui_session",
            return_value={"session_id": "nirvana-session-1"},
        ), patch(
            "services.nirvana_service.send_sync_chat",
            return_value={"answer": "Telemetry reviewed. Proceed with next diagnostics."},
        ), patch(
            "services.nirvana_service.get_bridge_status",
            return_value={
                "webui_running": True,
                "webui_url": "http://127.0.0.1:8789",
                "summary": {
                    "current_model": "phi-3-mini",
                    "current_provider": "openai-compatible",
                    "chat_ready": True,
                    "completed": True,
                },
            },
        ):
            response = self.client.post(
                "/api/agent/chat",
                json={
                    "messages": [{"role": "user", "content": "refresh telemetry for linux-edge-1"}],
                    "profile_id": "orchestration-agent",
                    "session_id": "session-missing-is-ok",
                    "use_fleet_tools": True,
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["fleet_action"]["intent"], "telemetry")
        self.assertEqual(payload["fleet_action"]["job_id"], "cmd-agent-test")
        self.assertIn("Fleet action executed", payload["response"])

    def test_agent_chat_falls_back_to_local_runtime_when_webui_chat_fails(self):
        with patch("services.nirvana_service.ensure_webui_running"), patch(
            "services.nirvana_service.create_webui_session",
            return_value={"session_id": "nirvana-session-1"},
        ), patch(
            "services.nirvana_service.send_sync_chat",
            side_effect=NirvanaServiceError('Nirvana chat HTTP 500: {"error":"Internal server error"}'),
        ), patch(
            "services.nirvana_service.get_bridge_status",
            return_value={
                "webui_running": True,
                "webui_url": "http://127.0.0.1:8789",
                "summary": {
                    "current_model": "phi-3-mini",
                    "current_provider": "auto",
                    "chat_ready": False,
                    "completed": True,
                },
            },
        ), patch.object(
            agent_router,
            "_local_agent_chat",
            return_value={
                "response": "Local fallback handled the request.",
                "nirvana_runtime": {
                    "agent_name": "Nirvana",
                    "engine": "llama-cpp-python",
                    "model_file": "Phi-3-mini-4k-instruct-q4.gguf",
                    "model_loaded": True,
                    "uses_mock_responses": False,
                    "via": "local-gguf-fallback",
                    "runtime_mode": "auto",
                },
            },
        ):
            response = self.client.post(
                "/api/agent/chat",
                json={
                    "messages": [{"role": "user", "content": "run uptime on linux-edge-1"}],
                    "profile_id": "orchestration-agent",
                    "session_id": "session-fallback-test",
                    "use_fleet_tools": False,
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["response"], "Local fallback handled the request.")
        self.assertEqual(payload["nirvana_runtime"]["engine"], "llama-cpp-python")
        self.assertIn("Nirvana chat HTTP 500", payload["nirvana_runtime"]["fallback_errors"][0])

    def test_record_agent_session_turn_persists_assistant_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_state = os.path.join(temp_dir, "orchestration_state.json")
            with patch.object(orchestration_router, "STATE_FILE", temp_state):
                state = orchestration_router._default_state()
                orchestration_router._save_state(state)

                profile = state["agent_profiles"][0]
                session = state["agent_sessions"][0]
                updated = orchestration_router.record_agent_session_turn(
                    session_id=session["id"],
                    profile_id=profile["id"],
                    user_message={"role": "user", "content": "refresh telemetry"},
                    assistant_message={
                        "role": "assistant",
                        "content": "Telemetry refreshed.",
                        "fleet_action": {"intent": "telemetry", "job_id": "cmd-123", "status": "complete"},
                    },
                    runtime_meta={"nirvana_session_id": "nirvana-session-1"},
                )

                self.assertEqual(updated["messages"][-1]["fleet_action"]["job_id"], "cmd-123")

                reloaded = orchestration_router._load_state()
                persisted = next(item for item in reloaded["agent_sessions"] if item["id"] == session["id"])
                self.assertEqual(persisted["messages"][-1]["fleet_action"]["status"], "complete")
                self.assertEqual(persisted["nirvana_session_id"], "nirvana-session-1")


if __name__ == "__main__":
    unittest.main()