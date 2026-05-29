import unittest

from backend.services.benchmark_service import _plan_onnxruntime_execution


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


if __name__ == '__main__':
    unittest.main()