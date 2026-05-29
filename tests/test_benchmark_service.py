import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.services.benchmark_service import _plan_onnxruntime_execution, _probe_onnxruntime_provider_libraries


class BenchmarkServicePlanTests(unittest.TestCase):
    def test_auto_prefers_cuda_before_other_accelerators(self):
        plan = _plan_onnxruntime_execution('auto', ['CPUExecutionProvider', 'DmlExecutionProvider', 'CUDAExecutionProvider'])

        self.assertEqual(plan['attempts'][0]['device'], 'cuda')
        self.assertEqual(plan['attempts'][0]['primary_provider'], 'CUDAExecutionProvider')

    def test_gpu_request_uses_directml_when_cuda_is_missing(self):
        plan = _plan_onnxruntime_execution('gpu', ['CPUExecutionProvider', 'DmlExecutionProvider'])

        self.assertEqual(plan['attempts'][0]['device'], 'directml')
        self.assertEqual(plan['attempts'][0]['primary_provider'], 'DmlExecutionProvider')

    def test_npu_request_uses_openvino_npu_first(self):
        plan = _plan_onnxruntime_execution('npu', ['CPUExecutionProvider', 'OpenVINOExecutionProvider'])

        self.assertEqual(plan['attempts'][0]['device'], 'openvino-npu')
        self.assertEqual(plan['attempts'][0]['primary_provider'], 'OpenVINOExecutionProvider')
        self.assertTrue(plan['attempts'][-1]['fallback'])

    def test_probe_onnxruntime_provider_libraries_reports_missing_dependency(self):
        fake_ort = SimpleNamespace(__file__='J:/NPU-STACK/.venv/Lib/site-packages/onnxruntime/__init__.py')

        class FakePath(str):
            def resolve(self):
                return self

            @property
            def parent(self):
                return self

            def __truediv__(self, other):
                return FakePath(f'{self}/{other}')

            def exists(self):
                return True

            @property
            def name(self):
                return self.split('/')[-1]

        with patch('platform.system', return_value='Windows'), \
             patch('pathlib.Path', side_effect=lambda value: FakePath(value)), \
             patch('ctypes.WinDLL', side_effect=OSError('cublasLt64_12.dll is missing')):
            status = _probe_onnxruntime_provider_libraries(fake_ort)

        self.assertIn('CUDAExecutionProvider', status)
        self.assertFalse(status['CUDAExecutionProvider']['loadable'])
        self.assertIn('cublasLt64_12.dll', status['CUDAExecutionProvider']['error'])


if __name__ == '__main__':
    unittest.main()