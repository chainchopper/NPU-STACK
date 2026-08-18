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
| `huggingface_router` | `routers/huggingface.py` | HuggingFace Hub integration |
| `datasets_router` | `routers/datasets.py` | Dataset management |
| `serving_router` | `routers/serving.py` | OpenAI-compatible `/v1` endpoint |
| `finetuning_router` | `routers/finetuning.py` | Fine-tuning job management |
| `finetune_publish_router` | `routers/finetune_publish.py` | Publish fine-tuned models |
| `agent_router` | `routers/agent.py` | Nirvana bridge — chat, start, status, runtime |
| `orchestration_router` | `routers/orchestration.py` | Orchestration profiles, sessions, state |
| `nirvana_webui_router` | `routers/nirvana_webui.py` | Native Nirvana management — settings, sessions, skills, config read directly from shared state files |
| `fleet_command_router` | `routers/fleet_command.py` | Fleet command dispatch |
| `fleet_agent_router` | `routers/fleet_agent.py` | Fleet agent polling/registration |
| `devices_router` | `routers/devices.py` | Device discovery and inventory |
| `docs_index_router` | `routers/docs_index.py` | Documentation search/index |
| `assets_router` | `routers/assets.py` | Static asset serving |
| `civitai_router` | `routers/civitai.py` | CivitAI model integration |
| `cvedia_router` | `routers/cvedia.py` | CVEDIA integration |
| `filebrowser_router` | `routers/filebrowser.py` | File system browser |
| `flm_router` | `routers/flm.py` | FastFlowLM inference |
| `gguf_pipeline_router` | `routers/gguf_pipeline.py` | GGUF quantization pipeline |
| `ingest_router` | `routers/ingest.py` | Data ingestion |
| `nim_router` | `routers/nim.py` | NVIDIA NIM integration |
| `scanner_router` | `routers/scanner.py` | Hardware/GPU scanner |
| `vitis_compiler_router` | `routers/vitis_compiler.py` | Vitis AI compiler |
| `espnow_router` | `routers/espnow_router.py` | ESP-NOW firmware discovery, build commands, binary listing |
| `webcam_router` | `routers/webcam.py` | Webcam testing |
| `xiaozhi_websocket_router` | `routers/xiaozhi_websocket.py` | XiaoZhi voice WebSocket transport — hello/listen/abort/mcp/goodbye JSON + Opus binary (v1/v2/v3) |

## Key Services

| Service | File | Purpose |
| --- | --- | --- |
| `nirvana_service` | `services/nirvana_service.py` | Nirvana runtime: isolated Python, WebUI launch, bridge health, sync chat proxy |
| `gguf_service` | `services/gguf_service.py` | Local GGUF model loading and inference (recovery fallback) |
| `docs_index_service` | `services/docs_index_service.py` | Embedding-based documentation search |
| `fleet_orchestrator` | `services/fleet_orchestrator.py` | Fleet device orchestration logic |
| `training_service` | `services/training_service.py` | Training orchestration |
| `benchmark_service` | `services/benchmark_service.py` | Benchmark execution engine |
| `conversion_service` | `services/conversion_service.py` | Model format conversion engine |
| `cross_converter` | `services/cross_converter.py` | Cross-framework model conversion |
| `cvedia_service` | `services/cvedia_service.py` | CVEDIA integration logic |
| `dataset_builder` | `services/dataset_builder.py` | Dataset construction pipeline |
| `data_extractor` | `services/data_extractor.py` | Dataset extraction utilities |
| `edge_discovery` | `services/edge_discovery.py` | Edge device discovery — USB/PnP/mDNS/network + MicroPython/Nirvana OS serial probe (stable unique-id registration) |
| `flm_service` | `services/flm_service.py` | FastFlowLM integration |
| `gguf_pipeline` | `services/gguf_pipeline.py` | GGUF conversion pipeline |
| `hub_publisher` | `services/hub_publisher.py` | HuggingFace publishing |
| `litert_service` | `services/litert_service.py` | LiteRT runtime integration |
| `mediapipe_service` | `services/mediapipe_service.py` | MediaPipe integration |
| `model_registry` | `services/model_registry.py` | Model registry storage layer |
| `nim_service` | `services/nim_service.py` | NVIDIA NIM integration |
| `opencv_service` | `services/opencv_service.py` | OpenCV/computer vision utilities |
| `rknn_service` | `services/rknn_service.py` | Rockchip RKNN integration |
| `unsloth_service` | `services/unsloth_service.py` | Unsloth fine-tuning integration |
| `espnow_service` | `services/espnow_service.py` | ESP-NOW library discovery, examples, IDF commands, binaries |
| `vitis_compiler` | `services/vitis_compiler.py` | Vitis AI compiler integration |

