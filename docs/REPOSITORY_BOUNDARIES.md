# Repository boundaries

NPU-STACK is the public application and orchestration product. It creates the
management experience, backend services, device contracts, compatibility
metadata, and build/deployment integrations used to develop and operate the
Nirvana product family.

## Product relationship

The projects are related, but they are not one source tree:

```text
Private training project ── produces approved models/artifacts ──┐
                                                                  ├─> NPU-STACK
Private Nirvana OS repo ── produces internal device firmware ─────┘
Public firmware/catalog repo ── produces approved board builds ───┘
```

All of these products are made by and for the NPU-STACK ecosystem. Separate
repositories are an access and release boundary, not a separation of ownership
or product direction.

## What belongs in public NPU-STACK

- React frontend, FastAPI backend, API contracts, emulators, and tests.
- Public documentation and compatibility metadata for supported boards.
- General-purpose build, provisioning, OTA, fleet, and firmware-integration
  interfaces.
- Public firmware sources or board adapters only after they are deliberately
  approved for publication and contain no internal credentials, device data,
  private calibration assets, or unreleased product logic.
- Small, redistributable sample datasets and examples.

## What does not belong in public NPU-STACK

- Internal Nirvana OS firmware and device-specific application bundles.
- Firmware binaries, calibration files, board dumps, or test images intended
  only for our internal devices.
- Private training data, scraped data, annotations, training runs, checkpoints,
  and unreleased model artifacts.
- Secrets, personal device identifiers, Wi-Fi credentials, backend tokens, or
  private deployment configuration.

Those materials belong in the appropriate private Nirvana OS or training
project. The local checkout may contain ignored working copies for development,
but ignored does not mean releasable or safe to publish.

## Public board compatibility strategy

The public release path should support the XiaoZhi-compatible board ecosystem
as a general-purpose baseline. Board selection, board type, pin maps, feature
flags, voice-service settings, and build options belong in public manifests and
UI contracts. A generated build is publishable only when its board support,
licenses, dependencies, and capabilities have been verified.

Nirvana OS is the internal touch-first/device-specific implementation. Its
hardware work can inform public compatibility contracts, but internal firmware
is not copied into the public repository by default.

## Change-control rules

- Work on `dev`; merge audited public changes to `main`.
- Do not stage `internal/`, `firmware/nirvana-os/`, local device outputs, or
  training artifacts with broad `git add -A` commands.
- Before publishing firmware or datasets, explicitly classify the material as
  public, private, or release-gated and verify that credentials and device data
  are absent.
- Public NPU-STACK code may reference a separate firmware release URL or API
  contract; it must not require private source paths to build or test.
