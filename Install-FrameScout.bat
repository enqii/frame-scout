@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
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
 if not defined PYTHON_VERSION (echo Python 3.12 bis 3.14 nicht gefunden. & pause & exit /b 1)
 echo Verwende Python !PYTHON_VERSION!
 py -!PYTHON_VERSION! -m venv .venv
 if errorlevel 1 (echo Erstellen der virtuellen Umgebung fehlgeschlagen. & pause & exit /b 1)
)
".venv\Scripts\python.exe" -m pip install --no-cache-dir -r requirements.txt
if errorlevel 1 (echo Installation fehlgeschlagen. Siehe Fehlermeldung. & pause & exit /b 1)
".venv\Scripts\python.exe" -c "import torch,open_clip,ultralytics,streamlit;print('FrameScout: Importtest OK')"
pause
