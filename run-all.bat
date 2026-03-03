@echo off
setlocal EnableDelayedExpansion
title NPU-STACK

:: Capture root dir (no trailing backslash)
set "ROOT=%~dp0"
if "!ROOT:~-1!"=="\" set "ROOT=!ROOT:~0,-1!"

echo  ============================================
echo    NPU-STACK  ^|  Neural Processor Toolkit
echo    Backend:  http://localhost:8000
echo    Frontend: http://localhost:5173
echo    API Docs: http://localhost:8000/docs
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
"call "!ROOT!\.venv\Scripts\activate.bat" & cd /d "!ROOT!\backend" & python main.py"

timeout /t 3 /nobreak >nul

:: Start Frontend in new window
start "NPU-STACK Frontend" cmd /k ^
"cd /d "!ROOT!\frontend" & npm run dev"

echo.
echo   Both services launched in separate windows.
echo   Close those windows to stop the services.
echo.
pause
