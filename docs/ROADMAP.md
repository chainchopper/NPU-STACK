# NPU-STACK Roadmap & Curated Backlog

Living planning doc for the NPU-STACK edge device workstreams. Kept here so
surprise add-ons / mods can be slotted in without losing track of the current
focus. Update statuses as work lands.

> Curated handoff 2026-08-21 — Seeed Round Display Animation Workshop + agent
> face/eyes references + audio/IMU notes. Do NOT lose these links.

---

## 1. Display performance (XIAO Round Display, GC9A01 240×240)

**Status:** Done (v1). MicroPython-adapted: big-endian framebuffer (no byte-swap),
80 MHz SPI, dirty-pixel incremental rendering, native (viper) fill.

Seeed's Animation Workshop found these phases (C/LVGL/ESP-IDF). Mapped to our
MicroPython reality:

| Workshop phase | Their result | Our equivalent status |
| --- | --- | --- |
| P1 baseline (SPI 20 MHz full refresh) | ~9 FPS | ✅ We were worse (~2 FPS) — Python byte-swap loop |
| P2 foundation (240 MHz + SPI 80 MHz + `-O3`) | ~15 FPS | ⚠️ CPU already 240 MHz; SPI now 40 MHz (80 is the S3 hardware ceiling); `-O3` is ESP-IDF-only |
| P3 double buffering / DMA | ~9 FPS (regression) | ❌ N/A in MicroPython (no DMA control) |
| P4 PSRAM octal + `__builtin_bswap16` | ~25 FPS | ✅ Equivalent: we store **big-endian directly** — no swap loop at all |
| P5 internal SRAM + 32-bit SWAR + SIMD | ~30 FPS | ❌ N/A (no Xtensa SIMD intrinsics from MicroPython) |

**Our actual numbers** (benchmarked on-device @ 80 MHz): full frame 13 ms,
menu band clear 4 ms (viper fill), idle face 25 fps, face full redraw 62 ms.

Key techniques we adopted from the workshop:

- Byte-order: store RGB565 big-endian in the framebuffer → SPI push needs no swap
  (strictly better than their `bswap16`/SWAR, which still swap).
- Incremental redraw: only push the dirty band (`show_region`).
- SPI overclock: 20 → 40 → **80 MHz** (the S3 bus ceiling, per the workshop).

Remaining levers (ordered):

1. Skip redundant CASET/RASET window setup on full-screen `show()` (~1 ms).
2. Batch window commands into one CS assertion (~1 ms).
3. Touch debounce: fixed (edge-triggered, no blocking 250 ms sleep — instant nav).

Reference: <https://wiki.seeedstudio.com/round_display_animation_workshop/>

---

## 1b. Memory / partitioning (XIAO ESP32-S3 Sense)

**Finding:** the stock `ESP32_GENERIC_S3` MicroPython build targets **quad**
PSRAM, but the XIAO Sense has **8 MB OCTAL (OPI) PSRAM** — so the octal PSRAM
is never initialised and the whole heap runs in ~250 KB internal SRAM
(verified: `idf_heap_info` shows no PSRAM region; `gc.mem_free()` ≈ 180 KB).
Flash is fine (~6 MB LittleFS of 8 MB). Fix = custom build with
`CONFIG_SPIRAM_MODE_OCT` + max caches + (optional) PDM-RX — scaffolded at
`tools/micropython-xiao-s3/README.md`. Once the heap is in PSRAM the display
framebuffer and assets stop competing with the tiny SRAM heap.

**SD-card asset loading:** the separate Nirvana OS firmware product uses an
`assets.py` module to load/unload static assets (fonts/icons/app data) from
`/sd/assets` on demand and `gc.collect()` on unload, so big static things don't
sit in RAM. NPU-STACK tracks the integration contract and release metadata, not
the private firmware implementation.

**Agent voice:** `backend/routers/nirvana_audio.py` (`POST /api/nirvana/say`)
routes TTS through **Home Assistant** `tts.speak` (Piper/Google/Cloud) to any
`media_player`/ESPHome speaker — **ElevenLabs is test-only**, not production.
Needs `HA_BASE_URL` + `HA_TOKEN` in `.env`.

