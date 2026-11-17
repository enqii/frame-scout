@echo off
setlocal
cd /d "%~dp0"
rem Each version has one framescout-version-<version>.txt. A ZIP extracted over the
rem folder of another version leaves both files, and files of two versions must not run
rem together: stop before any Python runs. Install-FrameScout.bat has the same lines (a test
rem compares them). The folder path is not used here, so a "!" or ")" in it does no harm.
set "VERSION_FILES=0"
for %%F in (framescout-version-*.txt) do set /a VERSION_FILES+=1
if %VERSION_FILES% leq 1 goto version_checked
echo This folder holds files of two FrameScout versions (more than one
echo framescout-version-*.txt), left when a ZIP is extracted over another version.
echo Extract the ZIP of the version you want into a new, empty folder and copy your
echo data from this folder into it: profiles.json, settings.json and the folders photos,
echo references, results and .cache (downloaded models, so they are not downloaded
echo again). Then run Install-FrameScout.bat there.
pause
exit /b 1
:version_checked
rem Model downloads and library settings go to .cache, unless the user set a variable:
rem as for a manual engine run, that one wins. With the user's XDG_CACHE_HOME, torch and
rem Hugging Face use its folders, so these two lines come first. Install-FrameScout.bat has the same lines.
if not defined TORCH_HOME if not defined XDG_CACHE_HOME set "TORCH_HOME=%CD%\.cache\torch"
if not defined HF_HOME if not defined XDG_CACHE_HOME set "HF_HOME=%CD%\.cache\huggingface"
if not defined YOLO_CONFIG_DIR set "YOLO_CONFIG_DIR=%CD%\.cache\ultralytics"
if not defined XDG_CACHE_HOME set "XDG_CACHE_HOME=%CD%\.cache"
set "TMP=%CD%\.tmp"
set "TEMP=%CD%\.tmp"
if not exist ".tmp" mkdir ".tmp"
if not exist ".venv\Scripts\python.exe" (
 echo The Python environment is missing. Please run Install-FrameScout.bat first.
 pause
 exit /b 1
)
rem framescout_start.py runs the app on 127.0.0.1, port 8501 or the next free one up to
rem 8510, or opens the browser on the app of this folder if it runs already.
".venv\Scripts\python.exe" framescout_start.py
if errorlevel 1 pause
