# Custom MicroPython for the Seeed XIAO ESP32-S3 Sense

The stock `ESP32_GENERIC_S3` MicroPython build is configured for **quad PSRAM**,
but the XIAO ESP32-S3 Sense has **8 MB OCTAL (OPI) PSRAM**. Result: the octal
PSRAM is not initialised, `esp32.idf_heap_info()` shows no PSRAM region, and the
whole MicroPython heap runs in ~250 KB of internal SRAM — the 8 MB PSRAM sits
unused. (Verified: `gc.mem_free()` ≈ 180 KB, filesystem ≈ 6 MB of 8 MB flash.)

Fix: build MicroPython with octal-PSRAM support so the GC heap (and the display
framebuffer) live in PSRAM instead of the cramped internal SRAM.

## What to change (sdkconfig fragment)

```ini
# 8 MB octal PSRAM — this is the key fix for the XIAO S3 Sense
CONFIG_SPIRAM=y
CONFIG_SPIRAM_MODE_OCT=y
CONFIG_SPIRAM_SPEED_80M=y
CONFIG_SPIRAM_USE=y
CONFIG_SPIRAM_USE_MALLOC=y

# max hardware caches (small SRAM tradeoff, big speed win)
CONFIG_ESP32S3_INSTRUCTION_CACHE_SIZE=0x8000
CONFIG_ESP32S3_DATA_CACHE_SIZE=0x10000
CONFIG_ESP32S3_DATA_CACHE_LINE_SIZE=64
```

MicroPython side: the ESP32 port puts the GC heap in PSRAM when SPIRAM is
enabled (`MICROPY_GC_HEAP_IN_PSRAM` in the board config) — set it so the heap is
no longer capped at internal SRAM.

## Build (approx)

```powershell
git clone --depth 1 --branch v1.28.0 https://github.com/micropython/micropython.git
cd micropython/ports/esp32
# drop the sdkconfig fragment into boards/ESP32_GENERIC_S3/sdkconfig.spiram_oct
make BOARD=ESP32_GENERIC_S3 BOARD_VARIANT=SPIRAM_OCT submodules
make BOARD=ESP32_GENERIC_S3 BOARD_VARIANT=SPIRAM_OCT
# flash build-ESP32_GENERIC_S3-SPIRAM_OCT/firmware.bin at 0x0 with esptool
```

## Optional (same build)

- **PDM-RX** (onboard mic): apply micropython PR #14176 before building.
- **8 MB flash partition**: the v1.28 generic S3 build already gives ~6 MB
  LittleFS; bump the `vfs` partition to cover all 8 MB in `partitions.csv`.

## Why not just the stock build?

Stock `ESP32_GENERIC_S3` = quad PSRAM. The XIAO Sense = octal. Mismatch → PSRAM
silently unused. The Waveshare (2 MB quad) works with stock; the XIAO Sense does
not. This is the "configure for THIS board, not standard ESP32" fix.
