# Frontend Development Guide

## Overview

The frontend is a React 18 single-page application built with Vite.

Verified current state:

- `frontend/src/App.jsx` defines **17 routed pages**
- Shared API URL helpers live in `frontend/src/api/client.js`
- Local development uses proxy-safe relative calls instead of hardcoded backend origins
- Frontend smoke coverage runs under Vitest + React Testing Library
- GitHub Actions frontend validation now runs `npm ci`, `npm run test`, and `npm run build`
- Route pages are lazy-loaded from `App.jsx` to reduce the initial bundle
- Production build currently passes with `npm run build`

## Run locally

```bash
cd frontend
npm install
npm run dev
```

Default local URL: `http://localhost:5173`

## Build for production

```bash
cd frontend
npm run build
```

## Run smoke tests

```bash
cd frontend
npm run test
```

## CI validation

The repository now includes `.github/workflows/frontend-validation.yml`.

It runs on pushes, pull requests, and manual dispatches affecting `frontend/**`, and executes:

- `npm ci`
- `npm run test`
- `npm run build`

Latest verified build result:

- Build passes successfully
- Main entry bundle is about **184 kB** minified after route-level lazy loading
- The earlier Vite chunk-size warning is no longer emitted in the current verified build
- Current verified `npm audit` status is **5 moderate / 0 high / 0 critical**, with the remaining issues tied to the `vitest` major-upgrade path

## Dev proxy behavior

The Vite dev server proxies these backend surfaces:

| Frontend path | Backend target |
| --- | --- |
| `/api` | `http://localhost:8000` |
| `/v1` | `http://localhost:8000` |
| `/ws` | `ws://localhost:8000` |

That means frontend code should prefer helpers from `src/api/client.js`:

- `apiUrl(path)`
- `openAIUrl(path)`
- `absoluteUrl(path)`
- `websocketUrl(path)`

## Routed pages

| Route | Component | Purpose |
| --- | --- | --- |
| `/` | `Dashboard.jsx` | System overview and hardware status |
| `/playground` | `Playground.jsx` | Interactive inference playground |
| `/models` | `Models.jsx` | Model registry and uploads |
| `/hub` | `ModelHub.jsx` | Hugging Face and model discovery flows |
| `/hf-publisher` | `HubPublisher.jsx` | Publishing workflow |
| `/datasets` | `Datasets.jsx` | Dataset browsing and management |
| `/ingestion` | `DataIngestion.jsx` | Upload, extraction, and dataset build tasks |
| `/serving` | `Serving.jsx` | OpenAI-compatible serving UI and chat test |
| `/training` | `Training.jsx` | Training job management |
| `/finetuning` | `FineTuning.jsx` | LoRA/QLoRA job controls |
| `/gguf-studio` | `GGUFStudio.jsx` | GGUF inspect / quantize / convert / split / merge |
| `/fastflowlm` | `FastFlowLM.jsx` | FastFlowLM runtime controls |
| `/conversion` | `Conversion.jsx` | Conversion and quantization workflows |
| `/scanner` | `Scanner.jsx` | Local model scanning and import |
| `/webcam` | `WebcamTest.jsx` | Webcam object detection UI |
| `/benchmark` | `Benchmark.jsx` | Benchmarking and system capability views |
| `/edge-fleet` | `EdgeFleet.jsx` | Edge device discovery and firmware operations |

## Shared frontend patterns

### API access

Use the shared helpers instead of embedding `http://localhost:8000` in page components.

Why:

- works in local dev with Vite proxy
- works more cleanly behind Docker or reverse proxies
- avoids protocol/host mismatches for WebSocket and OpenAI-compatible endpoints

### Reusable components

Important shared pieces include:

- `components/FolderBrowser.jsx` for file and folder selection
- `api/client.js` for fetch wrappers, URL helpers, FLM normalization, and training WebSocket handling

### Serving page

`pages/Serving.jsx` now uses:

- `openAIUrl('/models')`
- `openAIUrl('/models/status')`
- `openAIUrl('/chat/completions')`
- absolute snippet URLs derived from the current browser origin

### GGUF Studio

`pages/GGUFStudio.jsx` posts relative GGUF endpoints through `apiUrl()` and should avoid passing already-prefixed `/api/...` paths.

## Key dependencies

- `react`
- `react-router-dom`
- `lucide-react`
- `recharts`
- `vite`

## Practical maintenance guidance

- Keep route additions synchronized with `navItems` in `App.jsx`
- Prefer adding network logic to `api/client.js` when a pattern is shared across pages
- Keep new routed pages lazy-loaded unless there is a strong reason not to
- Validate UI-impacting refactors with `npm run build` before moving on
- Validate core page rendering with `npm run test` when route or client behavior changes
- Treat docs as stale until verified against live code; the current page map above is based on the checked-in frontend, not legacy documentation
