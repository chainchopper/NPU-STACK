@echo off&&cd /d %~dp0
Title Torch 2.9.1 for 'ComfyUI Easy Install' by ivo
:: Pixaroma Community Edition ::

:: Set colors ::
call :set_colors

:: Set arguments ::
set "PIPargs=--no-cache-dir --no-warn-script-location --no-deps --timeout=1000 --retries 10"

:: Check Add-ons folder ::
if not exist ..\..\python_embeded\python.exe (
    cls
    echo %green%::::::::::::::: Run this file from the %red%'ComfyUI-Go\Add-ons\Torch-Pack'%green% folder
    echo %green%::::::::::::::: Press any key to exit...%reset%&Pause>nul
	exit
)

:: Installing Torch 2.9.1 ::
echo %green%::::::::::::::: Updating%yellow% Torch 2.9.1 %green%:::::::::::::::%reset%
echo.

..\..\python_embeded\python.exe -I -m pip uninstall torch torchvision torchaudio -y
..\..\python_embeded\python.exe -I -m pip install torch==2.9.1 torchvision==0.24.1 torchaudio==2.9.1 --index-url https://download.pytorch.org/whl/cu130 %PIPargs%

..\..\python_embeded\python.exe -I -m pip uninstall llama-cpp-python -y
..\..\python_embeded\python.exe -I -m pip install https://github.com/JamePeng/llama-cpp-python/releases/download/v0.3.24-cu130-Basic-win-20260208/llama_cpp_python-0.3.24+cu130.basic-cp312-cp312-win_amd64.whl %PIPargs%


:: Final Messages ::
echo.
echo.
echo %green%:::::::::::::::::::::::::: Installation Complete ::::::::::::::::::::::::%reset%
echo %red%!!! Make sure to reinstall Nunchaku, SageAttention and FlashAttention !!! %reset%
echo %yellow%:::::::::::::::::::::::::: Press any key to exit ::::::::::::::::::::::::%reset%&Pause>nul
exit

:set_colors
set warning=[33m
set     red=[91m
set   green=[92m
set  yellow=[93m
set    bold=[1m
set   reset=[0m
goto :eof