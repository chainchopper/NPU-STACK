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
| NirvanaChat | `NirvanaChat.jsx` | **Full Nirvana agent interface** — iframe-embedded WebUI with all features |

## Work Guidance

- The Agents page is the primary Nirvana interface — any absorption of Hermes WebUI panels (chat, sessions, settings, skills, cron, kanban, memory) should integrate into or alongside this page
- React components for Hermes WebUI features should wrap the vanilla JS modules from `hermes-webui/static/` using a thin event bus (`window.__nirvanaBus`)
- Namespace all absorbed Hermes CSS under a `.nirvana-ui` class to avoid conflicts
- Keep NPU-STACK React conventions: functional components, hooks, nanostores for shared state

## Shared Components

| Component | File | Purpose |
| --- | --- | --- |
| `ChatInterface` | `components/ChatInterface.jsx` | Shared chat UI used across chat/playground/agents |
| `SystemAgent` | `components/SystemAgent.jsx` | System agent status display |
| `AgentVisual` | `components/AgentVisual.jsx` | Agent visualization/animation |
| `ModelSelector` | `components/ModelSelector.jsx` | Reusable model picker dropdown |
| `DatasetSelector` | `components/DatasetSelector.jsx` | Reusable dataset picker |
| `LoRASelector` | `components/LoRASelector.jsx` | LoRA adapter picker |
| `FolderBrowser` | `components/FolderBrowser.jsx` | File/folder tree browser |
| `ContextWizard` | `components/ContextWizard.jsx` | Multi-step configuration wizard |
| `EnhancedTrainingSetup` | `components/EnhancedTrainingSetup.jsx` | Training configuration form |
| `ActivityLogCard` | `components/ActivityLogCard.jsx` | Activity log card display |
| `CapabilityPill` | `components/CapabilityPill.jsx` | Capability tag/badge |
| `OperationNotice` | `components/OperationNotice.jsx` | Operation status notice banner |

## Verification

- Dev server: `npm run dev` from `frontend/`
- Build check: `npm run build`
- The Agents page should show bridge status, session list, and working chat
- All management pages should load without console errors

## Child DOX Index

No child boundaries yet. Source structure:

| Path | Purpose |
| --- | --- |
| `src/api/` | API client utilities and request helpers |
| `src/components/` | 12 shared React components (see Shared Components above) |
| `src/context/` | React context providers (theme, auth, state) |
| `src/hooks/` | Custom React hooks |
| `src/pages/` | 25 route-level page components (see Page Index above) |
| `src/styles/` | Additional style modules |
| `src/nirvana-webui/` | Absorbed Hermes WebUI static files — JS modules, CSS, vendor libs, favicons. Phase 1 uses iframe embedding; Phase 2 will mount modules directly. |
| `src/test/` | Frontend test utilities |
| `src/__tests__/` | Jest/Vitest test suites |
| `src/App.jsx` | Root app component with router |
| `src/main.jsx` | React entry point |
| `src/index.css` | Global stylesheet (NPU-STACK theme) |
