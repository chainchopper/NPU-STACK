@echo off
setlocal EnableDelayedExpansion
title NPU-STACK Backend

if not defined NPU_STACK_BACKEND_PORT set "NPU_STACK_BACKEND_PORT=8010"
set "BACKEND_PORT=!NPU_STACK_BACKEND_PORT!"

set "ROOT=%~dp0"
if "!ROOT:~-1!"=="\" set "ROOT=!ROOT:~0,-1!"

echo   Starting NPU-STACK Backend...
echo   API:  http://localhost:!BACKEND_PORT!
echo   Docs: http://localhost:!BACKEND_PORT!/api/docs
echo   Press Ctrl+C to stop.
echo.

if not exist "!ROOT!\.venv\Scripts\python.exe" (
    echo [ERROR] .venv Python not found. Please run setup.bat first.
    pause & exit /b 1
)

:: Add llama.cpp DLL to PATH if present
if exist "!ROOT!\llama.cpp\llama.dll" (
    set "PATH=!ROOT!\llama.cpp;!PATH!"
)

cd /d "!ROOT!"
set "NPU_STACK_BACKEND_PORT=!BACKEND_PORT!"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
"!ROOT!\.venv\Scripts\python.exe" -m uvicorn backend.main:app --host 127.0.0.1 --port !BACKEND_PORT!
set "EXIT_CODE=!ERRORLEVEL!"
if not "!EXIT_CODE!"=="0" echo [ERROR] Backend exited with code !EXIT_CODE!.
pause
exit /b !EXIT_CODE!
