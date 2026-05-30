import unittest
from unittest.mock import patch
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import services.fleet_orchestrator as orchestrator
from main import app


class FleetOrchestratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app, raise_server_exceptions=False)
        cls.auth_headers = {}
        if orchestrator.AGENT_SHARED_SECRET:
            cls.auth_headers["X-NPU-Agent-Secret"] = orchestrator.AGENT_SHARED_SECRET

    def setUp(self):
        orchestrator._command_history.clear()
        orchestrator._command_jobs.clear()
        orchestrator._pending_agent_jobs.clear()

    def test_parse_command_matches_firmware_template(self):
        registry = {
            "devices": {
                "usb-COM15": {
                    "id": "usb-COM15",
                    "family": "esp32",
                    "chip": "ESP32-D0WD-V3",
                    "status": "detected",
                    "paired": True,
                }
            }
        }
        registry_view = {
            "devices": [
                {
                    "id": "usb-COM15",
                    "family": "esp32",
                    "chip": "ESP32-D0WD-V3",
                    "status": "detected",
                    "paired": True,
                    "available": True,
                    "connection": "usb",
                    "agent_installed": False,
                }
            ],
            "count": 1,
            "paired_count": 1,
            "available_count": 1,
        }

        with patch.object(orchestrator, "load_registry", return_value=registry), patch.object(
            orchestrator,
            "list_registry_devices",
            return_value=registry_view,
        ):
            parsed = orchestrator.parse_command(
                "backup flash verify the esp32 using firmware.bin",
                use_agent=False,
            )

        self.assertEqual(parsed["intent"], "firmware")
        self.assertEqual(parsed["template_id"], "backup-flash-verify")
        self.assertIn("usb-COM15", parsed["target_devices"])
        self.assertTrue(parsed["action_params"]["backup_before_update"])
        self.assertTrue(parsed["action_params"]["verify_after_flash"])
        self.assertEqual(parsed["action_params"]["firmware_path"], "firmware.bin")

    def test_execute_shell_job_prefers_http_agent(self):
        parsed = {
            "command_text": "run uptime on edge-1",
            "intent": "shell",
            "target_devices": ["edge-1"],
            "action_params": {"shell_command": "uptime", "timeout_seconds": 10},
            "confidence": 0.9,
            "alternatives": [],
            "tool_context": {"source": "test"},
        }
        device = {
            "id": "edge-1",
            "transport_preference": "http-agent",
            "agent_endpoint": "http://10.0.0.5:9200",
            "status": "online",
        }

        with patch.object(orchestrator, "get_device_from_registry", return_value=device), patch.object(
            orchestrator,
            "_http_request",
            return_value={"returncode": 0, "stdout": "up 1 day", "stderr": ""},
        ):
            job = orchestrator.create_command_job(parsed)
            orchestrator.execute_command_job(job["job_id"], parsed, dry_run=False)
            stored = orchestrator.get_command_job(job["job_id"])

        result = stored["results_by_device"]["edge-1"]
        self.assertEqual(stored["status"], "complete")
        self.assertEqual(result["transport"], "http-agent")
        self.assertEqual(result["status"], "success")
        self.assertIn("up 1 day", result["stdout"])

    def test_mobile_agent_register_claim_and_report(self):
        register_response = self.client.post(
            "/api/fleet/agent/register",
            json={
                "device_id": "linux-edge-1",
                "device_name": "linux-edge-1",
                "family": "rockchip",
                "chip": "RK3588",
                "ip": "192.168.1.55",
                "agent_port": 9200,
                "agent_transport": "polling",
                "transport_preference": "agent-poll",
            },
            headers=self.auth_headers,
        )
        self.assertEqual(register_response.status_code, 200, register_response.text)

        parsed = {
            "command_text": "deploy training job",
            "intent": "shell",
            "target_devices": ["linux-edge-1"],
            "action_params": {"shell_command": "python3 worker.py"},
            "confidence": 0.9,
            "alternatives": [],
            "tool_context": {"source": "test"},
        }
        job = orchestrator.create_command_job(parsed)
        orchestrator.execute_command_job(job["job_id"], parsed, dry_run=False)

        claim_response = self.client.get(
            "/api/fleet/agent/jobs/claim",
            params={"device_id": "linux-edge-1"},
            headers=self.auth_headers,
        )
        self.assertEqual(claim_response.status_code, 200, claim_response.text)
        claim_payload = claim_response.json()
        self.assertEqual(claim_payload["status"], "job")
        self.assertEqual(claim_payload["job"]["job_id"], job["job_id"])

        report_response = self.client.post(
            f"/api/fleet/agent/jobs/{job['job_id']}/result",
            params={"device_id": "linux-edge-1"},
            json={
                "status": "success",
                "stdout": "worker started",
                "stderr": "",
                "exit_code": 0,
                "transport": "agent-poll",
            },
            headers=self.auth_headers,
        )
        self.assertEqual(report_response.status_code, 200, report_response.text)
        reported_job = report_response.json()
        self.assertEqual(reported_job["status"], "complete")
        self.assertEqual(reported_job["results_by_device"]["linux-edge-1"]["stdout"], "worker started")


if __name__ == "__main__":
    unittest.main()
