# Backend API Guide

## Overview

The backend is a FastAPI application rooted at `backend/main.py`.

Verified current state:

- Imports successfully in the repository virtual environment
- Mounts **136 routes** in the current workspace state
- Aggregates **23 feature routers** plus health, status, docs, and WebSocket entrypoints
- Serves both platform APIs under `/api/*` and an OpenAI-compatible surface under `/v1/*`

## Run locally

### Standard

```bash
cd backend
pip install -r requirements.txt
python main.py
```

### From the repository virtual environment

```bash
.venv\Scripts\python.exe backend\main.py
```

API docs are exposed at `http://localhost:8000/api/docs`.

## Verified validation commands

```bash
# Backend smoke test suite
python -m unittest discover -s tests -p test_backend_smoke.py
```

The smoke suite currently covers:

- `/api/health`
- `/api/status`
- `/v1/models`
- `/v1/models/status`
- `/api/benchmark/system-info`
- `/api/finetune/jobs`
- `/api/flm/status`
- `/api/devices`

## Core entrypoints

### Platform health and status

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Liveness check for backend availability |
| `GET` | `/api/status` | Summary counts for models, jobs, and benchmarks |
| `WS` | `/ws/training/{job_id}` | Real-time training progress stream |

### OpenAI-compatible serving

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/v1/models` | List registered and loaded models in OpenAI format |
| `GET` | `/v1/models/status` | List currently loaded server-side models |
| `POST` | `/v1/models/load` | Load a model into memory |
| `POST` | `/v1/models/unload` | Unload a model |
| `POST` | `/v1/chat/completions` | Chat completion endpoint |
| `POST` | `/v1/completions` | Legacy completion endpoint |
| `POST` | `/v1/embeddings` | Embeddings endpoint |

### Feature router map

| Prefix | Router | Purpose |
| --- | --- | --- |
| `/api/models` | `routers/models.py` | Registry CRUD and model file handling |
| `/api/training` | `routers/training.py` | Training jobs and WebSocket progress |
| `/api/convert` | `routers/conversion.py` | Conversion and quantization |
| `/api/benchmark` | `routers/benchmark.py` | Hardware info and benchmark runs |
| `/api/inference` | `routers/inference.py` | Playground inference endpoints |
| `/api/huggingface` | `routers/huggingface.py` | Hugging Face search and download |
| `/api/datasets` | `routers/datasets.py` | Dataset catalog and management |
| `/api/finetune` | `routers/finetuning.py` | LoRA/QLoRA job creation and status |
| `/api/scanner` | `routers/scanner.py` | Local file scanning and import |
| `/api/webcam` | `routers/webcam.py` | Webcam object detection and streaming |
| `/api/browse` | `routers/filebrowser.py` | File and folder browsing helpers |
| `/api/ingest` | `routers/ingest.py` | Data ingestion and extraction flows |
| `/api/assets` | `routers/assets.py` | Asset serving and lookup |
| `/api/gguf` | `routers/gguf_pipeline.py` | GGUF inspect / quantize / convert / split / merge |
| `/api/finetune-publish` | `routers/finetune_publish.py` | Publishing fine-tuned artifacts |
| `/api/nim` | `routers/nim.py` | NVIDIA NIM integration |
| `/api/cvedia` | `routers/cvedia.py` | CVEDIA-RT integration |
| `/api/vitis` | `routers/vitis_compiler.py` | AMD Vitis AI compilation |
| `/api/devices` | `routers/devices.py` | Edge Fleet discovery and firmware ops |
| `/api/agent` | `routers/agent.py` | Agent-focused backend actions |
| `/api/civitai` | `routers/civitai.py` | Civitai search and download |
| `/api/flm` | `routers/flm.py` | FastFlowLM runtime lifecycle and proxy chat |
| `/v1` | `routers/serving.py` | OpenAI-compatible serving surface |

## Important behavior notes

### Fine-tuning input shape

`POST /api/finetune/start` expects **form fields**, not JSON.

Relevant inputs include:

- `model_id`
- `dataset`
- `epochs`
- `batch_size`
- `learning_rate`
- `use_lora`
- `lora_r`
- `lora_alpha`
- `text_column`
- `max_length`

### FastFlowLM

`/api/flm/status` is safe for smoke testing because it reports install and server state without requiring FLM to be running.

### Devices

`/api/devices` reads the persisted edge device registry and returns a stable shape:

- `devices`
- `count`
- `last_scan`

### Benchmark system info

`/api/benchmark/system-info` returns local hardware capability data and is a good non-destructive diagnostics endpoint for environment verification.

## Data and storage

Backend runtime data lives under `backend/data/`, including:

- model storage
- dataset storage
- Hugging Face cache directories
- firmware backups
- uploads and transient extraction output

## Practical maintenance guidance

- Treat `backend/main.py` as the source of truth for mounted routers
- Prefer smoke coverage for endpoint existence before deeper integration tests
- Keep frontend calls relative to `/api`, `/v1`, and `/ws` so Vite and Docker reverse proxies work consistently
