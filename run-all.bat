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
echo    Frontend: http://localhost:5173
echo    API Docs: http://localhost:!BACKEND_PORT!/api/docs
echo    App Docs: http://localhost:5173/documentation
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

:: Start Backend in new window
:: Note: call the activate script by full path, then cd to backend by full path
start "NPU-STACK Backend" cmd /k ^
set NPU_STACK_BACKEND_PORT=!BACKEND_PORT! ^& call "!ROOT!\.venv\Scripts\activate.bat" ^& cd /d "!ROOT!" ^& python -m uvicorn backend.main:app --host 127.0.0.1 --port !BACKEND_PORT!

timeout /t 3 /nobreak >nul

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
start "NPU-STACK Frontend" cmd /k ^
cd /d "!ROOT!\frontend" ^& npm run dev

echo.
echo   Both services launched in separate windows.
echo   Close those windows to stop the services.
echo.
pause
