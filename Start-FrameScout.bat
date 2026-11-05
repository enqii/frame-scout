@echo off
setlocal
cd /d "%~dp0"
rem I16: a ZIP of this version extracted over an older folder leaves the older single file
rem framescout_core.py next to the folder framescout_core, which refuses to load next to it.
rem This .bat is of the newer version, so the single file is the leftover. Install-FrameScout.bat
rem has the same lines. Jumps instead of a block: no "(" that a ")" in a path could end.
if not exist "framescout_core.py" goto obsolete_done
if not exist "framescout_core\__init__.py" goto obsolete_done
echo Deleting framescout_core.py, a leftover of an older FrameScout version.
del "framescout_core.py"
:obsolete_done
set "TORCH_HOME=%CD%\.cache\torch"
set "HF_HOME=%CD%\.cache\huggingface"
set "YOLO_CONFIG_DIR=%CD%\.cache\ultralytics"
set "XDG_CACHE_HOME=%CD%\.cache"
set "TMP=%CD%\.tmp"
set "TEMP=%CD%\.tmp"
if not exist ".tmp" mkdir ".tmp"
if not exist ".venv\Scripts\python.exe" (
 echo The Python environment is missing. Please run Install-FrameScout.bat first.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501 --server.headless false --browser.gatherUsageStats false
if errorlevel 1 pause
