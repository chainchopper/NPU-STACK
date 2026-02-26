@echo off
setlocal EnableDelayedExpansion

::  NPU-STACK Setup Script
::  Made by Fanalogy - Powered by Nirvana
:: ============================================

:: Check for Administrative privileges for Long Path support
>nul 2>&1 "%SYSTEMROOT%\system32\cacls.exe" "%SYSTEMROOT%\system32\config\system"
if %errorlevel% neq 0 (
    echo.
    echo  [!!] This script works best with Administrator privileges
    echo       (Required to enable Windows Long Path support)
    echo.
)

title NPU-STACK Setup
color 0A

echo.
echo  ============================================
echo    NPU-STACK  -  Neural Processor Toolkit
echo    Made by Fanalogy  -  Powered by Nirvana
echo  ============================================
echo.

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "PYTHON_DIR=%ROOT%\python"
set "VENV_DIR=%ROOT%\.venv"
set "PYTHON_VER=3.11.9"
set "PYTHON_URL=https://www.python.org/ftp/python/%PYTHON_VER%/python-%PYTHON_VER%-embed-amd64.zip"
set "GET_PIP_URL=https://bootstrap.pypa.io/get-pip.py"
set "PYTHON_ZIP=%ROOT%\python-embed.zip"
set "ENV_FILE=%ROOT%\.env"

:: =============================================
:: STEP 0: Enable Windows Long Paths (Optional)
:: =============================================
echo [0/6] Checking Windows Long Path support...
reg query "HKLM\System\CurrentControlSet\Control\FileSystem" /v LongPathsEnabled >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=3" %%a in ('reg query "HKLM\System\CurrentControlSet\Control\FileSystem" /v LongPathsEnabled') do set "LP_VAL=%%a"
    if "!LP_VAL!"=="0x1" (
        echo   [OK] Long Paths already enabled.
    ) else (
        echo   [!!] Long Paths are disabled. This can cause model download errors.
        echo   Attempting to enable...
        reg add "HKLM\System\CurrentControlSet\Control\FileSystem" /v LongPathsEnabled /t REG_DWORD /d 1 /f >nul 2>&1
        if !errorlevel! equ 0 (
            echo   [OK] Long Paths enabled successfully.
        ) else (
            echo   [WARN] Failed to enable Long Paths. Please run as Administrator or
            echo          edit the registry manually if you see I/O errors.
        )
    )
)

:: =============================================
:: STEP 1: Check / Download Portable Python
:: =============================================
echo [1/6] Checking for Python...

:: Check if venv already exists and is working
if exist "%VENV_DIR%\Scripts\python.exe" (
    echo   [OK] Virtual environment already exists at .venv\
    goto :SKIP_PYTHON
)

:: Check if portable Python already downloaded
if exist "%PYTHON_DIR%\python.exe" (
    echo   [OK] Portable Python found at python\
    goto :CREATE_VENV_PORTABLE
)

:: Check if system Python 3.10+ is available
where python >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=*" %%i in ('python --version 2^>^&1') do set "SYS_PY_VER=%%i"
    echo   Found system !SYS_PY_VER!

    python -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)" 2>nul
    if !errorlevel! equ 0 (
        echo   [OK] System Python is compatible, creating isolated venv...
        set "PY_CMD=python"
        goto :CREATE_VENV_SYSTEM
    ) else (
        echo   [!!] System Python is too old, downloading portable Python...
    )
) else (
    echo   [!!] No system Python found, downloading portable Python...
)

:: Download portable Python
echo.
echo   Downloading Python %PYTHON_VER% portable...
    echo   URL: !PYTHON_URL!
    powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; $ProgressPreference = 'SilentlyContinue'; Write-Host '   Downloading Python...' -ForegroundColor Cyan; (New-Object System.Net.WebClient).DownloadFile('!PYTHON_URL!', '!PYTHON_ZIP!'); Write-Host '   Extracting...' -ForegroundColor Cyan; Expand-Archive -Path '!PYTHON_ZIP!' -DestinationPath '!PYTHON_DIR!' -Force; Remove-Item '!PYTHON_ZIP!' -Force; Write-Host '   Done!' -ForegroundColor Green"

if not exist "%PYTHON_DIR%\python.exe" (
    echo.
    echo   [ERROR] Failed to download Python.
    echo   Please check your internet connection.
    echo   You can also install Python 3.11+ from https://python.org
    echo.
    pause
    exit /b 1
)

:: Fix embedded Python to allow pip
echo   Configuring portable Python for pip support...
for %%f in ("%PYTHON_DIR%\python*._pth") do (
    echo   Patching %%~nxf...
    > "%%f" echo python311.zip
    >> "%%f" echo .
    >> "%%f" echo ..
    >> "%%f" echo import site
)

:: Download and install pip
echo   Installing pip into portable Python...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference = 'SilentlyContinue'; (New-Object System.Net.WebClient).DownloadFile('%GET_PIP_URL%', '%PYTHON_DIR%\get-pip.py')"