## Work Guidance

- Follow FastAPI conventions: Pydantic models for request/response, async handlers
- Native Nirvana management endpoints at `/api/nirvana/*` read directly from shared state — no proxy, no WebUI process needed
- `GET /api/nirvana/settings`, `GET /api/nirvana/sessions`, `GET /api/nirvana/skills` all return data from `.hermes/webui/` state files
- The proxy middleware protects `/api/nirvana/*` from being forwarded to `:8789`
- When adding a new router, register it in `main.py` before any catch-all proxy routes
- The OpenAI-compatible endpoint at `/v1` must remain ABI-compatible with the OpenAI client SDK
- `GET /api/devices/scan` probes connected USB serial ports for live MicroPython/Nirvana boards and registers them by stable unique id (`nirvana-<uid>`); the background auto-poll probes only ports not yet identified
- `GET /api/health` doubles as the Nirvana board phone-home: when called with `device_id`/`ip`/`firmware`/`machine` query params it registers/refreshes the board in the edge registry

## Verification

- Backend health: `curl http://127.0.0.1:8010/api/health` → `{"status":"healthy"}`
- Nirvana bridge: `curl http://127.0.0.1:8010/api/agent/runtime` → check `engine`, `current_provider`, `chat_ready`
- Import check: `.venv\Scripts\python.exe -c "from backend.main import app; print('ok')"`
- Nirvana native health: `curl http://127.0.0.1:8010/api/nirvana/health`
- MCP tools: `.venv\Scripts\python.exe -c "from backend.mcp_server import mcp; print(f'Tools: {len(mcp._tool_manager._tools)}')"` → 13

## Nirvana Native Endpoints (`/api/nirvana/*`)

| Method | Path | Reads from |
| --- | --- | --- |
| GET | `/health` | Multiple state files |
| GET | `/overview` | Aggregated: settings, sessions, skills, config |
| GET | `/settings` | `settings.json` |
| PATCH | `/settings` | `settings.json` (write) |
| GET | `/sessions` | `sessions/_index.json` |
| GET | `/sessions/{id}` | `sessions/{id}.json` |
| GET | `/skills` | `skills/**/SKILL.md` + `.usage.json` |
| GET | `/skills/{name}` | `skills/**/SKILL.md` |
| GET | `/config` | `config.yaml` |
| GET | `/cron` | `cron/output/` |
| GET | `/kanban` | `kanban/boards/` |
| GET | `/kanban/{slug}` | `kanban/boards/{slug}/board.json` |
| GET | `/memory` | `memories/` |
| GET | `/memory/{file}` | `memories/{file}` |
| GET | `/providers` | `auth.json` |
| GET | `/logs` | `logs/` |
| GET | `/logs/{name}?tail=N` | `logs/{name}` |
| GET | `/workspace?path=` | File system (J:\NPU-STACK) |

### MCP Tools (13 via stdio)

`backend/mcp_server.py` — discovered by Nirvana via `config.yaml` `mcp_servers.npu-stack`.

detect_hardware, system_health, system_status, list_models, get_model_info,
list_devices, fleet_status, run_fleet_command, list_training_jobs,
list_conversion_paths, nirvana_overview, nirvana_settings, nirvana_sessions

## Child DOX Index

No child boundaries yet. Service files and routers are flat under `backend/`.
