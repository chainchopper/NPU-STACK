# DOX framework

- DOX is highly performant AGENTS.md hierarchy installed here
- Agent must follow DOX instructions across any edits

## Core Contract

- AGENTS.md files are binding work contracts for their subtrees
- Work products, source materials, instructions, records, assets, and durable docs must stay understandable from the nearest applicable AGENTS.md plus every parent AGENTS.md above it

## Working Directives

### Verify Code Landed

- "Code written" is not "code landed". Device/firmware work is only DONE when the change is proven to land: compiled clean, flashed, and (where possible) observed running on the device.
- Every completion report must state exactly what happened — compiled ✓ / flashed ✓ / observed running ✓. If flashing or observation was not possible (no device attached, no control path), say so explicitly; never claim a feature works from code changes alone.
- No feature on a device (AMB82, ESP32, CircuitPython, MicroPython, etc.) may be reported as "done" without evidence it landed.

### Plan & Track

- Break multi-step work into a todo list up front and keep it updated (in-progress → completed) as steps finish.
- Mark one todo in-progress at a time; complete it before moving on.
- For device/firmware tasks, the final todo must be the "verify it landed" step.

## Read Before Editing

1. Read the root AGENTS.md
2. Identify every file or folder you expect to touch
3. Walk from the repository root to each target path
4. Read every AGENTS.md found along each route
5. If a parent AGENTS.md lists a child AGENTS.md whose scope contains the path, read that child and continue from there
6. Use the nearest AGENTS.md as the local contract and parent docs for repo-wide rules
7. If docs conflict, the closer doc controls local work details, but no child doc may weaken DOX

Do not rely on memory. Re-read the applicable DOX chain in the current session before editing.

## Update After Editing

Every meaningful change requires a DOX pass before the task is done.

Update the closest owning AGENTS.md when a change affects:

- purpose, scope, ownership, or responsibilities
- durable structure, contracts, workflows, or operating rules
- required inputs, outputs, permissions, constraints, side effects, or artifacts
- user preferences about behavior, communication, process, organization, or quality
- AGENTS.md creation, deletion, move, rename, or index contents

Update parent docs when parent-level structure, ownership, workflow, or child index changes. Update child docs when parent changes alter local rules. Remove stale or contradictory text immediately. Small edits that do not change behavior or contracts may leave docs unchanged, but the DOX pass still must happen.

## Hierarchy

- Root AGENTS.md is the DOX rail: project-wide instructions, global preferences, durable workflow rules, and the top-level Child DOX Index
- Child AGENTS.md files own domain-specific instructions and their own Child DOX Index
- Each parent explains what its direct children cover and what stays owned by the parent
- The closer a doc is to the work, the more specific and practical it must be

## Child Doc Shape

- Create a child AGENTS.md when a folder becomes a durable boundary with its own purpose, rules, responsibilities, workflow, materials, or quality standards
- Work Guidance must reflect the current standards of the project or user instructions; if there are no specific standards or instructions yet, leave it empty
- Verification must reflect an existing check; if no verification framework exists yet, leave it empty and update it when one exists

Default section order:
- Purpose
- Ownership
- Local Contracts
- Work Guidance
- Verification
- Child DOX Index

## Style

- Keep docs concise, current, and operational
- Document stable contracts, not diary entries
- Put broad rules in parent docs and concrete details in child docs
- Prefer direct bullets with explicit names
- Do not duplicate rules across many files unless each scope needs a local version
- Delete stale notes instead of explaining history
- Trim obvious statements, repeated rules, misplaced detail, and warnings for risks that no longer exist

## Closeout

1. Re-check changed paths against the DOX chain
2. Update nearest owning docs and any affected parents or children
3. Refresh every affected Child DOX Index
4. Remove stale or contradictory text
5. Run existing verification when relevant
6. Report any docs intentionally left unchanged and why

## User Preferences

