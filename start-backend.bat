@echo off
set "NPU_STACK_BACKEND_PORT=8010"
call "%~dp0run-backend.bat"
exit /b %errorlevel%
