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

## 2. Agent face / eyes ("always alive")

**Status:** Done (v1). `face.py` (in `firmware/nirvana-os/`) renders a parametric
face with 11 emotions (neutral, happy, sad, angry, surprised, sleepy, wink, love,
thinking, listening, talking) plus blink, gaze tracking and mouth openness. Runs
on-device and in the emulator; registered as the `face` marketplace app. The menu
now enters an idle screensaver (`face.alive()`) after 8 s of no activity — it
blinks, drifts its gaze, and talks when the mic level rises (emulator), then
returns to the menu on tap.

**Pending:** wire a real on-device mic level (PDM read), per-emotion gaze/brow
polish, and physical IMU gaze tracking when hardware is added.

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

**Status:** Planned. The XIAO ESP32-S3 Sense has a **PDM mic (input only)** and
**no audio DAC**. To hear the agent's voice / TTS:

- Add an external **I2S DAC + class-D amp + speaker** (e.g., MAX98357A) — wire
  I2S DOUT to a free XIAO pin. Note which pins the camera/mic/touch/SD already
  use (see board pin map).
- The xiaozhi voice server is already in `deploy/xiaozhi-server/` (MQTT+UDP) —
  audio relay plumbing exists; needs the I2S-out endpoint on-device.

Open question: pin availability for I2S given camera (GPIO10-18,38-48), PDM mic
(41/42), SD (3/7/8/9), display SPI (7/8/9/2/4/43), touch/RTC I2C (5/6), UART (43/44).

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
  scan a QR, phone sends SSID/pass, board joins. We already have SoftAP + QR
  provisioning (`wifi_provision.py`); adopt the IMPROV protocol for
  compatibility with generic tools (ESP Web Tools, Home Assistant).
- **ESP-NOW** zero-config pairing via a beacon device on this machine, or the
  `portal-1` webserver for special cases — beacon broadcasts board identity and
  a pairing token; backend `/api/esp/...` + `espnow_service` already exist.

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