**ESP flash safety audit:** all ESP write paths now require a successful,
validated full-flash backup before writing. XIAO ESP32-S3/Sense and legacy ESP
workflows are fixed at exactly **8 MiB**; incomplete, failed, or unavailable
backups block the write, and `backup_first=false` cannot bypass the service
guard. The ESP-IDF path still accepts an explicitly detected board size from
the supported set (including 16 MiB), while defaulting to 8 MiB. Frontend
manual-backup defaults were aligned with the XIAO hardware. Validation:
`tests.test_esp_flash_safety` 22/22 and `tests.test_backend_smoke` 9/9,
plus frontend Vitest 20/20 and a successful Vite production build.

**Detection note:** `detect_current_firmware()` reports a generic 4 MiB
metadata default when `esptool` identifies an ESP32; this is informational
only and does not control backup or flash sizing. A future improvement is to
parse the detected chip's actual flash size. Generated documentation snapshots
may retain older 4 MiB wording until their source index is regenerated.

**Custom all-in-one firmware (2026-09-02):** built MicroPython v1.28 for a new
board variant `ESP32_GENERIC_S3_XIAO_SENSE` = octal PSRAM + OV2640 camera
(lemariva driver) + PDM-RX mic (PR #14176). Two hard-won build lessons:

- **Octal PSRAM, QUAD flash.** Upstream `sdkconfig.spiram_oct` only sets
  `CONFIG_SPIRAM_MODE_OCT` and assumes the board base enables `CONFIG_SPIRAM`;
  the generic S3 base does not, so SPIRAM gets silently pruned and the build
  boots with ~250 KB internal SRAM — every heap allocation fails
  (`import camera` → `MemoryError`). The XIAO Sense has **octal PSRAM but a
  QUAD (QIO) flash chip**; on ESP32-S3 the two share the MSPI bus but run
  independent modes, so octal PSRAM does NOT require octal flash. (An earlier
  attempt forced `CONFIG_ESPTOOLPY_OCT_FLASH`/`FLASHMODE_OPI` and the ROM
  could no longer read the quad flash — chip dropped into download mode on
  every boot.) Fix = board-local `sdkconfig.spiram_oct_xiao` enabling
  `CONFIG_SPIRAM=y` + `SPIRAM_MODE_OCT` + `BOOT_INIT` + `USE_MALLOC` while
  leaving flash at the base QIO. Verified in `build/sdkconfig`:
  `SPIRAM=y`, `SPIRAM_MODE_OCT=y`, `ESP32S3_SPIRAM_SUPPORT=y`,
  `FLASHMODE_QIO=y`, `OCT_FLASH` unset.
- **Stale `build/sdkconfig` overrides new defaults.** kconfig loads the existing
  sdkconfig as authoritative; editing a defaults file then rebuilding does NOT
  apply it. Must delete `build/sdkconfig` to regenerate from defaults.
- **Windows cmd 8191-char limit:** qstr preprocessing inlines ~500 sources +
  hundreds of `-I` flags (>90 KB). Fixed with response files: `mkrules.cmake`
  writes `qstr_pp_args.txt` (newline-separated for makeqstrdefs' keyword
  parsing), `makeqstrdefs.py` writes a per-chunk space-separated gcc `.rsp`
  with embedded `"` escaped as `\"` (so `-DFFCONF_H="..."` survives), and the
  sed-based `qstrdefs.preprocessed.h` step is replaced by
  `ports/esp32/preprocess_qstrdefs.py` (sed's `&`/`\0` get mangled by cmd).

**Accidental remote download-mode latch (2026-09-02):** an esptool
`--before default_reset --after hard_reset` sequence on the XIAO's native
USB-CDC left the chip in `boot:0x22 (DOWNLOAD(USB/UART0))` "waiting for
download" **without the BOOT button held** — a subsequent RTS-only reset did
not clear it. Undesirable here, but as a technique (software-forced download
mode) it could be valuable for headless OTA recovery / factory reflash without
touching the tiny BOOT button. Parked for investigation: reproduce the exact
DTR/RTS pulse order, then wrap it as a deliberate `enter_download_mode()` tool.

**Native-USB DTR/RTS caveat (2026-09-03):** the XIAO Sense's flash/REPL port is
the ESP32-S3's **native USB-Serial/JTAG**, not a UART bridge — so DTR/RTS are
software signals to the chip, NOT wired to EN/GPIO0. esptool's
`--before/--after` line toggles therefore do NOT reset or re-strap the chip on
this port; only a physical power-cycle or the BOOT/RESET buttons change the
boot mode. Repeatedly opening/closing the CDC port to "pulse" it wedges the
USB-serial-JTAG download stub into a state where it stops emitting its banner
and stops ACKing esptool sync (write timeout), recoverable only by a full
power-cycle + clean BOOT-held entry. Lesson: on native-USB S3 boards, don't try
to software-pulse your way out of download mode — power-cycle cleanly once.

**USB-Serial-JTAG latched-strap bug (root cause of the 2026-09-03 "brick"):**
Espressif IDFGH-12237. When download mode is entered on the native USB-Serial/
JTAG port, the USB peripheral can only trigger a *core* reset, which does NOT
re-sample the boot strapping pin — GPIO0 stays latched LOW even after BOOT is
released, so every reset returns `boot:0x22 (DOWNLOAD)` "waiting for download".
The recovery is the **EN/RESET button alone** (a real chip reset re-samples
GPIO0 high). NOT a dead BOOT button, NOT a brick: the flashed image was valid
(magic 0xE9, quad mode) throughout. Verified 2026-09-03: single RESET press
brought the board from COM9/download back to COM10/app with the face running,
PSRAM live (`free mem=8171120`), display/touch/RTC all OK on first boot.

**Camera module enable (2026-09-03):** the lemariva driver gated its whole body
behind `#if MODULE_CAMERA_ENABLED`, and the define had to reach BOTH the
compiler and the makeqstrdefs qstr-collection pass or all of the module's
`MP_QSTR_*` strings go uncollected (cryptic `MP_QSTR_framesize undeclared`).
Fix: define it in the board `mpconfigboard.h`. Two more v1.28 porting gaps:
the driver uses the removed `STATIC` macro (compat shim `#define STATIC
static` added to modcamera.c), and `img_converters.h` pulls `jpeg_decoder.h`
from the esp_jpeg managed component (added its include dir to the usermod
cmake; linking `idf::esp32-camera` directly breaks the qstr pass's
component-requirements resolution, so include-path only).

**Universal-boot contract (confirmed 2026-09-03):** the firmware must boot
clean with any subset of display/camera/mic/touch/SD present — like a Windows
install, missing hardware degrades gracefully, never blocks. This is already
the design: `board.detect()` wraps every probe in try/except and gates on
capability; `camera_capture.py` is fully lazy (raises on absent module/
hardware, `status()` never forces a capture); `main.py` only runs splash/
menu/screen-provisioning when `caps["display"] and caps["touch"]`, else falls
to serial command mode; `sd.py` mount failure returns False. A bare ESP32-S3
with no expansion boots to serial REPL; a full Sense boots the face/menu.

---

## 2. Agent face / eyes ("always alive")

**Status:** Done (v1). The Nirvana OS firmware product's `face.py` renders a
parametric face with 11 emotions (neutral, happy, sad, angry, surprised, sleepy,
wink, love, thinking, listening, talking) plus blink, gaze tracking and mouth
openness. Runs on-device and in the emulator; registered as the `face`
marketplace app. The menu
now enters an idle screensaver (`face.alive()`) after 8 s of no activity — it
blinks, drifts its gaze, and talks when the mic level rises (emulator), then
returns to the menu on tap.

**Pending:** per-emotion gaze/brow polish, and physical IMU gaze tracking when
hardware is added.

**Sensor wiring landed** (private firmware implementation, local-only): unified
`rtc()/battery_mv()/temp_c()/imu()/light()/camera()/mic()` mirroring the emulator
API. Verified on-device: temp 44 °C, RTC present (unset → None), camera present,
IMU/light absent. `face.alive()` now falls back to a breathing/talking pattern
when mic level is 0 so the idle face stays animated.

**On-device PDM mic is blocked** by stock MicroPython (no PDM-RX I2S mode —
unmerged PR #14176). Real mic level needs a PDM-patched build or an I2S mic on
free pins. Battery % on A0/D0 (GPIO1) conflicts with the CHSC6X touch reset (the
pin must stay driven HIGH for touch to answer I2C) — see `docs/SENSORS.md`.

References (fetch + adapt when we build this):

- <https://github.com/FluxGarage/RoboEyes> — Arduino animated eyes (great primitives)
- <https://github.com/0015/lvgl_kawaii_face> — kawaii face expressions for LVGL
- <https://github.com/jaredrhod/ai-visualizer>
- <https://lvgl.io/tools/imageconverter> — image → LVGL C array
- <https://ctmprojectsblog.wordpress.com/2022/02/10/arduino-oled-eyes/> — OLED eyes
- <https://wiki.seeedstudio.com/round_display_christmas_ball/> — contributor project

Adaptation plan for our MicroPython driver (no LVGL/SVG):

- Draw eyes with our existing primitives (`fill_rect`, `rect`, `line`, `pixel`,
  plus a small `arc`/`circle` helper we'd add to `gc9a01.py`).
- Stimuli: mic level (`sensors.mic()`), IMU if present (see §4), touch, RTC.
- Idle timeout → full-screen face (overlay mode over the menu).

---

## 3. Audio output (voicebox / TTS relay feedback)

**Status:** Firmware landed (audio.py + IMA-ADPCM); amp wiring OR Home Assistant
routing. The XIAO ESP32-S3 Sense has a **PDM mic (input only)** and **no audio
DAC**.

Two ways the agent talks:

1. **Home Assistant / ESPHome routing (no XIAO hardware).** The backend already
   has TTS (ElevenLabs key in `.env`); generate TTS, POST to HA
   `media_player.play_media` (or an ESPHome `speaker`) and a room device plays
   it. The XIAO just triggers "say X". Needs the HA URL + long-lived token.
2. **Local I2S amp.** `audio.py` (`init/tone/beep/play_wav/play_samples/
   play_adpcm`) over `machine.I2S` TX on BCLK=GPIO11, LRC=GPIO12, DIN=GPIO13.
   `adpcm.py` is a pure-MicroPython **IMA ADPCM** codec (4:1, ~1.9% error,
   verified round-trip) — the backend can encode TTS to ADPCM and stream it
   compactly (same codec the XIAO nRF52840 reference uses for BLE audio).

Also: `ble_scan.py` (BLE central scanner) is landed — the XIAO scans nearby BLE
devices (verified: 34 devices incl. a Nanoleaf), for presence/HomeKit discovery.
Bluetooth is the under-used radio the fleet should lean on more.

---

## 4. IMU / accel / gyro

**Status:** Verify. The **XIAO ESP32-S3 Sense does NOT ship with an onboard IMU**
(no LSM6DS3/MPU — the IMU lives on the XIAO **nRF52840 Sense**, not the S3).
The Round Display carrier has touch (CHSC6X MCU) + RTC (PCF8563) + TF slot, no IMU.

- If motion input is required: add an external IMU (e.g., LSM6DS3/MPU6050/ICM-42688)
  on the I2C bus (SDA=GPIO5, SCL=GPIO6), or use a different XIAO.
- Emulator already stubs IMU (`accel_xyz`/`gyro_xyz` in `sensors`) so face/motion
  logic can be developed before hardware exists.

---

## 5. Competitive / catch-up (unsloth)

**Status:** Note. "unsloth claims to be the only app that runs and trains models."
We've been doing run+train for months — capture parity in messaging/features.
Unsloth studio is absorbed under `temp_unsloth_studio_inspect/` (reference only).

---

## 6. Fleet pairing / onboarding

**Status:** Planned. Per the Nirvana Fleet Intelligence plan, boards onboard via:

- **IMPROV WiFi** provisioning (QR-code based, <https://www.improv-wifi.com/>) —
  scan a QR, phone sends SSID/pass, board joins. **Landed (HTTP + BLE + menu):**
  `wifi_provision.py` serves the IMPROV-HTTP flow (`GET /redirect` 302,
  `POST /provison` + `/provision` JSON `{ssid,password}` → save → 303 + result
  fragment); the home menu gained a **"WiFi Setup"** item that re-runs the
  SoftAP + QR + portal wizard. **BLE GATT landed** in the separate Nirvana OS
  firmware product: its `improv_ble.py` advertises the Improv service UUID +
  service data (0x4677),
  registers State/Error/RPC-Command/RPC-Result/Capabilities characteristics,
  and handles `identify` / `device info` / `send wifi settings` RPC commands
  (checksum-verified). Verified on-device: 31-byte advertisement, GATT service
  registered, RPC send-wifi parsing drives the save+reboot callback, ~105 KB
  free RAM alongside SoftAP. Full phone/Home Assistant handshake still needs an
  external BLE client test.
- **ESP-NOW** zero-config pairing via a beacon device on this machine, or the
  `portal-1` webserver for special cases. **Landed (receiver + beacon script):**
  the separate Nirvana OS firmware product's board-side pairing module (activates
  ESP-NOW, adds the broadcast peer, sets a fleet PMK, polls for `NPUPAIR1|{json}`
  offers and saves WiFi+backend on match) and `espnow_beacon.py` (beacon side —
  broadcasts the
  offer every 3s; flash onto the spare Matrix Portal S3 / any ESP32). Wired into
  `provision()` alongside the SoftAP portal (`serve_portal` polls ESP-NOW each
  accept timeout). Verified on-device: receiver activates + polls cleanly.
  **Pending:** live end-to-end needs the beacon ESP32 free; backend
  `/api/esp/...` + `espnow_service` still to wire for portal-1-based pairing.
- **ESP-NOW fleet messaging (master/slave)** — landed in the separate Nirvana OS
  firmware product: its `espnow_msg.py` (`Link` class) lets screen devices pass
  short commands without
  a router. Frame = `NPUMSG1|{json}`; types `text` (s + optional RGB565 c),
  `color`, `power` (on/off), `ping`→`pong`, `img`. Role from `config.json`
  `espnow_role` = `master` (sends) / `slave` (applies to display via
  `apply_to_display`) / `off`. Wired into `main.py` (starts the link at boot,
  `espnow_master`/`espnow_slave`/`espnow_off` control commands) and the menu loop
  (slave polls each tick). Verified in the emulator (slave text dispatch,
  ping/pong, master send). This is the transport for the Matrix Portal S3 +
  Waveshare round-display fleet apps below.

### Multi-board fleet (Waveshare + Matrix Portal S3)

- **Waveshare ESP32-S3-LCD-1.28** (non-touch round display) — **onboarded.** New
  `board_profile = "waveshare-lcd128"`: GC9A01A pins SCK=10/MOSI=11/CS=9/DC=8/
  RST=12/BL=40 (madctl 0x00), QMI8658 6-axis IMU on I2C SDA=GPIO6/SCL=GPIO7.
  Verified on-device: display GC9A01 OK + QMI8658 detected @0x6B. Non-touch →
  serial command mode (`n/p/s`, `help`). `scripts/raw_copy.py` is the CH343-safe
  file-transfer path (mpremote's reset handshake breaks on that bridge).
- **Matrix Portal S3** (product 5778) — ESP32-S3 + LIS3DH accel, CircuitPython
  stock firmware. Restoring its factory demo ("digital sand"/marbles) needs UF2
  boot mode (double-tap reset → MATRIXBOOT drive) or the CircuitPython toolchain.
  Plan: default demo + ESP-NOW/API text/color/power/image control as an app.
Xiaozhi is the base we're rebranding/customizing from — we're not far off;
reuse its onboarding flow (AP + QR + web portal) and layer IMPROV on top.

---

## Curated reference links (keep)

Display/face:

- <https://wiki.seeedstudio.com/round_display_animation_workshop/>
- <https://wiki.seeedstudio.com/round_display_christmas_ball/>
- <https://github.com/FluxGarage/RoboEyes>
- <https://github.com/0015/lvgl_kawaii_face>
- <https://github.com/jaredrhod/ai-visualizer>
- <https://lvgl.io/tools/imageconverter>
- <https://ctmprojectsblog.wordpress.com/2022/02/10/arduino-oled-eyes/>

Board hardware:

- <https://www.improv-wifi.com/>
- <https://wiki.seeedstudio.com/xiao_esp32s3_pin_multiplexing/>
- <https://wiki.seeedstudio.com/get_start_round_display/>
- <https://wiki.seeedstudio.com/seeedstudio_round_display_usage/>
- <https://github.com/Seeed-Studio/Seeed_Arduino_RoundDisplay>
- <https://github.com/Seeed-Projects/SeeedStudio_TFT_eSPI>
- <https://github.com/78/xiaozhi-assets-generator>
