# Backend API Documentation

## Overview

The NPU-STACK backend is a FastAPI application providing REST APIs and WebSocket endpoints for managing ML models, training, conversion, quantization, and benchmarking.

## Running

```bash
cd backend
pip install -r requirements.txt
python main.py
# → http://localhost:8000/api/docs
```

## API Endpoints

### Models (`/api/models`)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/models/upload` | Upload model file (multipart form) |
| `GET` | `/api/models` | List all models, optional `?framework=` filter |
| `GET` | `/api/models/{id}` | Get model details + metadata |
| `DELETE` | `/api/models/{id}` | Delete model from registry and disk |
| `GET` | `/api/models/{id}/download` | Download model file |

**Supported Formats:** `.onnx`, `.pt`, `.pth`, `.xml` (OpenVINO), `.tflite`, `.pb`

### Training (`/api/training`)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/training/start` | Start a training job |
| `GET` | `/api/training/jobs` | List all jobs, optional `?status=` |
| `GET` | `/api/training/jobs/{id}` | Get job details + metrics history |
| `POST` | `/api/training/jobs/{id}/stop` | Stop a running job |
| `WS` | `/ws/training/{id}` | Real-time progress via WebSocket |

**Training Config:**
```json
{
  "name": "my-job",
  "architecture": "resnet18",  // simple_cnn, resnet18, mobilenet_v2, efficientnet_b0
  "dataset": "cifar10",        // mnist, fashion_mnist, cifar10
  "epochs": 10,
  "batch_size": 64,
  "learning_rate": 0.001,
  "optimizer": "adam",          // adam, adamw, sgd
  "weight_decay": 0.0001
}
```

**WebSocket Messages:**
- `epoch_complete`: Per-epoch metrics (loss, accuracy, time)
- `batch_progress`: Batch-level progress updates
- `log`: Status messages
- `status`: Job status changes (running, completed, failed, stopped)

### Conversion (`/api/convert`)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/convert` | Convert model format |
| `POST` | `/api/convert/quantize` | Quantize model |
| `GET` | `/api/convert/validate/{id}` | Validate ONNX model graph |

**Conversion Targets:** `openvino` (ONNX → OpenVINO IR)

**Quantization Methods:**
- `dynamic` — ONNX Runtime dynamic INT8 (no calibration needed)
- `static` — ONNX Runtime static INT8 (with calibration data)
- `nncf_int8` — NNCF INT8 weight compression (OpenVINO optimized)
- `nncf_int4` — NNCF INT4 weight compression (maximum compression)

### Benchmark (`/api/benchmark`)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/benchmark/run` | Run inference benchmark |
| `GET` | `/api/benchmark/results` | List past results |
| `GET` | `/api/benchmark/compare?ids=1,2,3` | Compare benchmarks |
| `GET` | `/api/benchmark/system-info` | Hardware capabilities |

**Benchmark Config:**
```json
{
  "model_id": 1,
  "runtime": "onnxruntime",  // onnxruntime, openvino
  "device": "cpu",            // cpu, npu, cuda, auto
  "batch_size": 1,
  "warmup_runs": 10,
  "num_iterations": 100
}
```

## Database

SQLite database stored at `data/npu_stack.db`. Tables: `models`, `training_jobs`, `benchmark_results`.

## Service Architecture

- **training_service.py** — PyTorch training loop with real datasets and model architectures
- **conversion_service.py** — ONNX validation, OpenVINO conversion, ONNX Runtime quantization, NNCF compression
- **benchmark_service.py** — ONNX Runtime and OpenVINO inference benchmarking with statistical profiling
