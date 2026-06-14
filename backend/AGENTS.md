# backend/ — NPU-STACK Backend

## Purpose

FastAPI server providing all NPU-STACK APIs: model registry, training orchestration, conversion pipeline, benchmarking, inference, HuggingFace integration, fleet operations, the Nirvana agent bridge, and the OpenAI-compatible `/v1` endpoint.

## Ownership

This is an active development boundary. All changes to API routes, services, or backend behavior go here.

## Local Contracts

- Runs on port `8010` by default
- Uses SQLite at `backend/npu_stack.sqlite` for operational state
- Nirvana runtime state lives in `backend/data/nirvana-runtime/`
- The `.env` file at the repo root provides API keys and config — DO NOT modify without approval
- All routers are mounted in `main.py` in declaration order — native NPU-STACK routes first, then agent/orchestration routes
- The Nirvana bridge is DeepSeek-first; local GGUF is recovery-only fallback

## Router Map

| Router | File | Purpose |
| --- | --- | --- |
| `models_router` | `routers/models.py` | Model registry, upload, download, scan |
| `training_router` | `routers/training.py` | Training job lifecycle + WebSocket |
| `conversion_router` | `routers/conversion.py` | Model format conversion |
| `benchmark_router` | `routers/benchmark.py` | Performance benchmarks |
| `inference_router` | `routers/inference.py` | Local inference endpoints |
| `huggingface_router` | `routers/huggingface.py` | HF Hub integration |
| `datasets_router` | `routers/datasets.py` | Dataset management |
| `serving_router` | `routers/serving.py` | OpenAI-compatible `/v1` endpoint |
| `finetuning_router` | `routers/finetuning.py` | Fine-tuning job management |
| `agent_router` | `routers/agent.py` | Nirvana agent bridge — chat, start, status, runtime |
| `orchestration_router` | `routers/orchestration.py` | Orchestration profiles, sessions, state |
| `fleet_command_router` | `routers/fleet_command.py` | Fleet command dispatch |
| `fleet_agent_router` | `routers/fleet_agent.py` | Fleet agent polling/registration |
| `devices_router` | `routers/devices.py` | Device discovery and inventory |
| `docs_index_router` | `routers/docs_index.py` | Documentation search/index |

## Key Services

| Service | File | Purpose |
| --- | --- | --- |
| `nirvana_service` | `services/nirvana_service.py` | Nirvana runtime: isolated Python, WebUI launch, bridge health, sync chat proxy |
| `gguf_service` | `services/gguf_service.py` | Local GGUF model loading and inference (recovery fallback) |
| `docs_index_service` | `services/docs_index_service.py` | Embedding-based documentation search |
| `fleet_orchestrator` | `services/fleet_orchestrator.py` | Fleet device orchestration logic |
| `training_service` | `services/training_service.py` | Training orchestration |

## Work Guidance

- Follow FastAPI conventions: Pydantic models for request/response, async handlers
- The Nirvana bridge is the critical path — test against pinned session `session-0c9b513294` for regressions
- When adding a new router, register it in `main.py` before any catch-all proxy routes
- The OpenAI-compatible endpoint at `/v1` must remain ABI-compatible with the OpenAI client SDK

## Verification

- Backend health: `curl http://127.0.0.1:8010/api/health` → `{"status":"healthy"}`
- Nirvana bridge: `curl http://127.0.0.1:8010/api/agent/runtime` → check `engine`, `current_provider`, `chat_ready`
- Import check: `.venv\Scripts\python.exe -c "from backend.main import app; print('ok')"`

## Child DOX Index

No child boundaries yet. Service files and routers are flat under `backend/`.
