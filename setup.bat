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
echo [0/7] Checking Windows Long Path support...
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
echo [1/7] Checking for Python...

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
echo [2/7] Creating isolated virtual environment...
%PY_CMD% -m venv "%VENV_DIR%"
if %errorlevel% neq 0 (
    echo   [ERROR] Failed to create venv.
    pause
    exit /b 1
)
goto :SKIP_PYTHON

:CREATE_VENV_PORTABLE
echo.
echo [2/7] Creating isolated virtual environment with portable Python...
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
echo [3/7] Installing backend dependencies...
echo   This will take several minutes (PyTorch, OpenVINO, etc.)
echo.

"%PIP%" install --upgrade pip setuptools wheel >nul 2>&1

echo   Installing core ML dependencies (Torch 2.9.1+cu130)...
"%PIP%" uninstall torch torchvision torchaudio -y >nul 2>&1
"%PIP%" install torch==2.9.1 torchvision==0.24.1 torchaudio==2.9.1 --index-url https://download.pytorch.org/whl/cu130
if %errorlevel% neq 0 (
    echo   [WARN] Optimized PyTorch install failed, falling back to standard...
)

echo   Installing llama-cpp-python (optional - GGUF inference)...
"%PIP%" uninstall llama-cpp-python -y >nul 2>&1
set "LLAMA_CPP_OK=1"
set "PY_MINOR="
"%PYTHON%" -c "import sys; print(sys.version_info[1])" > "%TEMP%\pyver_npu.tmp" 2>nul
if exist "%TEMP%\pyver_npu.tmp" (
    set /p PY_MINOR= < "%TEMP%\pyver_npu.tmp"
    del "%TEMP%\pyver_npu.tmp" >nul 2>&1
)
if "!PY_MINOR!"=="12" (
    "%PIP%" install https://github.com/JamePeng/llama-cpp-python/releases/download/v0.3.24-cu130-Basic-win-20260208/llama_cpp_python-0.3.24+cu130.basic-cp312-cp312-win_amd64.whl
    if !errorlevel! neq 0 set "LLAMA_CPP_OK=0"
) else if "!PY_MINOR!"=="11" (
    "%PIP%" install https://github.com/JamePeng/llama-cpp-python/releases/download/v0.3.24-cu130-Basic-win-20260208/llama_cpp_python-0.3.24+cu130.basic-cp311-cp311-win_amd64.whl
    if !errorlevel! neq 0 set "LLAMA_CPP_OK=0"
) else (
    REM Use --only-binary to avoid triggering a source build (which requires nmake/MSVC on Windows)
    "%PIP%" install llama-cpp-python --only-binary :all: --index-url https://pypi.org/simple/
    if !errorlevel! neq 0 set "LLAMA_CPP_OK=0"
)
if "!LLAMA_CPP_OK!"=="0" (
    echo.
    echo   [INFO] llama-cpp-python could not be installed as a pre-built binary.
    echo   [INFO] This is OPTIONAL - the core platform will work without it.
    echo   [INFO] GGUF inference features will be unavailable until resolved.
    echo   [INFO] To install manually (requires Visual Studio Build Tools):
    echo   [INFO]   https://visualstudio.microsoft.com/visual-cpp-build-tools/
    echo   [INFO]   Then run: .venv\Scripts\pip install llama-cpp-python
    echo   [INFO] Alternatively, use Docker for full support:
    echo   [INFO]   docker compose up --build
    echo.
)

echo   Installing remaining requirements...
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
:: STEP 4: Download GGUF Tools
:: =============================================
echo [4/7] Downloading GGUF Tools...
"%PYTHON%" "%ROOT%\scripts\download_llama_cpp_tools.py"
if %errorlevel% neq 0 (
    echo   [WARN] llama.cpp tools download failed or was skipped.
    echo   [WARN] GGUF conversion features may be unavailable.
    echo   [WARN] You can retry manually: .venv\Scripts\python scripts\download_llama_cpp_tools.py
)
echo.

:: =============================================
:: STEP 5: Generate .env File
:: =============================================
echo [5/7] Generating .env configuration...

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
:: STEP 6: Create Data Directories
:: =============================================
echo [6/7] Creating data directories...

if not exist "%ROOT%\backend\data\models"   mkdir "%ROOT%\backend\data\models"
if not exist "%ROOT%\backend\data\datasets" mkdir "%ROOT%\backend\data\datasets"
if not exist "%ROOT%\backend\data\hf_cache" mkdir "%ROOT%\backend\data\hf_cache"

echo   [OK] Data directories ready.
echo.

:: =============================================
:: STEP 7: Create Launcher Scripts (skip if already present)
:: =============================================
echo [7/7] Checking launcher scripts...

