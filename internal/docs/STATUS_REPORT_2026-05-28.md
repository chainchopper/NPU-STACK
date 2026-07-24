# NPU-STACK Status Report — 2026-05-28

## Executive summary

This repository is **well beyond an empty scaffold** and currently behaves like a **broad functional prototype** with real backend depth and a sizeable frontend shell.

Based on direct code inspection and runtime validation in this session, my evidence-based estimate is:

- **Functional prototype maturity:** ~65%
- **Production hardening / operational readiness:** ~35%
- **Documentation accuracy:** ~30%

That means the project already has meaningful substance, but there is still a noticeable gap between the platform's implemented surface area and its consistency, test coverage, and deployability.

## What I recovered from the prior session

I attempted to recover the earlier Antigravity IDE conversation context from local session metadata and workspace artifacts.

### Recovery result

- I found evidence of prior VS Code/Copilot session storage.
- I did **not** find a recoverable prior transcript specific to `NPU-STACK` with actionable task history.
- One older recovered chat artifact belonged to a **different repository**, so it was not used.
- The best reliable reconstruction path was therefore the **current repository state**: source tree, docs, git status, routes, pages, and runtime checks.

## What was verified in this session

### Backend

Validated directly:

- `backend/main.py` imports successfully in the project virtual environment.
- FastAPI app mounts **136 routes**.
- Core smoke call works:
  - `health_check()` returned healthy status.
- Representative route shapes were verified with a test client:
  - `/api/flm/status`
  - `/api/flm/models`
  - `/api/devices`
  - `/api/devices/backups`
  - `/api/devices/rp2040/detect`
  - `/v1/models`
  - `/v1/models/status`
  - `/api/finetune/jobs`

### Frontend

Validated directly:

- Frontend production build succeeds with `npm run build`.
- Current build output is successful but emits a **large bundle warning**:
  - main JS chunk is ~`800 kB` minified before gzip warning threshold considerations.
- No file-level diagnostics were reported in the touched frontend files.

## Actual codebase shape

### Frontend surface

The real frontend is larger than the docs claim.

Observed pages under `frontend/src/pages/`:

- `Dashboard`
- `Playground`
- `Models`
- `ModelHub`
- `HubPublisher`
- `Datasets`
- `DataIngestion`
- `Serving`
- `Training`
- `FineTuning`
- `GGUFStudio`
- `FastFlowLM`
- `Conversion`
- `Scanner`
- `WebcamTest`
- `Benchmark`
- `EdgeFleet`

That is **17 routed pages**, not the smaller set described in the docs.

### Backend surface

Observed backend routers under `backend/routers/` include at least:

- `models`
- `training`
- `conversion`
- `benchmark`
- `inference`
- `huggingface`
- `datasets`
- `serving`
- `finetuning`
- `scanner`
- `webcam`
- `filebrowser`
- `ingest`
- `assets`
- `gguf_pipeline`
- `finetune_publish`
- `nim`
- `cvedia`
- `vitis_compiler`
- `devices`
- `agent`
- `civitai`
- `flm`

The backend surface is therefore significantly richer than the docs suggest.

## What appears genuinely implemented

These areas have real code paths, actual route wiring, and enough implementation depth to count as substantive:

- FastAPI application bootstrap and router composition
- OpenAI-compatible `/v1` serving surface
- Model registry / upload / list / delete
- Benchmark route and hardware/system-info plumbing
- Scanner and file-browser support
- HuggingFace integration
- Dataset management
- Training and fine-tuning route scaffolding with job state
- GGUF pipeline routes
- Device discovery / edge fleet registry
- FastFlowLM integration layer
- Dashboard-level hardware/system summary UI

## What appears partial, fragile, or inconsistent

These areas exist, but currently show signs of incomplete productization:

### 1. Frontend/backend contract drift

This is the most important current issue category.

Examples found in this session:

- `FastFlowLM` frontend expected a different status shape than the backend actually returns.
- `FastFlowLM` model catalog/local model objects did not line up cleanly with backend payloads.
- `FineTuning` job detail UI was calling the wrong backend endpoint.
- `EdgeFleet` backup rendering assumed simple strings while backend returns rich objects.
- `EdgeFleet` RP2040 detection UI expected a different response format than the backend returns.

### 2. Docs are outdated

Observed mismatches:

- `README.md` architecture counts do not match current router/page counts.
- `docs/FRONTEND.md` still describes a much smaller app.
- `docs/BACKEND.md` only covers a subset of what now exists.

### 3. Several frontend pages bypass the shared API layer

There are many hardcoded `http://localhost:8000` URLs in the frontend.
This creates avoidable drift, complicates proxying, and makes deployment less portable.

### 4. Some UI areas are still placeholder-level

Concrete example:

- `frontend/src/pages/HubPublisher.jsx` explicitly states that full interactive forms are "coming soon".

### 5. Test strategy is weak at the app level

- There is no obvious focused frontend test suite for routed pages.
- There is no small backend smoke-test suite covering the project's own critical routes.
- There are many third-party/library tests in vendored subtrees, but those do **not** prove the main app works.

## What I fixed during this session

I made targeted repairs to high-value integration issues instead of only reporting them.

### Fixed now

#### `frontend/src/api/client.js`

- Normalized FastFlowLM status payloads into the shape the UI expects.
- Normalized FastFlowLM model metadata for both local and catalog entries.
- Fixed FastFlowLM pull-stream parsing so SSE payloads are handled correctly.
- Normalized FLM pull completion state from backend `complete` to frontend `completed`.

#### `frontend/src/pages/EdgeFleet.jsx`

- Fixed RP2040 detection logging to use the backend's real `{ devices, count }` response.
- Fixed firmware backup rendering to show backup object data properly instead of treating items like plain strings.

#### `frontend/src/pages/FineTuning.jsx`

- Fixed job detail fetch path from the incorrect `/api/finetune/jobs/{id}` to the real `/api/finetune/status/{id}`.

## Progress assessment by area

### Strongest areas

- **Backend breadth:** surprisingly substantial
- **Hardware/system discovery foundation:** credible and real
- **OpenAI-compatible serving direction:** real and testable
- **Frontend shell and navigation:** extensive and functional enough to compile cleanly

### Weakest areas

- **Contract consistency between pages and APIs**
- **Documentation fidelity**
- **Deployment portability in frontend network calls**
- **App-specific tests / smoke coverage**
- **Bundle size / code splitting**

## Current repo state notes

The repository contains substantial in-flight work beyond the tracked diff alone, including untracked additions such as:

- `backend/routers/devices.py`
- `backend/routers/flm.py`
- `backend/services/edge_discovery.py`
- `backend/services/flm_service.py`
- `frontend/src/pages/EdgeFleet.jsx`
- `frontend/src/pages/FastFlowLM.jsx`
- `firmware/`
- `libraries/`
- `compositions/`

This reinforces the conclusion that the project is actively expanding and that the docs are lagging behind the implementation.

## Risk summary

### High risk

- Frontend/backend contract drift on newly added features
- Hardcoded API origins in frontend code
- Hidden breakage due to lack of small smoke tests

### Medium risk

- Oversized frontend bundle
- Documentation misrepresenting current feature readiness
- Mixed maturity level across feature pages

### Low risk

- Core app bootstrap and build pipeline, as currently tested in this session

## Bottom line

`NPU-STACK` is **not vaporware**. It is a **real, ambitious, partially working platform** with meaningful backend implementation and a broad frontend shell.

The project is best described today as:

> **A capable full-stack AI platform prototype with strong backend momentum, uneven frontend integration quality, and significant need for consolidation/hardening before calling it production-ready.**
