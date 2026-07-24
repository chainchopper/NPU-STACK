# NPU-STACK Moving Forward Directive

## Direction

Do **not** add more major feature surfaces until the current platform is stabilized.

The best next phase is **consolidation over expansion**.

The repository already has enough breadth. The bottleneck is now **consistency, contract stability, and proof that core flows really work**.

## Immediate priority order

### 1. Stabilize frontend/backend contracts

Treat this as the top priority.

Required actions:

- Move pages toward the shared API client instead of ad hoc `fetch()` calls.
- Remove hardcoded `http://localhost:8000` usage from runtime API calls where proxy-relative paths are appropriate.
- Normalize backend responses or adapter layers so UI pages consume stable shapes.
- Add a lightweight contract checklist for these pages first:
  - `Dashboard`
  - `Serving`
  - `FineTuning`
  - `FastFlowLM`
  - `EdgeFleet`
  - `ModelHub`
  - `DataIngestion`

### 2. Add app-specific smoke tests

Create a small, boring, trustworthy smoke suite.

Minimum backend smoke coverage should verify:

- app import
- `/api/health`
- `/api/status`
- `/v1/models`
- `/v1/models/status`
- `/api/benchmark/system-info`
- `/api/finetune/jobs`
- `/api/flm/status`
- `/api/devices`

Minimum frontend verification should cover:

- app routes render without crashing
- main sidebar navigation works
- critical pages handle empty-state responses without errors

### 3. Refresh documentation to match reality

Update these first:

- `README.md`
- `docs/BACKEND.md`
- `docs/FRONTEND.md`

The docs must clearly separate:

- implemented and validated
- implemented but environment-dependent
- partially implemented / placeholder

Do not market a feature as complete unless it has been validated end-to-end.

### 4. Consolidate API access patterns

Adopt one frontend rule:

> New pages do not call the backend directly with hardcoded origins unless there is a very explicit reason.

Instead:

- use the shared API client
- centralize response normalization
- centralize error handling

This will prevent the exact drift I fixed in this session.

### 5. Reduce frontend bundle size

After stability work begins, split the biggest routes with lazy loading.

Best candidates:

- `GGUFStudio`
- `FastFlowLM`
- `EdgeFleet`
- `ModelHub`
- `WebcamTest`

### 6. Clean repo hygiene before feature expansion

Treat repository cleanliness as engineering work, not cosmetic work.

Immediate cleanup actions:

- ignore editor/session residue such as `.vs/`, `.thumbnails/`, and local workspace files
- keep real feature work separate from machine-local artifacts
- classify support scripts, test helpers, assets, and firmware files before committing them on `main`
- avoid mixing docs, cleanup, and feature work in one giant commit

### 7. Decide how `libraries/` is supposed to work

The nested directories under `libraries/` are separate Git repositories, not ordinary source folders.

Do not commit them casually as if they were normal project files.

Pick one explicit strategy:

- submodules
- documented external prerequisites
- intentionally vendored dependencies

**Recommended default for this repository right now:**

- treat `libraries/` as **documented external prerequisites**
- do **not** absorb nested `.git` trees into the main repo accidentally
- move to **submodules** only if the project truly needs exact upstream revision pinning inside this workspace

Until an implementation pass happens, treat `libraries/` as a separate repository-management concern.

## Definition of “done” for the next phase

The next stabilization phase should be considered complete only when:

- the main frontend pages use consistent API access patterns
- critical backend routes have smoke coverage
- docs match the current app surface
- bundle warnings are reduced or consciously accepted
- the newer pages no longer depend on guessed response shapes
- editor/session residue is not polluting normal repo status
- `libraries/` handling is documented intentionally

## What was already executed in this session

The following cleanup work has already started:

- FastFlowLM client payload normalization
- FastFlowLM SSE pull parsing fix
- Edge Fleet backup response rendering fix
- Edge Fleet RP2040 response handling fix
- Fine-Tuning job detail endpoint fix
- Shared frontend API helper migration across major pages
- Hardcoded frontend localhost origins replaced with proxy-safe relative paths
- `Serving.jsx` repaired after refactor corruption
- `GGUFStudio.jsx` endpoint double-prefix bug fixed
- Backend smoke suite added at `tests/test_backend_smoke.py` and verified passing
- `README.md`, `docs/BACKEND.md`, and `docs/FRONTEND.md` refreshed against actual code

## Recommended rule for future work

Before adding any new feature page or router:

1. define the response shape
2. wire it through the shared client
3. add a smoke check
4. update docs
5. only then expand the feature surface

That order will save this project from becoming a beautiful maze with trapdoors.
