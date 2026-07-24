# AMB82-Mini (Realtek RTL8735B) — NPU-STACK Platform Profile

## Board Specs
- Chip: Realtek RTL8735B (Arm Cortex-M33 + NN engine)
- WiFi: 802.11 a/b/g/n (2.4GHz + 5GHz)
- BLE: 5.1
- Flash: 16MB SPI
- RAM: 512KB SRAM + 4MB PSRAM
- Camera: OV5647 CSI (5MP)
- USB: Type-C (power + data)
- Audio: I2S mic + speaker headers
- Display: SPI/parallel LCD header
- GPIO: UART, I2C, SPI, PWM, ADC

## SDK
- Arduino: https://github.com/Ameba-AIoT/ameba-arduino-pro2
- Board package: https://github.com/Ameba-AIoT/ameba-arduino-pro2/raw/main/Arduino_package/package_realtek_amebapro2_early_index.json
- Docs: https://ameba-doc-arduino-sdk.readthedocs-hosted.com/

## Flash Method
- Arduino IDE (not esptool — Realtek chip, not Espressif)
- Board: "Ameba ARDUINO with AMB82-mini (RTL8735B)"
- Flash via Arduino IDE upload (Serial/OTA)

## CircuitPython/MicroPython
- Not currently supported (Realtek chip, not in mainline CP/MP)
- Can run Arduino sketches with RTSP streaming + MQTT
- NPU: built-in NN engine for vision AI

## NPU-STACK Fleet Integration
- VID: 0x0BDA (Realtek) — auto-detected by fleet/identify
- Flash method: arduino-ide
- Template: none (needs custom Arduino sketch)
- Platform: amb82-mini

## References
- RTSP streaming: https://github.com/Dennis40816/ameba_stream_project
- Datasheet: https://www.amebaiot.com/en/datasheet-download-amb82-mini/
- Forum: https://forum.amebaiot.com/
