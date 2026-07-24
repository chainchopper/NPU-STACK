@echo off
setlocal EnableDelayedExpansion
title Edge Fleet Setup — Nirvana

set "ROOT=%~dp0"
if "!ROOT:~-1!"=="\" set "ROOT=!ROOT:~0,-1!"

echo ============================================================
echo   Nirvana Edge Fleet — Dependency Installer
echo ============================================================
echo.

if not exist "!ROOT!\.venv\Scripts\pip.exe" (
    echo [ERROR] .venv not found. Please run setup.bat first.
    pause & exit /b 1
)

echo [1/4] Installing pyserial (USB device detection)...
"!ROOT!\.venv\Scripts\pip.exe" install pyserial

echo.
echo [2/4] Installing zeroconf (mDNS/WiFi discovery)...
"!ROOT!\.venv\Scripts\pip.exe" install zeroconf

echo.
echo [3/4] Installing esptool (ESP32 firmware operations)...
"!ROOT!\.venv\Scripts\pip.exe" install esptool

echo.
echo [4/4] Installing bleak (Bluetooth Low Energy scanning)...
"!ROOT!\.venv\Scripts\pip.exe" install bleak

echo.
echo ============================================================
echo   Done! Edge Fleet dependencies installed.
echo   Restart the backend to activate: run-backend.bat
echo ============================================================
pause
