@echo off
set "BACKEND_PORT=8010"
title NPU-STACK Backend (port %BACKEND_PORT%)
cd /d J:\NPU-STACK
call .venv\Scripts\activate.bat
echo ============================================
echo   NPU-STACK Backend starting on :%BACKEND_PORT%
echo ============================================
set "NPU_STACK_BACKEND_PORT=%BACKEND_PORT%"
python -m uvicorn backend.main:app --host 127.0.0.1 --port %BACKEND_PORT% --reload
pause
