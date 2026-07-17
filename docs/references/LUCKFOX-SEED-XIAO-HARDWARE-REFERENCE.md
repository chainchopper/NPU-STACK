# LuckFox Pico SDK & Hardware Reference
# ======================================
# Saved from user session 2026-07-16 for NPU-STACK fleet development

## RV1106 SDK
- SDK Image Compilation: https://wiki.luckfox.com/Luckfox-Pico-RV1106/SDK/SDK-Image-Compilation
- SDK Overlay: https://wiki.luckfox.com/Luckfox-Pico-RV1106/SDK/SDK-Overlay
- Docker Image Build: https://wiki.luckfox.com/Luckfox-Pico-RV1106/SDK/Docker-Image-Build
- Buildroot Configuration: https://wiki.luckfox.com/Luckfox-Pico-RV1106/SDK/Buildroot-Configuration
- Device Tree: https://wiki.luckfox.com/Luckfox-Pico-RV1106/SDK/Device-Tree

## RV1106 NPU (RKNN)
- RKNN Inference: https://wiki.luckfox.com/Luckfox-Pico-RV1106/RKNN

## LuckFox Pico Pro/Max
- MPI (Media Processing Interface): https://wiki.luckfox.com/Luckfox-Pico-Pro-Max/MPI/

## LuckFox Pico 86 Panel
- QT UI Design Guide: https://wiki.luckfox.com/Luckfox-Pico-86-Panel/QT/QT-UI-Design-Guide
- Modbus Communication: https://wiki.luckfox.com/Luckfox-Pico-86-Panel/QT/Modbus-Communication-Tutorial
- LVGL Porting: https://wiki.luckfox.com/Luckfox-Pico-86-Panel/LVGL/LVGL-Porting-Tutorial

## Seeed Studio XIAO Round Display
- Usage Guide: https://wiki.seeedstudio.com/seeedstudio_round_display_usage/
- Features KE button + GPIO, CircuitPython/MicroPython support
- May require SD card for full CP/MP support
- Board: XIAO ESP32S3 Sense + Round Display

## Rockchip / Armbian
- Armbian images available for Rockchip boards
- rockusb protocol: VID 0x2207, vendor-specific USB class 0xFF
- rkdeveloptool: https://github.com/rockchip-linux/rkdeveloptool
- LuckFox SDK: https://github.com/LuckfoxTECH/luckfox-pico

## MCP2221 Bridge
- Microchip MCP2221 USB-I2C/UART Combo (04D8:00DD)
- Used as USB bridge for GPS radio module
- Exposes COM14 serial port on Windows
- NPU-STACK should communicate via serial terminal (WebSocket bridge)

## LuckFox Pico 86 Panel (additional)
- LVGL 86 Panel Design Guide: https://wiki.luckfox.com/Luckfox-Pico-86-Panel/LVGL/LVGL-86-Panel-Design-Guide

## LuckFox RV1106 (additional)
- OpenCV Mobile: https://wiki.luckfox.com/Luckfox-Pico-RV1106/opencv-mobile
- Downloads (firmware images, SDK, tools): https://wiki.luckfox.com/Luckfox-Pico-RV1106/Downloads

## XiaoZhi ESP32 Voice Assistant (Reference)
- GitHub: https://github.com/78/xiaozhi-esp32 (28.2k stars, v2.3.0)
- Architecture: Wake Word → ASR → LLM → TTS pipeline over WebSocket/MQTT+UDP
- Supports ESP32-S3/P4/C3/C5/C6, OPUS codec, OLED/LCD with emoji
- MCP protocol for device control (servo, LED, GPIO)
- 70+ boards supported: M5Stack, Waveshare, LILYGO, SenseCAP
- Custom board guide: https://github.com/78/xiaozhi-esp32/blob/main/docs/custom-board.md
- Server implementations: Python, Java, Golang available
- NPU-STACK should integrate the MCP protocol for AI agent control of fleet devices

## XIAO ESP32S3 Round Display Pin Reference
- Display: TFT_eSPI / LVGL / Arduino GFX libraries
- Touch: CHSC6x I2C controller (D4 SDA, D5 SCL, D3 DC, D1 CS, D7 INT, D6 backlight)
- SD Card: SPI (D2 CS, D8 SCK, D9 MISO, D10 MOSI) — requires TFT init first
- RTC: PCF8563T I2C (D4 SDA, D5 SCL)
- Battery: A0/D0 analog voltage read, KE switch toggles D6/A0 between display backlight and GPIO
- Camera: ESP32S3 Sense has onboard camera (OV2640)