if exist "%ROOT%\run-backend.bat" (
    echo   [OK] run-backend.bat already exists, skipping.
) else (
:: --- run-backend.bat ---
> "%ROOT%\run-backend.bat" echo @echo off
>> "%ROOT%\run-backend.bat" echo setlocal EnableDelayedExpansion
>> "%ROOT%\run-backend.bat" echo title NPU-STACK Backend
>> "%ROOT%\run-backend.bat" echo set "ROOT=%%~dp0"
>> "%ROOT%\run-backend.bat" echo if "!ROOT:~-1!"=="\" set "ROOT=!ROOT:~0,-1!"
>> "%ROOT%\run-backend.bat" echo echo   Starting NPU-STACK Backend...
>> "%ROOT%\run-backend.bat" echo echo   API:  http://localhost:8000
>> "%ROOT%\run-backend.bat" echo echo   Docs: http://localhost:8000/docs
>> "%ROOT%\run-backend.bat" echo echo   Press Ctrl+C to stop.
>> "%ROOT%\run-backend.bat" echo echo.
>> "%ROOT%\run-backend.bat" echo if not exist "!ROOT!\.venv\Scripts\activate.bat" (echo [ERROR] .venv not found. Please run setup.bat first. ^& pause ^& exit /b 1)
>> "%ROOT%\run-backend.bat" echo if exist "!ROOT!\llama.cpp\llama.dll" set "PATH=!ROOT!\llama.cpp;!PATH!"
>> "%ROOT%\run-backend.bat" echo call "!ROOT!\.venv\Scripts\activate.bat"
>> "%ROOT%\run-backend.bat" echo cd /d "!ROOT!\backend"
>> "%ROOT%\run-backend.bat" echo python main.py
>> "%ROOT%\run-backend.bat" echo pause
    echo   [OK] Created run-backend.bat
)

if exist "%ROOT%\run-frontend.bat" (
    echo   [OK] run-frontend.bat already exists, skipping.
) else (
:: --- run-frontend.bat ---
> "%ROOT%\run-frontend.bat" echo @echo off
>> "%ROOT%\run-frontend.bat" echo setlocal EnableDelayedExpansion
>> "%ROOT%\run-frontend.bat" echo title NPU-STACK Frontend
>> "%ROOT%\run-frontend.bat" echo set "ROOT=%%~dp0"
>> "%ROOT%\run-frontend.bat" echo if "!ROOT:~-1!"=="\" set "ROOT=!ROOT:~0,-1!"
>> "%ROOT%\run-frontend.bat" echo echo   Starting NPU-STACK Frontend...
>> "%ROOT%\run-frontend.bat" echo echo   UI: http://localhost:5173
>> "%ROOT%\run-frontend.bat" echo echo   Press Ctrl+C to stop.
>> "%ROOT%\run-frontend.bat" echo echo.
>> "%ROOT%\run-frontend.bat" echo if not exist "!ROOT!\frontend\node_modules" (
>> "%ROOT%\run-frontend.bat" echo     echo [INFO] node_modules missing - installing...
>> "%ROOT%\run-frontend.bat" echo     cd /d "!ROOT!\frontend"
>> "%ROOT%\run-frontend.bat" echo     call npm install
>> "%ROOT%\run-frontend.bat" echo     if errorlevel 1 ( echo [ERROR] npm install failed. ^& pause ^& exit /b 1 )
>> "%ROOT%\run-frontend.bat" echo )
>> "%ROOT%\run-frontend.bat" echo cd /d "!ROOT!\frontend"
>> "%ROOT%\run-frontend.bat" echo npm run dev
>> "%ROOT%\run-frontend.bat" echo pause
    echo   [OK] Created run-frontend.bat
)

if exist "%ROOT%\run-all.bat" (
    echo   [OK] run-all.bat already exists, skipping.
) else (
:: --- run-all.bat ---
> "%ROOT%\run-all.bat" echo @echo off
>> "%ROOT%\run-all.bat" echo setlocal EnableDelayedExpansion
>> "%ROOT%\run-all.bat" echo title NPU-STACK
>> "%ROOT%\run-all.bat" echo set "ROOT=%%~dp0"
>> "%ROOT%\run-all.bat" echo if "!ROOT:~-1!"=="\" set "ROOT=!ROOT:~0,-1!"
>> "%ROOT%\run-all.bat" echo echo  ============================================
>> "%ROOT%\run-all.bat" echo echo    NPU-STACK  ^|  Neural Processor Toolkit
>> "%ROOT%\run-all.bat" echo echo    Backend:  http://localhost:8000
>> "%ROOT%\run-all.bat" echo echo    Frontend: http://localhost:5173
>> "%ROOT%\run-all.bat" echo echo    API Docs: http://localhost:8000/docs
>> "%ROOT%\run-all.bat" echo echo  ============================================
>> "%ROOT%\run-all.bat" echo echo.
>> "%ROOT%\run-all.bat" echo if not exist "!ROOT!\.venv\Scripts\activate.bat" (echo [ERROR] .venv not found. Please run setup.bat first. ^& pause ^& exit /b 1)
>> "%ROOT%\run-all.bat" echo if not exist "!ROOT!\frontend\node_modules" (cd /d "!ROOT!\frontend" ^& call npm install ^& cd /d "!ROOT!")
>> "%ROOT%\run-all.bat" echo start "NPU-STACK Backend" cmd /k "call "!ROOT!\.venv\Scripts\activate.bat" ^& cd /d "!ROOT!\backend" ^& python main.py"
>> "%ROOT%\run-all.bat" echo timeout /t 3 /nobreak ^>nul
>> "%ROOT%\run-all.bat" echo start "NPU-STACK Frontend" cmd /k "cd /d "!ROOT!\frontend" ^& npm run dev"
>> "%ROOT%\run-all.bat" echo echo.
>> "%ROOT%\run-all.bat" echo echo   Both services launched in separate windows.
>> "%ROOT%\run-all.bat" echo echo   Close those windows to stop the services.
>> "%ROOT%\run-all.bat" echo echo.
>> "%ROOT%\run-all.bat" echo pause
    echo   [OK] Created run-all.bat
)
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
