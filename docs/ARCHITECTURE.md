# Architecture Overview

## System Design

NPU-STACK follows a clean client-server architecture with clear separation of concerns:

```
┌─────────────┐       HTTP/WS        ┌──────────────────┐
│   Frontend  │ ◄──────────────────▶ │     Backend      │
│  React SPA  │                      │  FastAPI Server   │
│  Vite/Nginx │                      │                  │
└─────────────┘                      ├──────────────────┤
                                     │  Training        │──▶ PyTorch
                                     │  Service         │──▶ torchvision
                                     ├──────────────────┤
                                     │  Conversion      │──▶ OpenVINO
                                     │  Service         │──▶ ONNX Runtime
                                     │                  │──▶ NNCF
                                     ├──────────────────┤
                                     │  Benchmark       │──▶ ORT InferenceSession
                                     │  Service         │──▶ OV CompiledModel
                                     ├──────────────────┤
                                     │  Storage Layer   │
                                     │  SQLite + Files  │
                                     └──────────────────┘
```

## Data Flow

### Training Pipeline
1. User configures job (architecture, dataset, hyperparameters)
2. FastAPI creates job record, starts async training task
3. PyTorch training loop runs with real datasets/models
4. Progress broadcast via WebSocket per batch/epoch
5. On completion: model saved as PyTorch checkpoint + ONNX export
6. Exported ONNX model auto-registered in model registry

### Conversion Pipeline
1. User selects source model (ONNX) and target format
2. OpenVINO `convert_model()` transforms ONNX → IR format
3. Optional FP16 compression applied during conversion
4. Quantization uses ONNX Runtime or NNCF APIs
5. Converted model registered as new entry in registry

### Benchmark Pipeline
1. User selects model, runtime, device, and config
2. ONNX Runtime or OpenVINO loads model for target device
3. Warmup runs followed by timed iterations
4. Memory profiling via Python `tracemalloc`
5. Statistical aggregation: mean, p50, p95, p99 latency
6. Results stored in database for comparison

## NPU Integration

### Intel NPU (via OpenVINO)
- Models must be in OpenVINO IR format (converted from ONNX)
- INT8/INT4 quantization via NNCF optimizes for NPU execution
- OpenVINO compiles model using NPU driver's graph extension API
- Benchmark supports `device: "NPU"` for Intel Core Ultra systems

### TPU (via PyTorch/XLA)
- Training supports TPU devices when `torch_xla` is installed
- Models exported as ONNX after training
- TPU inference requires Google Cloud TPU VM environment

## Technology Dependencies

### Backend Runtime
- **PyTorch 2.x** — Model architectures and training loops
- **torchvision** — Built-in datasets and pretrained model architectures
- **ONNX** — Model interchange format validation
- **ONNX Runtime** — Cross-platform inference and quantization
- **OpenVINO** — Intel NPU model conversion and inference
- **NNCF** — Neural Network Compression Framework for INT8/INT4

### Frontend
- **React 18** — Component-based UI
- **Vite** — Fast build tool with HMR
- **Recharts** — Data visualization (training curves, benchmarks)
- **Lucide React** — Icon system

### Infrastructure
- **FastAPI** — Async Python web framework with auto-docs
- **SQLAlchemy** — ORM for SQLite metadata
- **Docker Compose** — Container orchestration
- **Nginx** — Static file serving and API reverse proxy
