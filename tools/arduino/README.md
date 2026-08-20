# NPU-STACK — Baked-in Arduino toolchain (offline, self-contained)

NPU-STACK vendors its own `arduino-cli` + board cores so flashing supported
Arduino-compatible boards needs **no internet and no Arduino IDE**.

## What lives here (gitignored — local only)

| Path | Contents | Size |
| --- | --- | --- |
| `arduino-cli.exe` | arduino-cli binary (vendored) | ~40 MB |
| `data/packages/realtek/hardware/AmebaPro2/4.1.0/` | Realtek Ameba Pro2 board package (AMB82-Mini) | — |
| `data/packages/realtek/tools/ameba_pro2_toolchain/` | RTL8735B GCC toolchain | ~600 MB |
| `data/packages/realtek/tools/ameba_pro2_tools/` | Realtek flash tools | — |
| `data/package_realtek_amebapro2_index.json` | Realtek package index (offline) | 37 KB |

`config.yaml` (kept in git) points arduino-cli at these local dirs.

## Reproduce the vendored toolchain

On a machine with internet, once:

```powershell
# 1. arduino-cli (any recent version) into tools/arduino/arduino-cli.exe
# 2. Register the Realtek board package URL
& tools\arduino\arduino-cli.exe config add board_manager.additional_urls `
  https://github.com/Ameba-AIoT/ameba-arduino-pro2/raw/main/Arduino_package/package_realtek_amebapro2_early_index.json `
  --config-file tools\arduino\config.yaml

# 3. Install the core + toolchain into the local data dir
& tools\arduino\arduino-cli.exe core install realtek:AmebaPro2 `
  --config-file tools\arduino\config.yaml
```

After that, everything under `data/` is self-contained and works offline.

## Usage

```powershell
# Compile the AMB82-Mini Nirvana sketch (fully offline)
& tools\arduino\arduino-cli.exe compile `
  --config-file tools\arduino\config.yaml `
  --fqbn realtek:AmebaPro2:Ameba_AMB82-MINI `
  firmware\amb82-mini\amb82-nirvana-agent

# Upload to a connected board
& tools\arduino\arduino-cli.exe upload -p COM34 `
  --config-file tools\arduino\config.yaml `
  --fqbn realtek:AmebaPro2:Ameba_AMB82-MINI `
  firmware\amb82-mini\amb82-nirvana-agent
```

> Windows note: run with `LC_ALL=C` / `LANG=C` (or from the backend, which sets
> them automatically) to avoid an arduino-cli `std::locale` crash.

The backend `POST /api/devices/{id}/flash-arduino` uses this baked toolchain
automatically.
