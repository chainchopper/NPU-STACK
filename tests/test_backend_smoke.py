import unittest

from fastapi.testclient import TestClient

from backend.main import app


class BackendSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app, raise_server_exceptions=False)

    def get_json(self, path):
        response = self.client.get(path)
        self.assertEqual(
            response.status_code,
            200,
            msg=f"GET {path} failed with {response.status_code}: {response.text}",
        )
        return response.json()

    def test_health_endpoint(self):
        data = self.get_json('/api/health')
        self.assertEqual(data.get('status'), 'healthy')
        self.assertEqual(data.get('service'), 'npu-stack-backend')
        self.assertIn('version', data)

    def test_status_endpoint(self):
        data = self.get_json('/api/status')
        for key in ('models', 'training_jobs', 'running_jobs', 'benchmarks'):
            self.assertIn(key, data)
            self.assertIsInstance(data[key], int)

    def test_openai_models_endpoint(self):
        data = self.get_json('/v1/models')
        self.assertEqual(data.get('object'), 'list')
        self.assertIn('data', data)
        self.assertIsInstance(data['data'], list)

    def test_openai_models_status_endpoint(self):
        data = self.get_json('/v1/models/status')
        self.assertIn('loaded_count', data)
        self.assertIn('models', data)
        self.assertIsInstance(data['loaded_count'], int)
        self.assertIsInstance(data['models'], list)

    def test_benchmark_system_info_endpoint(self):
        data = self.get_json('/api/benchmark/system-info')
        for key in ('platform', 'cpu_count', 'memory_total_gb', 'cuda_available'):
            self.assertIn(key, data)

    def test_finetune_jobs_endpoint(self):
        data = self.get_json('/api/finetune/jobs')
        self.assertIn('jobs', data)
        self.assertIsInstance(data['jobs'], list)

    def test_flm_status_endpoint(self):
        data = self.get_json('/api/flm/status')
        for key in ('installed', 'server_running', 'server_managed', 'active_model', 'server_models'):
            self.assertIn(key, data)

    def test_devices_endpoint(self):
        data = self.get_json('/api/devices')
        for key in ('devices', 'count', 'last_scan'):
            self.assertIn(key, data)
        self.assertIsInstance(data['devices'], list)
        self.assertIsInstance(data['count'], int)

    def test_device_profiles_endpoint(self):
        data = self.get_json('/api/devices/profiles')
        self.assertIn('profiles', data)
        self.assertIn('count', data)
        self.assertIsInstance(data['profiles'], list)
        self.assertIsInstance(data['count'], int)


if __name__ == '__main__':
    unittest.main()