- **Nirvana** is the agent's name — never call it "Hermes" in user-facing text, UI, or documentation. The upstream repos (`hermes-agent/`, `hermes-webui/`) exist as absorbed reference implementations; the agent persona is ALWAYS Nirvana.
- Nirvana is the built-in system orchestration intelligence — it sits ABOVE all other chat/playground/test interfaces in the NPU-STACK UI.
- DeepSeek is the preferred provider for Nirvana. Local GGUF/Phi-3 is recovery-only fallback.
- Never modify the `.env` file locally without explicit approval.
- Push to GitHub frequently — after every validated slice of work.
- **Branch strategy**: `dev` is the primary development branch. `main` receives trickle-down merges from `dev` after audit. Never commit directly to `main` — always work in `dev` first. Sensitive/internal features stay in `dev` and are filtered before push to `main`.
- **internal/ folder**: Private NPU-STACK assets (training data, scrapers, proposals, internal docs) live in `internal/`. This folder is **gitignored** — never push to GitHub. Use `git add -A` with caution; prefer `git add <specific files>` to avoid accidentally staging internal/.
- **BACKUP BEFORE FLASH — MANDATORY**: Every device flash MUST be preceded by a full firmware backup. NO EXCEPTIONS. Use `GET /api/esp/fleet/backup` or the platform-specific backup method. If backup fails, STOP — do not proceed to flash. This is enforced in the flash endpoint (`backup_first=True`) but the agent must also enforce it at the planning/debugging level. The S3 Matrix game (accelerometer+gyroscope, running for years) was lost because this rule was violated. That never happens again.
- **NEVER format, delete, or write to ANY drive without explicit user approval**. Some devices expose SD cards or CIRCUITPY drives as Windows drive letters. These may be system drives or contain irreplaceable data. Detection/reading is fine — writing and formatting is forbidden without confirmation.
- Nirvana WebUI absorption: Phase 1 complete — proxy middleware (`backend/hermes_proxy.py`) forwards unmatched /api/* paths to absorbed WebUI at :8789. Frontend has /nirvana-chat route with iframe-embedded full WebUI. Agent icon opens Nirvana Chat directly. Phase 2 will mount vanilla JS modules directly.

## Child DOX Index

### Active Development Boundaries (own AGENTS.md)

| Path | AGENTS.md | Purpose |
|------|-----------|---------|
| `backend/` | ✅ exists | FastAPI server — all API routes, Nirvana bridge, model registry, training, fleet ops, inference |
| `frontend/` | ✅ exists | React/Vite SPA — management shell, agent interface, dashboard, 25+ tool pages |
| `mcp_temp_assets/servers/src/everything/` | ✅ exists | MCP "Everything" server — tools, resources, prompts, transports |

### Absorbed Upstream Repos (read-only reference, DO NOT EDIT)

| Path | AGENTS.md | Purpose |
|------|-----------|---------|
| `hermes-agent/` | ✅ exists | Upstream Hermes agent runtime — AIAgent, tools, skills, providers, plugins, CLI |
| `hermes-webui/` | ✅ exists | Upstream Hermes WebUI — vanilla JS chat UI, sessions, settings, panels, streaming |

### Documentation & Assets (no child AGENTS.md needed)

| Path | Purpose |
|------|---------|
| `docs/` | Project documentation — architecture, backend, frontend, Docker, status reports |
| `gitbook-npu-stack/` | NPU-STACK documentation source for GitBook publishing |
| `gitbook-clone/` | Upstream GitBook platform clone (absorbed for docs hosting) |
| `datasets/` | Training datasets for model fine-tuning |
| `compositions/` | HyperFrames video compositions (showcase, intros, overlays) |

### Edge & Firmware

| Path | Purpose |
|------|---------|
| `firmware/circuitpython-agent/` | CircuitPython agent for microcontrollers |
| `firmware/esp32-agent/` | ESP32 fleet agent firmware |
| `firmware/linux-agent/` | Linux edge device agent (systemd, OTA, polling) |
| `firmware/nirvana-os/` | Branded MicroPython firmware (Nirvana OS) for ESP32-S3 — XIAO Sense |

### Infrastructure & Build

| Path | Purpose |
|------|---------|
| `llama.cpp/` | Upstream llama.cpp (absorbed for GGUF inference backend) |
| `libraries/` | Shared C/C++ libraries for inference runtimes |
| `deploy/` | Self-hosted service deployment configs (xiaozhi voice server, etc.) |
| `scripts/` | Utility scripts (pruning, testing, setup automation) |
| `tests/` | Test suite |
| `web/` | Static landing page and API reference |
| `sandbox/` | Experimentation sandbox — not production, no contracts |
| `temp_unsloth_studio_inspect/` | Temporary inspection of Unsloth Studio (absorbed reference) |

### Root-Level Launchers & Config

| File | Purpose |
|------|---------|
| `setup.bat` / `setup.sh` | First-time project setup |
| `run-all.bat` / `run-all.sh` | Launch full stack (backend + frontend + services) |
| `run-backend.bat` / `run-backend.sh` | Launch backend only |
| `run-frontend.bat` / `run-frontend.sh` | Launch frontend only |
| `docker-compose.yml` | Container orchestration for services |
| `NPU-STACK.code-workspace` | VS Code multi-root workspace definition |
| `.env` | Environment variables (DO NOT MODIFY without approval) |
| `README.md` | Project overview and quick-start |