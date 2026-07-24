# Repo Cleanup Matrix — 2026-05-28

This file classifies the currently visible local-only changes into three buckets:

- **Safe to ignore/delete**
- **Keep and commit**
- **Probably move out of repo / decide intentionally**

## Safe to ignore/delete

These are editor/session residue or machine-local artifacts and should not drive product decisions.

### Confirmed noise

- `.vs/`
- `.thumbnails/`
- `NPU-STACK.code-workspace`
- `hardware_results.json`

### Action

- Ignore in Git: **done for the items above in this session** via `.gitignore`
- Safe to delete locally if not needed

## Keep and commit

These are real app changes or repo documentation produced from this analysis.

### Real modified source files

- `backend/main.py`
- `backend/requirements.txt`
- `backend/routers/serving.py`
- `backend/services/benchmark_service.py`
- `frontend/src/App.jsx`
- `frontend/src/api/client.js`
- `frontend/src/index.css`
- `frontend/src/pages/Dashboard.jsx`
- `frontend/src/pages/FineTuning.jsx`

### Real untracked feature work

#### FastFlowLM

- `backend/routers/flm.py`
- `backend/services/flm_service.py`
- `frontend/src/pages/FastFlowLM.jsx`

#### Edge Fleet

- `backend/routers/devices.py`
- `backend/services/edge_discovery.py`
- `frontend/src/pages/EdgeFleet.jsx`

### Documentation generated this session

- `docs/STATUS_REPORT_2026-05-28.md`
- `docs/MOVING_FORWARD_DIRECTIVE.md`
- `docs/REPO_CLEANUP_MATRIX_2026-05-28.md`

### Commit strategy

- Keep staged separately from noise cleanup
- Prefer feature-focused commits:
  - one commit for FLM stabilization
  - one commit for Edge Fleet stabilization
  - one commit for docs / cleanup hygiene

## Probably move out of repo / decide intentionally

These are not obviously junk, but they need an explicit ownership decision before committing on `main`.

### Candidate local additions

- `assets/`
- `compositions/`
- `firmware/`
- `setup-edge-fleet.bat`
- `start-all.bat`
- `start-backend.bat`
- `start-frontend.bat`
- `test_escape.bat`
- `test_hardware.py`
- `test_quote.bat`

### Why these need a decision

They may be legitimate support files, but today they look like one of:

- local experimentation
- environment/bootstrap helpers
- content/demo assets
- hardware-lab support

They should be committed only if they are part of the intended product/repo contract.

### Recommendation

- If needed for all contributors: **document and commit**
- If only needed for one workstation / lab: **move to a local tools repo or ignored folder**
- If they support a feature area, group them under a documented top-level folder with a README

## Nested Git repositories under `libraries/`

Confirmed in this session: each of these contains its own `.git` directory.

- `libraries/kauldron`
- `libraries/rocm-libraries`
- `libraries/RyzenAI-SW`
- `libraries/unsloth`

## Recommendation for `libraries/`

Do **not** commit these blindly as ordinary repo contents.

Choose one intentional strategy:

1. **Submodules** if this repo is meant to reference exact upstream revisions
2. **External prerequisites** if contributors are expected to clone/fetch separately
3. **Vendored sources** only if long-term maintenance responsibility is accepted

### Current recommendation

Best default: treat them as **documented external dependencies**, not incidental untracked content on `main`.

If this repo later needs pinned upstream revisions in-tree, promote them to **submodules** intentionally rather than committing nested Git repositories by accident.

## Next-sprint cleanup order

1. Commit `.gitignore` hygiene and docs
2. Isolate FLM + Edge Fleet feature work from unrelated files
3. Keep frontend API access on shared helpers and prevent regressions
4. Expand smoke coverage beyond backend GET endpoints into frontend empty-state rendering
5. Implement the chosen `libraries/` documentation strategy before any commit that touches nested repos
