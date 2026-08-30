@echo off
setlocal EnableDelayedExpansion
title NPU-STACK

set "BACKEND_PORT=8010"

:: Capture root dir (no trailing backslash)
set "ROOT=%~dp0"
if "!ROOT:~-1!"=="\" set "ROOT=!ROOT:~0,-1!"

echo  ============================================
echo    NPU-STACK  ^|  Neural Processor Toolkit
echo    Backend:  http://localhost:!BACKEND_PORT!
echo    Frontend: http://localhost:5180
echo    Nirvana:  http://localhost:8789
echo    API Docs: http://localhost:!BACKEND_PORT!/api/docs
echo    App Docs: http://localhost:5180/documentation
echo    GitBook:  http://localhost:3001
echo  ============================================
echo.

:: Guard: venv must exist
if not exist "!ROOT!\.venv\Scripts\activate.bat" (
    echo [ERROR] .venv not found. Please run setup.bat first.
    pause & exit /b 1
)

:: Auto-install frontend deps if missing
if not exist "!ROOT!\frontend\node_modules" (
    echo [INFO] node_modules missing - installing...
    cd /d "!ROOT!\frontend"
    call npm install
    if errorlevel 1 ( echo [ERROR] npm install failed. & pause & exit /b 1 )
    cd /d "!ROOT!"
)

:: Start the supported root-based backend launcher in a new window.
set "NPU_STACK_BACKEND_PORT=!BACKEND_PORT!"
start "NPU-STACK Backend" "%ComSpec%" /d /k ""!ROOT!\run-backend.bat""

:: Report the real readiness result instead of assuming a fixed startup delay.
call :wait_for_backend
if errorlevel 1 echo [WARN] Backend is not ready; inspect the NPU-STACK Backend window for the startup exception.

:: Start shared GitBook host when Docker is available
where docker >nul 2>nul
if not errorlevel 1 (
    start "NPU-STACK Docs Host" cmd /k ^
    cd /d "!ROOT!" ^& docker compose --profile docs up shared-gitbook
) else (
    echo [WARN] Docker not found - shared GitBook host not launched.
)

timeout /t 2 /nobreak >nul

:: Start Frontend in new window
start "NPU-STACK Frontend" "%ComSpec%" /d /k ""!ROOT!\run-frontend.bat""

timeout /t 2 /nobreak >nul

:: Start Nirvana WebUI in new window (absorbed hermes-webui)
if exist "!ROOT!\hermes-webui\start.ps1" (
    start "Nirvana WebUI" cmd /k ^
    set HERMES_WEBUI_HOST=127.0.0.1 ^& set HERMES_WEBUI_PORT=8789 ^& set HERMES_WEBUI_AGENT_DIR=!ROOT!\hermes-agent ^& call "!ROOT!\.venv\Scripts\activate.bat" ^& powershell -ExecutionPolicy Bypass -File "!ROOT!\hermes-webui\start.ps1" -Port 8789 -BindHost 127.0.0.1
)

echo.
echo   Both services launched in separate windows.
echo   Close those windows to stop the services.
echo.
pause
exit /b 0

:wait_for_backend
for /l %%N in (1,1,20) do (
    curl.exe --fail --silent --max-time 2 "http://127.0.0.1:!BACKEND_PORT!/api/health" >nul 2>nul
    if not errorlevel 1 (
        echo   [OK] Backend ready at http://127.0.0.1:!BACKEND_PORT!
        exit /b 0
    )
    timeout /t 1 /nobreak >nul
)
exit /b 1
