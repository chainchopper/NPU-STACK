# frontend/ — NPU-STACK Frontend

## Purpose

React/Vite SPA providing the management shell for NPU-STACK: dashboard, model registry, training UI, conversion tools, fleet operations, the Nirvana agent interface, and 25+ tool pages. This is also the target for absorbing the Hermes WebUI's chat/sessions/settings/panels into a unified Nirvana experience.

## Ownership

This is an active development boundary. All UI changes go here.

## Local Contracts

- Dev server runs on port `5177` (Vite default)
- Proxies `/api` → `http://127.0.0.1:8010` (NPU-STACK backend)
- React Router for SPA navigation
- Dark theme by default, light toggle available
- Nirvana is the built-in orchestration agent — distinct from chat/playground/test interfaces
- The Agents page (`Agents.jsx`) is the primary Nirvana control surface

## Page Index

| Page | File | Purpose |
| --- | --- | --- |
| Dashboard | `Dashboard.jsx` | System overview, status cards, quick actions |
| Models | `Models.jsx` | Model registry browser, upload, download |
| Training | `Training.jsx` | Training job configuration and monitoring |
| Conversion | `Conversion.jsx` | Model format conversion tools |
| Benchmark | `Benchmark.jsx` | Performance benchmarking |
| FineTuning | `FineTuning.jsx` | Fine-tuning workflow |
| HubPublisher | `HubPublisher.jsx` | Publish models to HuggingFace |
| GGUFStudio | `GGUFStudio.jsx` | GGUF quantization and conversion |
| Datasets | `Datasets.jsx` | Dataset management |
| DataIngestion | `DataIngestion.jsx` | Data ingest pipelines |
| Scanner | `Scanner.jsx` | Hardware/GPU scanner |
| Serving | `Serving.jsx` | Inference serving configuration |
| Playground | `Playground.jsx` | Interactive model playground |
| Chat | `Chat.jsx` | Basic chat interface |
| ChatPlayground | `ChatPlayground.jsx` | Advanced chat playground |
| Agents | `Agents.jsx` | **Nirvana control center** — profiles, sessions, bridge panel, transcript |
| Orchestration | `Orchestration.jsx` | Nirvana identity, MCP config, runtime settings |
| EdgeFleet | `EdgeFleet.jsx` | Fleet device management |
| FleetCommand | `FleetCommand.jsx` | Fleet command dispatch |
| FastFlowLM | `FastFlowLM.jsx` | FastFlowLM inference UI |
| AdvancedTraining | `AdvancedTraining.jsx` | Advanced training configuration |
| AutoResearch | `AutoResearch.jsx` | Automated research tools |
| Documentation | `Documentation.jsx` | Embedded documentation browser |
| WebcamTest | `WebcamTest.jsx` | Webcam/camera testing |
| ModelHub | `ModelHub.jsx` | Model discovery hub |

## Work Guidance

- The Agents page is the primary Nirvana interface — any absorption of Hermes WebUI panels (chat, sessions, settings, skills, cron, kanban, memory) should integrate into or alongside this page
- React components for Hermes WebUI features should wrap the vanilla JS modules from `hermes-webui/static/` using a thin event bus (`window.__nirvanaBus`)
- Namespace all absorbed Hermes CSS under a `.nirvana-ui` class to avoid conflicts
- Keep NPU-STACK React conventions: functional components, hooks, nanostores for shared state

## Verification

- Dev server: `npm run dev` from `frontend/`
- Build check: `npm run build`
- The Agents page should show bridge status, session list, and working chat
- All management pages should load without console errors

## Child DOX Index

No child boundaries yet. Components live under `src/components/`, pages under `src/pages/`.
