# Unified Runtime Compatibility Roadmap (NPU-STACK)

## Mission

NPU-STACK must act as a **compatibility fabric**, not a collection of isolated pages.

That means one user flow across:

- Devices (CPU, GPU, NPU)
- Frameworks/runtimes (native API, FastFlowLM, Unsloth workflows, others)
- Models (registry, remote IDs/URLs, local paths)
- Data (datasets, prep, train, test, eval)
- Serving (runtime-aware deployment)

## Product Rules (non-negotiable)

1. **Single Chat & Playground UX is primary** for inference testing.
2. Integrated repos (FastFlowLM, Unsloth, etc.) should appear as **runtime capabilities** in the same UX.
3. Runtime/device selection must dynamically constrain model options.
4. Dedicated pages (like FastFlowLM) remain as advanced workbenches, not the only entry point.
5. All compatibility logic must be testable and versioned.

---

## Current State (after this change set)

### ✅ Completed now

- Fixed Dashboard parser regression (`Dashboard.jsx`) caused by orphaned tokens.
- Added unified compatibility controls in `ChatPlayground`:

  - Device target selector (`auto/cpu/gpu/npu`)
  - Runtime selector (`auto/native/fastflowlm`)
  - Model reference input (ID/tag/path)
  - Inline FastFlowLM controls when runtime is NPU/FLM:

    - select FLM model
    - serve model
    - stop server

- Direct chat path now routes to FastFlowLM stream chat when FLM runtime selected.
- Playground text generation now routes to FastFlowLM when FLM runtime selected.
- Native path accepts selected model **or typed model reference**.

### ⚠️ Gaps still open

- Compatibility matrix is currently heuristic in frontend; needs backend source of truth.
- Model metadata is not yet normalized for strict device/runtime compatibility.
- Unsloth chat/fine-tune runtime exposure in the same selection surface is pending.
- Unified serving selector still needs runtime adapters beyond FastFlowLM/native.

---

## Phase Plan

### Phase 1 — Compatibility Source of Truth (Backend)

Create backend capability contract:

- Endpoint: `GET /api/compatibility/matrix`
- Returns:

  - detected hardware (cpu/gpu/npu classes)
  - installed runtimes (fastflowlm, native, llama.cpp, etc.)
  - model compatibility predicates by runtime+device
  - unsupported reason codes (`missing_driver`, `runtime_not_installed`, `model_arch_mismatch`)

Deliverables:

- Typed response schema
- Unit tests for matrix generation
- Mapping from `benchmark/system-info` + runtime probes

### Phase 2 — Unified Model Selection Contract

Model identity pipeline:

- Resolve model source from:

  - registered model ID
  - remote model identifier/URL
  - local path

- Normalize model metadata into common shape:

  - `architecture`, `format`, `quantization`, `context`, `runtime_support`, `device_support`

Deliverables:

- `resolve_model_reference()` service
- server-side validation endpoint
- clear user-facing errors for incompatible choices

### Phase 3 — Runtime Adapter Layer

Standardize runtime adapters with shared interface:

- `check_health`
- `list_models`
- `can_run(model, device)`
- `serve(model, device)`
- `chat(messages, params)`
- `stop()`

Initial adapters:

- Native inference adapter (existing)
- FastFlowLM adapter (existing logic wrapped into interface)
- Unsloth adapter surface for supported inference/fine-tune flows

Deliverables:

- Adapter registry
- Runtime fallback strategy (`auto` mode)
- Adapter integration tests

### Phase 4 — Unified Chat & Playground UX Hardening

UI rules:

- Device selection filters runtime list.
- Runtime selection filters model options.
- Incompatible selections show explicit reason + remediation CTA.
- Serving controls appear contextually in one panel.

Deliverables:

- Unified inference sidebar finalization
- Runtime badges + reason codes
- visual regression tests for key combinations

### Phase 5 — End-to-End Compatibility Test Matrix

Matrix examples:

- CPU + native + GGUF
- GPU + native + ONNX/PyTorch
- NPU + FastFlowLM + compatible FLM tag
- NPU selected but no NPU drivers
- model supplied by URL that is runtime-incompatible

Deliverables:

- automated integration tests
- smoke checks in CI
- compatibility report artifact per commit

---

## GAIA Integration Direction (Research-Backed)

From upstream GAIA docs/releases:

- GAIA provides hardware requirement validation, MCP integration, and local agent workflows.
- Viable integration strategy for NPU-STACK:

  1. treat GAIA as optional orchestrator/runtime integration plugin
  2. consume GAIA capabilities through adapter pattern (not hardwire UX assumptions)
  3. expose GAIA-backed runtimes in the same device/runtime/model selector

## windows-mcp Integration Direction (Research-Backed)

From windows-mcp docs/security:

- Supports `stdio`, `sse`, and `streamable-http` transports.
- Strong security requirements for remote deployment (auth key/OAuth + TLS + IP allowlist).
- High-risk tools (PowerShell, Click, Type, etc.) need explicit policy controls.

NPU-STACK recommendation:

- Default to local `stdio` mode for single-machine.
- For remote control: require auth + TLS + allowlist.
- Add allow/deny tool policy profile in orchestration before enabling remote mode.

---

## Risk Controls

- Do not enable destructive MCP tools by default in remote mode.
- Do not auto-execute runtime switching without explicit user intent.
- Preserve graceful fallback to native runtime when FastFlowLM unavailable.
- Keep compatibility errors actionable, not generic.

---

## Immediate Next Implementation Steps

1. Add `/api/compatibility/matrix` backend endpoint.
2. Move frontend compatibility heuristics to backend-driven rules.
3. Add runtime adapter abstraction for native + FastFlowLM.
4. Add Unsloth adapter stub and expose in unified selector.
5. Add CI integration tests for CPU/GPU/NPU routing paths.
