@echo off
title NPU-STACK Backend (port 8000)
cd /d J:\NPU-STACK
call .venv\Scripts\activate.bat
echo ============================================
echo   NPU-STACK Backend starting on :8000
echo ============================================
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
pause
