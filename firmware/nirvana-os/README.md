# Nirvana OS — MicroPython (XIAO ESP32-S3 Sense)

Branded MicroPython firmware for the NPU-STACK fleet. The application layer
(boot.py + main.py + config.json) runs on top of the stock MicroPython
ESP32-S3 image.

## Files

| File | Purpose |
|------|---------|
| `boot.py` | Clock + hostname (runs first) |
| `main.py` | Nirvana OS app — WiFi, heartbeat, OTA, setup menu |
| `config.json` | Runtime config (WiFi, backend, device id, OTA channel). **gitignored** — real creds stay local |
| `config.example.json` | Safe template (empty creds) |
| `version.json` | OTA manifest served from the update channel |

## Flash

```powershell
# from repo root, with the venv active
python scripts/flash_nirvana_os.py --port COM4
```

1. Hold the XIAO's **BOOT** button, plug in USB, release BOOT (download mode).
2. The script erases flash, writes `ESP32_GENERIC_S3-20260406-v1.28.0.bin`,
   then uploads `boot.py` / `main.py` / `config.json`.
3. Reopen the serial REPL at 115200 baud — you should see the Nirvana OS banner.

## First-run config

Without a saved `config.json`, the device drops to a serial setup prompt:

```
SSID: <type your network>
Password: <type your password>
```

Or pre-create `firmware/nirvana-os/config.json` (copy the example) and re-run the
flash script — it uploads the real `config.json` when present.

## OTA

Set `update_channel` in `config.json` to a URL that serves `version.json` +
`main.py` (e.g. a GitHub raw path or the NPU-STACK `/api/fleet/ota` endpoint).
On boot, Nirvana OS fetches `version.json`; if `version` differs from the
running `VERSION`, it downloads the new `main.py`, writes it to flash, and reboots.

## Roadmap

- [x] v0.1 — boot, WiFi, heartbeat, OTA scaffold, serial setup
- [ ] v0.2 — MQTT fleet registration + commands (bundled MiniMQTT)
- [ ] v0.3 — xiaozhi MQTT+UDP / WebSocket voice client
- [ ] v0.4 — app-store marketplace + home-screen menus (BLE/WiFi provisioning)
