# Docker Deployment Guide

## Quick Start

```bash
docker compose up --build
```

This launches:
- **Backend** at `http://localhost:8000` (API + WebSocket)
- **Frontend** at `http://localhost:3000` (Dashboard UI)

## Services

### npu-backend
- **Image:** Python 3.11-slim with PyTorch, OpenVINO, NNCF
- **Port:** 8000
- **Health Check:** `/api/health`
- **Volumes:**
  - `model-store` — Persisted model files
  - `dataset-cache` — Downloaded datasets (CIFAR-10, MNIST)
  - `db-data` — SQLite database

### npu-frontend
- **Image:** Multi-stage Node 20 build → Nginx
- **Port:** 3000
- **Proxies:** `/api/*` and `/ws/*` to backend
- **Depends on:** npu-backend (healthy)

## Volumes

| Volume | Purpose |
|--------|---------|
| `model-store` | Uploaded and trained models |
| `dataset-cache` | Downloaded torchvision datasets |
| `db-data` | SQLite metadata database |

## Commands

```bash
# Start
docker compose up --build -d

# View logs
docker compose logs -f

# Stop
docker compose down

# Reset data
docker compose down -v
```

## Resource Requirements

- **Minimum:** 4 GB RAM, 10 GB disk
- **Recommended:** 8+ GB RAM for training larger models
- **GPU:** Optional (CUDA support requires nvidia-docker)
- **NPU:** Not available inside Docker (use local dev for NPU testing)

## Notes

- First run downloads PyTorch, OpenVINO, etc. (~5 GB image)
- Datasets download on first training job
- For NPU inference, run the backend locally with OpenVINO NPU plugin
