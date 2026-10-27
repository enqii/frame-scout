@echo off
setlocal
cd /d "%~dp0"
rem Usage: Install-FrameScout.bat [cpu or cuda]
rem Without an argument, an installed CUDA build of PyTorch is kept; otherwise GPU support
rem is offered if an NVIDIA graphics driver is found. "cpu" or "cuda" switches the build.
rem No delayed expansion (I21): it would remove a "!" from the folder path and the
rem arguments. The folder path is never used inside parentheses, where a ")" in it would
rem end the block; the steps below jump with goto instead.
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
rem An existing environment is kept, also one that an older installer created with an
rem installed Python (no migration).
if exist ".venv\Scripts\python.exe" goto packages
rem New installations get a private Python in .python (P5 part C): python.org's full
rem package for Windows, a ZIP, checked against its published SHA-256, so no Python has to
rem be installed on the PC. framescout_core.portable_python pins the same values (a test).
rem .venv refers to .python by its path: the folder cannot be moved afterwards.
set "PYTHON_VERSION=3.14.9"
set "PYTHON_URL=https://www.python.org/ftp/python/3.14.9/python-3.14.9-amd64.zip"
set "PYTHON_SHA256=874d01bac04b470c6e1422dfccb9e182b9efe90c6a8adc5fc50d66bf84c40191"
set "PYTHON_ZIP=.tmp\python-3.14.9-amd64.zip"
set "PYTHON_UNPACKED=.tmp\python-3.14.9"
if exist ".python\python.exe" goto venv
rem a .python without python.exe is a leftover, e.g. of an uninstall that stopped halfway
if exist ".python" rmdir /s /q ".python"
if exist ".python" goto python_locked
echo Downloading Python %PYTHON_VERSION% (about 33 MB) from python.org ...
curl.exe -fL --retry 3 -o "%PYTHON_ZIP%" "%PYTHON_URL%"
if errorlevel 1 goto download_failed
rem Windows PowerShell started from PowerShell 7 inherits its module path and then cannot
rem find Get-FileHash; without the variable it uses its own default. The value is restored
rem right after the check, so pip and install_torch.py get the user's value (review).
set "PSMODULEPATH_SAVED=%PSModulePath%"
set "PSModulePath="
powershell.exe -NoProfile -NonInteractive -Command "if ((Get-FileHash -Algorithm SHA256 -LiteralPath $env:PYTHON_ZIP).Hash -ne $env:PYTHON_SHA256) { exit 1 }"
set "HASH_RESULT=%errorlevel%"
set "PSModulePath=%PSMODULEPATH_SAVED%"
set "PSMODULEPATH_SAVED="
if not "%HASH_RESULT%"=="0" goto checksum_failed
if exist "%PYTHON_UNPACKED%" rmdir /s /q "%PYTHON_UNPACKED%"
mkdir "%PYTHON_UNPACKED%"
tar.exe -xf "%PYTHON_ZIP%" -C "%PYTHON_UNPACKED%"
if errorlevel 1 goto unpack_failed
if not exist "%PYTHON_UNPACKED%\python.exe" goto unpack_failed
rem moved as a whole: an interrupted extraction never leaves a .python that looks complete
move "%PYTHON_UNPACKED%" ".python" >nul
if errorlevel 1 goto unpack_failed
del "%PYTHON_ZIP%"
:venv
echo Creating the Python environment with the private Python in .python
".python\python.exe" -I -m venv .venv
if errorlevel 1 goto venv_failed
:packages
rem constraints.txt pins every package, including the dependencies of the dependencies, to
rem the version of the verified runs (I12); requirements.txt names the direct dependencies.
rem PIP_CONSTRAINT applies the pins to the pip call of install_torch.py too, so torch's
rem dependencies are not first installed in their newest versions (I18). It is set after
rem the venv is created and relative: pip splits its value at spaces, and both pip calls
rem run in this folder.
set "PIP_CONSTRAINT=constraints.txt"
rem PyTorch first (CPU or CUDA build); requirements.txt pins the same version. Without an
rem argument install_torch.py keeps an installed CUDA build, otherwise it asks if it finds
rem an NVIDIA driver.
".venv\Scripts\python.exe" install_torch.py %TORCH_VARIANT%
if errorlevel 1 (echo Installing PyTorch failed. See the error message above. & pause & exit /b 1)
".venv\Scripts\python.exe" -m pip install --no-cache-dir -r requirements.txt -c constraints.txt
if errorlevel 1 (echo Installation failed. See the error message above. & pause & exit /b 1)
".venv\Scripts\python.exe" -c "import torch,open_clip,ultralytics,streamlit,pillow_heif,rawpy;print('FrameScout: import test OK');print('PyTorch', torch.__version__, '- CUDA available:', torch.cuda.is_available())"
if errorlevel 1 (echo The import test failed. See the error message above. & pause & exit /b 1)
pause
exit /b 0

:python_locked
echo The folder .python is incomplete and cannot be deleted. Close the programs that use it,
echo delete the folder .python in this folder and run the installer again.
goto failed
:download_failed
echo Downloading Python failed. Check the internet connection (and the proxy settings, if
echo you use a proxy) and run the installer again.
goto failed
:checksum_failed
echo The downloaded Python does not match the checksum (SHA-256) that python.org publishes,
echo so it is not used. Run the installer again; if this happens again, something changes
echo the download on its way (e.g. a proxy or a virus scanner).
del "%PYTHON_ZIP%" >nul 2>&1
goto failed
:unpack_failed
echo Extracting Python failed. See the error message above, then run the installer again.
goto failed
:venv_failed
echo Creating the virtual environment failed. See the error message above. If it fails
echo again, delete the folder .python (the installer downloads it again) and the folder
echo .venv, if there is one, and run the installer again.
goto failed
:failed
pause
exit /b 1
