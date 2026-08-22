# Sensor & Pin Inventory — XIAO ESP32-S3 Sense + Round Display carrier

Authoritative hardware reference for the NPU-STACK edge boards. Verified against
the Seeed wiki (`xiao_esp32s3_getting_started` + `seeedstudio_round_display_usage`)
and on-device probing (`board.detect()`, I2C scan, ADC reads).

## Board stack

- **MCU board:** Seeed XIAO ESP32-S3 **Sense** — ESP32-S3R8, 8 MB PSRAM, 8 MB flash.
- **Carrier:** Seeed **Round Display for XIAO** (1.28", 240×240 GC9A01, touch, RTC, TF slot).

## Pin map (XIAO D-label → GPIO → function on this stack)

| D-label | GPIO | Used by | Notes |
| --- | --- | --- | --- |
| D0 / A0 | 1 | **Touch reset** (CHSC6X, active-low) + **battery divider** | Shared net — see conflict note |
| D1 | 2 | Display CS (GC9A01) | |
| D2 | 3 | SD card CS (TF slot) | |
| D3 | 4 | Display DC (GC9A01) | |
| D4 (SDA) | 5 | Touch + RTC I2C data | CHSC6X @0x2E, PCF8563 @0x51 |
| D5 (SCL) | 6 | Touch + RTC I2C clock | |
| D6 | 43 | Display backlight (BL) | KE switch "backlight" function |
| D7 | 44 | Touch interrupt (INT, active-low) | |
| D8 | 7 | SPI SCK (display + SD share) | |
| D9 | 8 | SPI MISO | |
| D10 | 9 | SPI MOSI | |
| D11 | 42 | PDM mic clock | Sense expansion board |
| D12 | 41 | PDM mic data | Sense expansion board |
| — | 21 | User LED (active-low) | on-board |

Camera (OV2640/OV3660/OV5640) rides a **dedicated SCCB I2C bus** (addr 0x30) on
the Sense expansion board — it is **not** on the user SDA/SCL pins and is not
visible to `i2c.scan()`.

## Sensor inventory

| Sensor | Where | Status | `sensors.*` |
| --- | --- | --- | --- |
| GC9A01 display | carrier | ✅ working | (via `display`) |
| CHSC6X touch | carrier, I2C 0x2E | ✅ working | (via `touch`) |
| PCF8563 RTC | carrier, I2C 0x51 | ✅ present, time unset until NTP/coin cell | `rtc()` → ISO or None |
| microSD | carrier TF slot, CS=GPIO3 | ✅ mounted at `/sd` | (via `sd`) |
| OV2640/OV3660 camera | Sense board, SCCB | ✅ present (driver pending) | `camera()` → `{present: True}` |
| PDM mic | Sense board, GPIO41/42 | ⚠️ **blocked** (see below) | `mic()` → 0 |
| Battery divider | carrier, A0/D0=GPIO1 | ⚠️ **conflicts with touch** (see below) | `battery_mv()` → best-effort |
| Internal temp | ESP32-S3 die | ✅ working (~44 °C) | `temp_c()` |
| IMU (accel/gyro) | **none** on S3 Sense | ❌ absent | `imu()` → None |
| Ambient light | **none** | ❌ absent | `light()` → None |

## PDM mic — blocked in stock MicroPython

The onboard mic is a **PDM** digital mic (data GPIO41, clock GPIO42). Stock
MicroPython (1.28) has **no PDM-RX I2S mode** — the feature is unmerged upstream
(micropython/micropython PR **#14176**). A 1 MHz PDM clock cannot be bit-banged
from Python.

Options to unlock real mic level:

1. Build MicroPython with the PDM-RX patch (ESP-IDF I2S PDM support), or
2. Read PDM from C on ESP-IDF and expose it to MicroPython, or
3. Swap to an I2S mic on the free pins (below) — standard `machine.I2S` RX works.

Until then `face.alive()` falls back to a breathing/talking pattern so the idle
face stays animated without live audio.

## Battery divider — shared pin conflict

The carrier's LiPo divider is on **A0/D0 = GPIO1**, the same net as the CHSC6X
**touch reset** (active-low; must stay driven HIGH for the touch controller to
run — releasing it to high-Z stops the controller answering I2C). Therefore:

- While the menu/touch driver is active, GPIO1 is driven HIGH → `battery_mv()`
  reads ~3.3 V regardless of cell, and with no cell attached reads ~0.15 V.
- `battery_pct()` returns `None` for implausible readings (see
  `sensors.py` `BAT_SHARED_WITH_TOUCH`).
- Reliable battery % needs either the KE switch on a different pin, a dedicated
  ADC divider on a free pin, or powering the board through the carrier while the
  touch driver is not holding GPIO1.

Seeed's reference calibration (divider ADC, not true cell volts):
`BAT_DEFICIT_VOL = 1850 mV`, `BAT_FULL_VOL = 2450 mV`,
`pct = (mv - 1850) * 100 / (2450 - 1850)`.

## Speaker / audio output guidance

The S3 Sense has **no DAC** — audio out requires an external **I2S DAC/amp**
(e.g. MAX98357A) + speaker.

Free pins for I2S (after everything above is claimed):

- **Free GPIOs:** 0 (BOOT — usable, strapping), 10, 11, 12, 13, 14, 15, 16, 17, 18, 33, 34, 35, 36, 37, 39, 40, 45, 46, 47, 48.
- **Recommended I2S wiring** (MAX98357A): BCLK → GPIO11, LRC → GPIO12, DIN → GPIO13, plus 3V3/GND. (GPIO0 is a strapping pin; avoid unless needed.)
- Keep I2S off the used nets: camera (10–18, 38–48 on the Sense B2B), PDM (41/42), SD (3/7/8/9), display SPI (7/8/9/2/4/43), touch/RTC I2C (5/6), UART (43/44).
- **Physical caveat:** every D0–D10 header pin is consumed by the carrier; the
  three I2S pins above live on the **B2B camera connector** pads, so they're only
  reachable if the camera expansion is removed (or via a breakout/second board).

**Firmware landed** — `firmware/nirvana-os/audio.py` (`init/tone/beep/play_wav/
say`). Verified on-device: `machine.I2S` TX on GPIO11/12/13 initialises and
`audio.tone(440, 20)` writes PCM cleanly — sound will play once the amp is wired.
Emulator parity: `machine.I2S` is stubbed in `backend/emulator/shim.py` (captures
writes) so `audio.py` is testable in the playground.

## RTC notes

PCF8563 @ 0x51, BCD registers at 0x02–0x08, coin cell (CR927) keeps time.
`rtc()` returns `None` until the time is set (blank chip reads garbage and is
rejected). Set it once via NTP (ESP32 has network) and it persists on the cell.

## Emulator parity

`backend/emulator/shim.py` stubs the same `sensors` API (`rtc/mic/battery_mv/
temp_c/light/imu/camera`) plus injectable `accel_xyz/gyro_xyz` for IMU-driven
gaze work before hardware exists. It also stubs `bluetooth` + `espnow`, so the
provisioning modules (`improv_ble`, `espnow_pair`) run unchanged in the
playground — inject an IMPROV RPC via `BLE:<hex>` and an offer via
`ESPNOW:<mac>,<msg>` on the runner stdin (covered by
`tests/test_emulator_provisioning.py`).
