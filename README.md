<div align="center">

# ⚡ NPU-STACK

### Full-Stack Neural Processor Model Toolkit

**Train · Convert · Quantize · Benchmark** ML models for **NPU** & **TPU** hardware

[![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python)](https://python.org)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react)](https://react.dev)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker)](https://docker.com)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

</div>

---

## 🎯 What is NPU-STACK?

NPU-STACK is an **open-source, full-stack platform** for developing machine learning models that run on Neural Processing Units (NPUs) and Tensor Processing Units (TPUs). It fills a critical gap in the open-source ecosystem by providing a unified workflow from training to deployment.

### Key Features

| Feature | Description |
|---------|-------------|
| 🏋️ **Model Training** | Real PyTorch training with CIFAR-10, MNIST, Fashion-MNIST + ResNet, MobileNet, EfficientNet architectures |
| 📦 **Model Registry** | Upload, version, and manage ONNX, PyTorch, OpenVINO models |
| 🔄 **Format Conversion** | ONNX → OpenVINO IR with FP16 compression for Intel NPU |
| ⚡ **Quantization** | Dynamic INT8, Static INT8, NNCF INT8/INT4 for NPU-optimized inference |
| 📊 **Benchmarking** | Real inference profiling: latency (p50/p95/p99), throughput, memory, device comparison |
| 🌐 **Web Dashboard** | Premium React UI with real-time training charts via WebSocket |
| 🐳 **One-Command Deploy** | Single `docker compose up` launches the full stack |

---

## 🏗️ Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                    NPU-STACK Architecture                       │
├────────────────────┬───────────────────────────────────────────┤
│                    │                                           │
│   React + Vite     │   FastAPI + Python                       │
│   (:5173 / :3000)  │   (:8000)                                │
│                    │                                           │
│   ┌─Dashboard──┐   │   ┌─Models API──────────────────────┐   │
│   │ Metrics    │   │   │ Upload / List / Download         │   │
│   │ System Info│   │   └─────────────────────────────────┘   │
│   └────────────┘   │                                           │
│                    │   ┌─Training API─────────────────────┐   │
│   ┌─Models─────┐   │   │ PyTorch Training Loop            │   │
│   │ Upload     │───│──▶│ WebSocket Progress                │   │
│   │ Registry   │   │   │ Auto ONNX Export                  │   │
│   └────────────┘   │   └─────────────────────────────────┘   │
│                    │                                           │
│   ┌─Training───┐   │   ┌─Conversion API──────────────────┐   │
│   │ Config     │   │   │ ONNX → OpenVINO IR               │   │
│   │ Live Chart │───│──▶│ Dynamic/Static Quantization      │   │
│   │ Logs       │   │   │ NNCF INT8/INT4 Compression       │   │
│   └────────────┘   │   └─────────────────────────────────┘   │
│                    │                                           │
│   ┌─Conversion─┐   │   ┌─Benchmark API───────────────────┐   │
│   │ Format     │   │   │ ONNX Runtime Inference            │   │
│   │ Quantize   │───│──▶│ OpenVINO Runtime (CPU/NPU)       │   │
│   └────────────┘   │   │ Statistical Profiling             │   │
│                    │   └─────────────────────────────────┘   │
│   ┌─Benchmark──┐   │                                           │
│   │ Profile    │   │   ┌─Storage────────────────────────┐   │
│   │ Compare    │───│──▶│ SQLite Metadata                   │   │
│   │ Charts     │   │   │ File-based Model Store            │   │
│   └────────────┘   │   └─────────────────────────────────┘   │
│                    │                                           │
└────────────────────┴───────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Docker (Recommended)

```bash
# Clone the repo
git clone <your-repo-url> NPU-STACK
cd NPU-STACK

# Launch the full stack
docker compose up --build

# Access:
#   Dashboard:  http://localhost:3000
#   API Docs:   http://localhost:8000/api/docs
```

### Local Development

**Backend:**
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/Mac
pip install -r requirements.txt
python main.py
# → http://localhost:8000/api/docs
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

---

## 📂 Project Structure

```
NPU-STACK/
├── docker-compose.yml          # One-command full-stack launch
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py                 # FastAPI entry point
│   ├── database.py             # SQLAlchemy models
│   ├── routers/
│   │   ├── models.py           # Model registry CRUD
│   │   ├── training.py         # Training job management
│   │   ├── conversion.py       # Format conversion & quantization
│   │   └── benchmark.py        # Inference benchmarking
│   └── services/
│       ├── training_service.py # Real PyTorch training loops
│       ├── conversion_service.py # ONNX/OpenVINO/NNCF conversion
│       └── benchmark_service.py  # ORT/OpenVINO benchmarking
├── frontend/
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── App.jsx             # Router + sidebar layout
│       ├── index.css           # Design system
│       ├── api/client.js       # API + WebSocket client
│       └── pages/
│           ├── Dashboard.jsx   # Overview + system info
│           ├── Models.jsx      # Model registry
│           ├── Training.jsx    # Training console
│           ├── Conversion.jsx  # Conversion studio
│           └── Benchmark.jsx   # Benchmark lab
└── docs/
    ├── BACKEND.md
    ├── FRONTEND.md
    ├── DOCKER.md
    └── ARCHITECTURE.md
```

---

## 🔧 Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Backend | FastAPI, Python 3.11 | REST API, WebSocket, async processing |
| Training | PyTorch 2.x | Model training with multiple architectures |
| Export | torch.onnx | Export to ONNX interchange format |
| Conversion | OpenVINO | Convert ONNX → OpenVINO IR for NPU |
| Quantization | ONNX Runtime, NNCF | INT8/INT4 for NPU-optimized inference |
| Inference | ONNX Runtime, OpenVINO | Cross-platform CPU/NPU inference |
| Frontend | React 18, Vite, Recharts | Modern SPA with real-time charts |
| Database | SQLite, SQLAlchemy | Lightweight metadata storage |
| Deploy | Docker Compose | Single-command full-stack launch |

---

## 📊 API Reference

All endpoints are auto-documented at `http://localhost:8000/api/docs` (Swagger UI).

### Core Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Health check |
| `GET` | `/api/status` | System status (counts) |
| `POST` | `/api/models/upload` | Upload a model file |
| `GET` | `/api/models` | List models |
| `POST` | `/api/training/start` | Start training job |
| `WS` | `/ws/training/{id}` | Real-time training progress |
| `POST` | `/api/convert` | Convert model format |
| `POST` | `/api/convert/quantize` | Quantize model |
| `POST` | `/api/benchmark/run` | Run inference benchmark |
| `GET` | `/api/benchmark/system-info` | System hardware detection |

---

## 🎛️ NPU/TPU Support

### Intel NPU (OpenVINO)
- Requires Intel Core Ultra processor with NPU 3720+
- Models are converted to OpenVINO IR and quantized with NNCF
- Benchmark with `device: "npu"` to run on NPU hardware

### Google TPU (PyTorch/XLA)
- Training supports TPU via PyTorch/XLA when running on Google Cloud
- Models are exported as ONNX for cross-platform inference

### CPU Fallback
- All features work on CPU — NPU/TPU are optional accelerators
- Great for development and testing before deploying to specialized hardware

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">

**Built with ❤️ for the NPU/TPU community**

*Filling the gap in open-source tooling for neural processor development*

</div>
# NPU-STACK
