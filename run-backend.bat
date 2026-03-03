@echo off
setlocal EnableDelayedExpansion
title NPU-STACK Backend

set "ROOT=%~dp0"
if "!ROOT:~-1!"=="\" set "ROOT=!ROOT:~0,-1!"

echo   Starting NPU-STACK Backend...
echo   API:  http://localhost:8000
echo   Docs: http://localhost:8000/docs
echo   Press Ctrl+C to stop.
echo.

if not exist "!ROOT!\.venv\Scripts\activate.bat" (
    echo [ERROR] .venv not found. Please run setup.bat first.
    pause & exit /b 1
)

:: Add llama.cpp DLL to PATH if present
if exist "!ROOT!\llama.cpp\llama.dll" (
    set "PATH=!ROOT!\llama.cpp;!PATH!"
)

call "!ROOT!\.venv\Scripts\activate.bat"
cd /d "!ROOT!\backend"
python main.py
pause
