from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class LauncherContractTests(unittest.TestCase):
    def read_launcher(self, name):
        return (ROOT / name).read_text(encoding="utf-8").lower()

    def test_windows_backend_launcher_uses_supported_package_entrypoint(self):
        launcher = self.read_launcher("run-backend.bat")

        self.assertIn(".venv\\scripts\\python.exe", launcher)
        self.assertIn("-m uvicorn backend.main:app", launcher)
        self.assertIn('cd /d "!root!"', launcher)
        self.assertIn("pythonioencoding=utf-8", launcher)
        self.assertIn("pythonutf8=1", launcher)
        self.assertNotIn('cd /d "!root!\\backend"', launcher)
        self.assertNotIn("--reload", launcher)

    def test_windows_full_launcher_checks_backend_readiness(self):
        launcher = self.read_launcher("run-all.bat")

        self.assertIn("call :wait_for_backend", launcher)
        self.assertIn("curl.exe --fail", launcher)
        self.assertIn("/api/health", launcher)
        self.assertIn("localhost:5180", launcher)
        self.assertNotIn("localhost:5173", launcher)

    def test_legacy_windows_launchers_delegate_to_supported_scripts(self):
        self.assertIn("run-backend.bat", self.read_launcher("start-backend.bat"))
        self.assertIn("run-all.bat", self.read_launcher("start-all.bat"))
        self.assertIn("run-frontend.bat", self.read_launcher("start-frontend.bat"))

    def test_posix_launchers_use_root_package_and_readiness_check(self):
        backend = self.read_launcher("run-backend.sh")
        full = self.read_launcher("run-all.sh")
        frontend = self.read_launcher("run-frontend.sh")

        self.assertIn("python -m uvicorn backend.main:app", backend)
        self.assertIn("pythonioencoding=utf-8", backend)
        self.assertIn("curl --fail", full)
        self.assertIn("/api/health", full)
        self.assertIn("localhost:5180", full)
        self.assertNotIn("localhost:5173", full)
        self.assertIn("localhost:5180", frontend)
        self.assertNotIn("localhost:5173", frontend)


if __name__ == "__main__":
    unittest.main()
