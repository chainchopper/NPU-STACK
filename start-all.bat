@echo off
echo ============================================
echo   Starting NPU-STACK (Backend + Frontend)
echo ============================================
start "NPU-STACK Backend" cmd /c "cd /d J:\NPU-STACK && call .venv\Scripts\activate.bat && python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload"
timeout /t 3 /nobreak >nul
start "NPU-STACK Frontend" cmd /c "cd /d J:\NPU-STACK\frontend && npm run dev"
echo.
echo   Backend: http://localhost:8000
echo   Frontend: http://localhost:5173
echo   Edge Fleet: http://localhost:5173/edge-fleet
echo.
echo Both windows opened. Close this to keep them running.
pause
