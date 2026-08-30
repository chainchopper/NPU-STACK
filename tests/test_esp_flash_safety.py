import tempfile
import unittest
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

# The router uses the backend package directory for its service imports.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from backend.routers import esp_router
from backend.routers import devices as devices_router
import routers.devices as devices_api
from main import app
import services.edge_discovery as edge_discovery
import services.fleet_orchestrator as fleet_orchestrator
import services.flash_service as flash_service
import services.idf_service as idf_service


class EspFlashSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app, raise_server_exceptions=False)

    def make_firmware(self, directory):
        firmware = Path(directory) / "firmware.bin"
        firmware.write_bytes(b"test firmware")
        return str(firmware)

    def test_flash_blocks_unsuccessful_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            firmware = self.make_firmware(directory)
            with patch.object(esp_router, "HAS_PYSERIAL", True), \
                    patch.object(esp_router, "backup_firmware", return_value={"success": False, "error": "read failed"}), \
                    patch.object(esp_router.subprocess, "run") as run:
                with self.assertRaises(HTTPException) as raised:
                    esp_router.flash_firmware("COM7", firmware)

            self.assertEqual(raised.exception.status_code, 412)
            self.assertIn("flash blocked", raised.exception.detail)
            run.assert_not_called()

    def test_flash_blocks_incomplete_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            firmware = self.make_firmware(directory)
            backup = Path(directory) / "backup.bin"
            backup.write_bytes(b"incomplete")
            backup_result = {"success": True, "backup_path": str(backup)}

            with patch.object(esp_router, "HAS_PYSERIAL", True), \
                    patch.object(esp_router, "backup_firmware", return_value=backup_result), \
                    patch.object(esp_router.subprocess, "run") as run:
                with self.assertRaises(HTTPException) as raised:
                    esp_router.flash_firmware("COM7", firmware)

            self.assertEqual(raised.exception.status_code, 412)
            self.assertIn("flash blocked", raised.exception.detail)
            run.assert_not_called()

    def test_flash_requires_backup_exception_to_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            firmware = self.make_firmware(directory)
            with patch.object(esp_router, "HAS_PYSERIAL", True), \
                    patch.object(esp_router, "backup_firmware", side_effect=RuntimeError("device disconnected")), \
                    patch.object(esp_router.subprocess, "run") as run:
                with self.assertRaises(HTTPException) as raised:
                    esp_router.flash_firmware("COM7", firmware)

            self.assertEqual(raised.exception.status_code, 412)
            self.assertIn("device disconnected", raised.exception.detail)
            run.assert_not_called()

    def test_flash_writes_only_after_complete_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            firmware = self.make_firmware(directory)
            backup = Path(directory) / "backup.bin"
            backup.write_bytes(b"0")
            with backup.open("ab") as stream:
                stream.truncate(8 * 1024 * 1024)

            events = []

            def backup_side_effect(device):
                events.append("backup")
                return {"success": True, "backup_path": str(backup)}

            def run_side_effect(*args, **kwargs):
                events.append("flash")
                return SimpleNamespace(returncode=0, stdout="written", stderr="")

            with patch.object(esp_router, "HAS_PYSERIAL", True), \
                    patch.object(esp_router, "backup_firmware", side_effect=backup_side_effect), \
                    patch.object(esp_router, "get_esptool_cmd", return_value=["esptool"]), \
                    patch.object(esp_router.subprocess, "run", side_effect=run_side_effect) as run:
                result = esp_router.flash_firmware("COM7", firmware)

            self.assertTrue(result["success"])
            self.assertEqual(events, ["backup", "flash"])
            self.assertEqual(run.call_count, 1)

    def test_flash_size_parser_handles_xiao_full_flash(self):
        self.assertEqual(esp_router._flash_size_bytes("8MB"), 8 * 1024 * 1024)
        self.assertEqual(esp_router._flash_size_bytes("0x800000"), 8 * 1024 * 1024)

    def test_router_backup_rejects_partial_flash_size(self):
        with self.assertRaises(HTTPException) as raised:
            esp_router.backup_firmware("COM7", "4MB")

        self.assertEqual(raised.exception.status_code, 422)

    def test_devices_backup_rejects_partial_flash_size(self):
        request = devices_router.ESPBackupRequest(port="COM7", flash_size_mb=4)
        with self.assertRaises(HTTPException) as raised:
            devices_router.backup_esp_firmware(request)

        self.assertEqual(raised.exception.status_code, 422)

    def test_devices_backup_endpoint_surfaces_protected_failure(self):
        with patch.object(devices_api, "esp_backup_firmware", return_value={"status": "failed", "error": "read failed"}):
            response = self.client.post(
                "/api/devices/esp/backup",
                json={"port": "COM7", "flash_size_mb": 8},
            )

        self.assertEqual(response.status_code, 412, response.text)

    def test_device_backup_endpoint_rejects_partial_flash_size(self):
        response = self.client.post(
            "/api/devices/esp/backup",
            json={"port": "COM7"},
        )

        self.assertEqual(response.status_code, 412, response.text)

    def test_devices_flash_endpoint_surfaces_protected_failure(self):
        with patch.object(devices_api, "esp_flash_firmware", return_value={"status": "failed", "backup": {"status": "failed"}, "error": "backup failed"}):
            response = self.client.post(
                "/api/devices/esp/flash",
                json={"port": "COM7", "firmware_path": "firmware.bin"},
            )

        self.assertEqual(response.status_code, 412, response.text)

    def test_edge_flash_validates_backup_before_write(self):
        events = []

        class FakeEsptool:
            @staticmethod
            def main(command):
                events.append("flash")

        backup = {
            "status": "success",
            "size_bytes": 8 * 1024 * 1024,
            "file": "backup.bin",
        }
        with tempfile.TemporaryDirectory() as directory:
            firmware = self.make_firmware(directory)
            with patch.object(edge_discovery, "esp_backup_firmware", side_effect=lambda *args, **kwargs: events.append("backup") or backup), \
                    patch.dict(sys.modules, {"esptool": FakeEsptool}):
                result = edge_discovery.esp_flash_firmware("COM7", firmware)

        self.assertEqual(result["status"], "success")
        self.assertEqual(events, ["backup", "flash"])

    def test_edge_backup_rejects_non_full_request(self):
        result = edge_discovery.esp_backup_firmware("COM7", flash_size_mb=4)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["required_size_mb"], 8)

    def test_fleet_workflow_cannot_disable_esp_backup(self):
        failed_backup = {"success": False, "error": "read failed"}
        with patch.object(flash_service, "detect_current_firmware", return_value={"detected": True}), \
                patch.object(flash_service, "backup_before_flash", return_value=failed_backup) as backup, \
                patch.object(flash_service, "prepare_bundle") as prepare, \
                patch.object(flash_service, "flash_esptool") as flash:
            result = flash_service.firmware_flash_workflow(
                "xiao", port="COM7", profile_id="micropython-esp32", backup_first=False,
            )

        self.assertFalse(result["success"])
        backup.assert_called_once_with("xiao", "COM7", 8)
        prepare.assert_not_called()
        flash.assert_not_called()

    def test_legacy_backup_rejects_partial_size(self):
        result = flash_service.backup_before_flash("xiao", "COM7", 4)
        self.assertFalse(result["success"])
        self.assertEqual(result["required_size_mb"], 8)

    def test_legacy_backup_blocks_write_when_image_is_incomplete(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(flash_service, "DATA_DIR", Path(directory)), patch.object(
                    flash_service.subprocess,
                    "run",
                    return_value=SimpleNamespace(returncode=0, stdout="", stderr=""),
            ) as run:
                result = flash_service.backup_before_flash("xiao", "COM7", 8)

        self.assertFalse(result["success"])
        run.assert_called_once()
        self.assertIn("Complete 8 MB", result["error"])

    def test_orchestrator_blocks_esp_write_after_backup_failure(self):
        device = {"id": "xiao", "family": "xiao-esp32s3-sense", "port": "COM7"}
        failed_backup = {"status": "failed", "error": "read failed"}
        with patch.object(fleet_orchestrator, "esp_backup_firmware", return_value=failed_backup) as backup, \
                patch.object(fleet_orchestrator, "esp_flash_firmware") as flash:
            result = fleet_orchestrator._execute_firmware(
                device, {"firmware_path": "firmware.bin", "backup_before_update": False},
            )

        self.assertEqual(result["status"], "failed")
        backup.assert_called_once_with("COM7", flash_size_mb=8, output_name="xiao")
        flash.assert_not_called()

    def test_idf_flash_blocks_idf_write_after_backup_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "idf-project"
            project.mkdir()
            with patch.object(idf_service, "detect_idf_installation", return_value={
                "installed": True,
                "active_path": directory,
                "idf_python": "python",
            }), patch.object(
                idf_service, "backup_before_idf_flash",
                return_value={"success": False, "error": "read failed"},
            ), patch.object(idf_service.subprocess, "run") as run:
                result = idf_service.idf_flash(str(project), "COM7", target="esp32s3")

        self.assertFalse(result["success"])
        self.assertEqual(result["phase"], "backup")
        self.assertIn("read failed", result["error"])
        run.assert_not_called()

    def test_idf_backup_blocks_idf_write_after_incomplete_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(idf_service, "REPO_ROOT", Path(directory)), \
                    patch.object(idf_service, "get_esptool_cmd", return_value=["esptool"]):
                def incomplete_backup(*args, **kwargs):
                    Path(args[0][-1]).write_bytes(b"incomplete")
                    return SimpleNamespace(returncode=0, stdout="", stderr="")

                with patch.object(idf_service.subprocess, "run", side_effect=incomplete_backup) as run:
                    result = idf_service.backup_before_idf_flash("COM7")

        self.assertFalse(result["success"])
        self.assertEqual(result["backup_size"], len(b"incomplete"))
        self.assertIn("Incomplete backup", result["error"])
        run.assert_called_once()

    def test_idf_flash_blocks_idf_write_when_backup_raises(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "idf-project"
            project.mkdir()
            with patch.object(idf_service, "detect_idf_installation", return_value={
                "installed": True,
                "active_path": directory,
                "idf_python": "python",
            }), patch.object(
                idf_service, "backup_before_idf_flash",
                side_effect=RuntimeError("device disconnected"),
            ), patch.object(idf_service.subprocess, "run") as run:
                result = idf_service.idf_flash(str(project), "COM7")

        self.assertFalse(result["success"])
        self.assertEqual(result["phase"], "backup")
        self.assertIn("device disconnected", result["error"])
        run.assert_not_called()

    def test_idf_flash_runs_once_after_validated_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "idf-project"
            project.mkdir()
            backup = {
                "success": True,
                "backup_path": str(Path(directory) / "backup.bin"),
                "backup_size": 8 * 1024 * 1024,
                "expected_size": 8 * 1024 * 1024,
            }
            with patch.object(idf_service, "detect_idf_installation", return_value={
                "installed": True,
                "active_path": directory,
                "idf_python": "python",
            }), patch.object(idf_service, "backup_before_idf_flash", return_value=backup), \
                    patch.object(idf_service, "get_idf_env", return_value={}) as get_env, \
                    patch.object(
                        idf_service.subprocess,
                        "run",
                        return_value=SimpleNamespace(returncode=0, stdout="written", stderr=""),
                    ) as run:
                result = idf_service.idf_flash(str(project), "COM7", target="esp32s3", baud="460800")

        self.assertTrue(result["success"])
        self.assertEqual(result["backup"], backup)
        get_env.assert_called_once_with()
        run.assert_called_once()
        command = run.call_args.args[0]
        self.assertIn("flash", command)
        self.assertIn("COM7", command)

    def test_idf_backup_uses_explicit_16_mb_board_size(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(idf_service, "REPO_ROOT", Path(directory)), \
                    patch.object(idf_service, "get_esptool_cmd", return_value=["esptool"]):
                def complete_backup(*args, **kwargs):
                    backup_path = Path(args[0][-1])
                    with backup_path.open("wb") as stream:
                        stream.truncate(16 * 1024 * 1024)
                    return SimpleNamespace(returncode=0, stdout="", stderr="")

                with patch.object(idf_service.subprocess, "run", side_effect=complete_backup) as run:
                    result = idf_service.backup_before_idf_flash("COM7", flash_size_mb=16)

        self.assertTrue(result["success"])
        self.assertEqual(result["expected_size"], 16 * 1024 * 1024)
        self.assertIn(hex(16 * 1024 * 1024), run.call_args.args[0])

    def test_idf_backup_rejects_unknown_flash_size(self):
        with patch.object(idf_service.subprocess, "run") as run:
            result = idf_service.backup_before_idf_flash("COM7", flash_size_mb=12)

        self.assertFalse(result["success"])
        self.assertIn("Unsupported ESP flash size", result["error"])
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
