@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
rem Usage: Install-FrameScout.bat [cpu or cuda]
rem Without an argument, an installed CUDA build of PyTorch is kept; otherwise GPU support
rem is offered if an NVIDIA graphics driver is found. "cpu" or "cuda" switches the build.
set "TORCH_VARIANT=%~1"
if not "%TORCH_VARIANT%"=="" if /i not "%TORCH_VARIANT%"=="cpu" if /i not "%TORCH_VARIANT%"=="cuda" (
 echo Usage: Install-FrameScout.bat [cpu^|cuda]
 echo   cpu    PyTorch for the CPU
 echo   cuda   PyTorch with CUDA support for an NVIDIA GPU
 echo Without an argument, FrameScout keeps an installed CUDA build, otherwise it asks
 echo if an NVIDIA graphics driver is found.
 pause
 exit /b 1
)
rem lower case for install_torch.py
if /i "%TORCH_VARIANT%"=="cpu" set "TORCH_VARIANT=cpu"
if /i "%TORCH_VARIANT%"=="cuda" set "TORCH_VARIANT=cuda"
set "PIP_CACHE_DIR=%CD%\.cache\pip"
set "TORCH_HOME=%CD%\.cache\torch"
set "HF_HOME=%CD%\.cache\huggingface"
set "YOLO_CONFIG_DIR=%CD%\.cache\ultralytics"
set "XDG_CACHE_HOME=%CD%\.cache"
set "TMP=%CD%\.tmp"
set "TEMP=%CD%\.tmp"
if not exist ".tmp" mkdir ".tmp"
if not exist ".venv\Scripts\python.exe" (
 set "PYTHON_VERSION="
 for %%V in (3.14 3.13 3.12) do (
  if not defined PYTHON_VERSION (
   py -%%V -c "import sys; print(sys.version)" >nul 2>&1
   if not errorlevel 1 set "PYTHON_VERSION=%%V"
  )
 )
 if not defined PYTHON_VERSION (echo Python 3.12 to 3.14 not found. & pause & exit /b 1)
 echo Using Python !PYTHON_VERSION!
 py -!PYTHON_VERSION! -m venv .venv
 if errorlevel 1 (echo Creating the virtual environment failed. & pause & exit /b 1)
)
rem PyTorch first (CPU or CUDA build); requirements.txt pins the same version. Without an
rem argument install_torch.py keeps an installed CUDA build, otherwise it asks if it finds
rem an NVIDIA driver.
".venv\Scripts\python.exe" install_torch.py %TORCH_VARIANT%
if errorlevel 1 (echo Installing PyTorch failed. See the error message above. & pause & exit /b 1)
rem constraints.txt pins every package, including the dependencies of the dependencies, to
rem the tested version (I12); requirements.txt names the direct dependencies.
".venv\Scripts\python.exe" -m pip install --no-cache-dir -r requirements.txt -c constraints.txt
if errorlevel 1 (echo Installation failed. See the error message above. & pause & exit /b 1)
".venv\Scripts\python.exe" -c "import torch,open_clip,ultralytics,streamlit,pillow_heif,rawpy;print('FrameScout: import test OK');print('PyTorch', torch.__version__, '- CUDA available:', torch.cuda.is_available())"
if errorlevel 1 (echo The import test failed. See the error message above. & pause & exit /b 1)
pause