"%PYTHON_DIR%\python.exe" "%PYTHON_DIR%\get-pip.py" --no-warn-script-location >nul 2>&1
if %errorlevel% neq 0 (
    echo   [WARN] pip bootstrap failed, trying ensurepip...
    "%PYTHON_DIR%\python.exe" -m ensurepip --upgrade >nul 2>&1
)

:: Install virtualenv
echo   Installing virtualenv...
"%PYTHON_DIR%\python.exe" -m pip install virtualenv --no-warn-script-location >nul 2>&1

set "PY_CMD=%PYTHON_DIR%\python.exe"
goto :CREATE_VENV_PORTABLE

:: =============================================
:: STEP 2: Create Virtual Environment
:: =============================================

:CREATE_VENV_SYSTEM
echo.
echo [2/6] Creating isolated virtual environment...
%PY_CMD% -m venv "%VENV_DIR%"
if %errorlevel% neq 0 (
    echo   [ERROR] Failed to create venv.
    pause
    exit /b 1
)
goto :SKIP_PYTHON

:CREATE_VENV_PORTABLE
echo.
echo [2/6] Creating isolated virtual environment with portable Python...
"%PYTHON_DIR%\python.exe" -m virtualenv "%VENV_DIR%" 2>nul
if %errorlevel% neq 0 (
    "%PYTHON_DIR%\python.exe" -m venv "%VENV_DIR%" 2>nul
)
goto :SKIP_PYTHON

:SKIP_PYTHON
set "PIP=%VENV_DIR%\Scripts\pip.exe"
set "PYTHON=%VENV_DIR%\Scripts\python.exe"

echo   [OK] Python: %PYTHON%
echo.

:: =============================================
:: STEP 3: Install Dependencies
:: =============================================
echo [3/6] Installing backend dependencies...
echo   This will take several minutes (PyTorch, OpenVINO, etc.)
echo.

"%PIP%" install --upgrade pip setuptools wheel >nul 2>&1
"%PIP%" install -r "%ROOT%\backend\requirements.txt"

if %errorlevel% neq 0 (
    echo.
    echo   [WARNING] Some packages may have failed.
    echo   Core platform will still work. GPU/NPU features may be limited.
    echo.
)

echo.
echo   [OK] Dependencies installed.
echo.

:: =============================================
:: STEP 4: Generate .env File
:: =============================================
echo [4/6] Generating .env configuration...

if exist "%ENV_FILE%" (
    echo   [OK] .env already exists, skipping. Delete it to regenerate.
) else (
    > "%ENV_FILE%" echo # NPU-STACK Environment Configuration
    >> "%ENV_FILE%" echo # Generated by setup.bat on %date% %time%
    >> "%ENV_FILE%" echo.
    >> "%ENV_FILE%" echo # --- Server ---
    >> "%ENV_FILE%" echo BACKEND_HOST=0.0.0.0
    >> "%ENV_FILE%" echo BACKEND_PORT=8000
    >> "%ENV_FILE%" echo FRONTEND_PORT=3000
    >> "%ENV_FILE%" echo.
    >> "%ENV_FILE%" echo # --- Database ---
    >> "%ENV_FILE%" echo DATABASE_URL=sqlite:///data/npu_stack.db
    >> "%ENV_FILE%" echo.
    >> "%ENV_FILE%" echo # --- Model Storage ---
    >> "%ENV_FILE%" echo MODEL_STORE_PATH=./data/models
    >> "%ENV_FILE%" echo DATASET_CACHE_PATH=./data/datasets
    >> "%ENV_FILE%" echo MAX_UPLOAD_SIZE_MB=500
    >> "%ENV_FILE%" echo.
    >> "%ENV_FILE%" echo # --- HuggingFace ---
    >> "%ENV_FILE%" echo HUGGINGFACE_TOKEN=
    >> "%ENV_FILE%" echo HUGGINGFACE_CACHE_DIR=./data/hf_cache
    >> "%ENV_FILE%" echo.
    >> "%ENV_FILE%" echo # --- Training ---
    >> "%ENV_FILE%" echo DEFAULT_DEVICE=cpu
    >> "%ENV_FILE%" echo TORCH_HOME=./data/torch_cache
    >> "%ENV_FILE%" echo CUDA_VISIBLE_DEVICES=0
    >> "%ENV_FILE%" echo.
    >> "%ENV_FILE%" echo # --- OpenVINO / NPU ---
    >> "%ENV_FILE%" echo OPENVINO_LOG_LEVEL=WARNING
    >> "%ENV_FILE%" echo NPU_DEVICE_NAME=NPU
    >> "%ENV_FILE%" echo.
    >> "%ENV_FILE%" echo # --- CORS ---
    >> "%ENV_FILE%" echo CORS_ORIGINS=http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173,http://127.0.0.1:3000
    >> "%ENV_FILE%" echo.
    >> "%ENV_FILE%" echo # --- Logging ---
    >> "%ENV_FILE%" echo LOG_LEVEL=INFO
    >> "%ENV_FILE%" echo DEBUG=false
    >> "%ENV_FILE%" echo.
    >> "%ENV_FILE%" echo # --- Branding ---
    >> "%ENV_FILE%" echo APP_NAME=NPU-STACK
    >> "%ENV_FILE%" echo APP_VERSION=1.0.0
    >> "%ENV_FILE%" echo BRAND=Fanalogy
    >> "%ENV_FILE%" echo POWERED_BY=Nirvana
    echo   [OK] Created .env
)
echo.

