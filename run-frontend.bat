@echo off
setlocal EnableDelayedExpansion
title NPU-STACK Frontend

set "ROOT=%~dp0"
if "!ROOT:~-1!"=="\" set "ROOT=!ROOT:~0,-1!"

echo   Starting NPU-STACK Frontend...
echo   UI: http://localhost:5173
echo   Press Ctrl+C to stop.
echo.

:: Auto-install deps if missing
if not exist "!ROOT!\frontend\node_modules" (
    echo [INFO] node_modules missing - installing...
    cd /d "!ROOT!\frontend"
    call npm install
    if errorlevel 1 ( echo [ERROR] npm install failed. & pause & exit /b 1 )
)

cd /d "!ROOT!\frontend"
npm run dev
pause
