@echo off
set "BACKEND_PORT=8010"
echo ============================================
echo   Starting NPU-STACK (Backend + Frontend)
echo ============================================
start "NPU-STACK Backend" cmd /c "cd /d J:\NPU-STACK && set NPU_STACK_BACKEND_PORT=%BACKEND_PORT% && call .venv\Scripts\activate.bat && python -m uvicorn backend.main:app --host 127.0.0.1 --port %BACKEND_PORT% --reload"
timeout /t 3 /nobreak >nul
where docker >nul 2>nul
if not errorlevel 1 start "NPU-STACK Docs Host" cmd /c "cd /d J:\NPU-STACK && docker compose --profile docs up shared-gitbook"
start "NPU-STACK Frontend" cmd /c "cd /d J:\NPU-STACK\frontend && npm run dev"
echo.
echo   Backend: http://localhost:%BACKEND_PORT%
echo   Frontend: http://localhost:5173
echo   Documentation: http://localhost:5173/documentation
echo   Shared GitBook: http://localhost:3001
echo   Edge Fleet: http://localhost:5173/edge-fleet
echo.
echo Both windows opened. Close this to keep them running.
pause