:: =============================================
:: STEP 5: Create Data Directories
:: =============================================
echo [5/6] Creating data directories...

if not exist "%ROOT%\backend\data\models"   mkdir "%ROOT%\backend\data\models"
if not exist "%ROOT%\backend\data\datasets" mkdir "%ROOT%\backend\data\datasets"
if not exist "%ROOT%\backend\data\hf_cache" mkdir "%ROOT%\backend\data\hf_cache"

echo   [OK] Data directories ready.
echo.

:: =============================================
:: STEP 6: Create Launcher Scripts
:: =============================================
echo [6/6] Creating launcher scripts...

:: --- run-backend.bat ---
> "%ROOT%\run-backend.bat" echo @echo off
>> "%ROOT%\run-backend.bat" echo title NPU-STACK Backend
>> "%ROOT%\run-backend.bat" echo echo Starting NPU-STACK Backend...
>> "%ROOT%\run-backend.bat" echo echo API: http://localhost:8000
>> "%ROOT%\run-backend.bat" echo echo Docs: http://localhost:8000/docs
>> "%ROOT%\run-backend.bat" echo echo Press Ctrl+C to stop.
>> "%ROOT%\run-backend.bat" echo echo.
>> "%ROOT%\run-backend.bat" echo call "%%~dp0.venv\Scripts\activate.bat"
>> "%ROOT%\run-backend.bat" echo cd /d "%%~dp0backend"
>> "%ROOT%\run-backend.bat" echo python main.py
>> "%ROOT%\run-backend.bat" echo pause

:: --- run-frontend.bat ---
> "%ROOT%\run-frontend.bat" echo @echo off
>> "%ROOT%\run-frontend.bat" echo title NPU-STACK Frontend
>> "%ROOT%\run-frontend.bat" echo echo Starting NPU-STACK Frontend...
>> "%ROOT%\run-frontend.bat" echo echo UI: http://localhost:5173
>> "%ROOT%\run-frontend.bat" echo echo Press Ctrl+C to stop.
>> "%ROOT%\run-frontend.bat" echo echo.
>> "%ROOT%\run-frontend.bat" echo cd /d "%%~dp0frontend"
>> "%ROOT%\run-frontend.bat" echo if not exist node_modules npm install
>> "%ROOT%\run-frontend.bat" echo npm run dev
>> "%ROOT%\run-frontend.bat" echo pause

:: --- run-all.bat ---
> "%ROOT%\run-all.bat" echo @echo off
>> "%ROOT%\run-all.bat" echo title NPU-STACK
>> "%ROOT%\run-all.bat" echo echo NPU-STACK - Starting Full Platform
>> "%ROOT%\run-all.bat" echo echo Backend:  http://localhost:8000
>> "%ROOT%\run-all.bat" echo echo Frontend: http://localhost:5173
>> "%ROOT%\run-all.bat" echo echo API Docs: http://localhost:8000/docs
>> "%ROOT%\run-all.bat" echo echo.
>> "%ROOT%\run-all.bat" echo start "NPU-STACK Backend" cmd /k "cd /d \"%%~dp0\" && call .venv\Scripts\activate.bat && cd backend && python main.py"
>> "%ROOT%\run-all.bat" echo timeout /t 3 /nobreak ^>nul
>> "%ROOT%\run-all.bat" echo start "NPU-STACK Frontend" cmd /k "cd /d \"%%~dp0frontend\" && npm run dev"
>> "%ROOT%\run-all.bat" echo echo Both services started in separate windows.
>> "%ROOT%\run-all.bat" echo pause

echo   [OK] Created run-backend.bat
echo   [OK] Created run-frontend.bat
echo   [OK] Created run-all.bat
echo.

:: =============================================
:: DONE
:: =============================================
echo  ============================================
echo   Setup Complete!
echo  ============================================
echo.
echo   Python:   %PYTHON%
echo   Config:   .env
echo.
echo   Quick Start:
echo     run-backend.bat   - Start API server
echo     run-frontend.bat  - Start React dev server
echo     run-all.bat       - Start both
echo.
echo   Or with Docker:
echo     docker compose up --build
echo.
echo  ============================================
echo.
pause
