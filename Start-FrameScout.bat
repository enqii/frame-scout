@echo off
setlocal
cd /d "%~dp0"
rem I16: a ZIP of this version extracted over an older folder leaves the older single file
rem framescout_core.py next to the folder framescout_core, which refuses to load next to it.
rem This .bat is of the newer version, so the single file is the leftover. Install-FrameScout.bat
rem has the same lines. Jumps instead of a block: no "(" that a ")" in a path could end.
rem A folder of that name is no leftover ("\*" exists only for a folder): del would ask and
rem delete the files in it. /f deletes a read-only file; a file that stays (open in another
rem program) stops here, as the app would not start next to it (review).
if not exist "framescout_core.py" goto obsolete_done
if exist "framescout_core.py\*" goto obsolete_done
if not exist "framescout_core\__init__.py" goto obsolete_done
echo Deleting framescout_core.py, a leftover of an older FrameScout version.
del /f "framescout_core.py"
if not exist "framescout_core.py" goto obsolete_done
echo framescout_core.py could not be deleted. Close the programs that use it or delete it
echo yourself, then run this file again.
pause
exit /b 1
:obsolete_done
rem I36: the same for framescout_scoring.py, the single file before the package
rem framescout_scoring (I30), which refuses to load next to it for older scripts.
if not exist "framescout_scoring.py" goto obsolete_scoring_done
if exist "framescout_scoring.py\*" goto obsolete_scoring_done
if not exist "framescout_scoring\__init__.py" goto obsolete_scoring_done
echo Deleting framescout_scoring.py, a leftover of an older FrameScout version.
del /f "framescout_scoring.py"
if not exist "framescout_scoring.py" goto obsolete_scoring_done
echo framescout_scoring.py could not be deleted. Close the programs that use it or delete it
echo yourself, then run this file again.
pause
exit /b 1
:obsolete_scoring_done
rem Model downloads and library settings go to .cache, unless the user set a variable
rem (A36): as for a manual engine run, that one wins. With the user's XDG_CACHE_HOME, torch and
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
rem F22: framescout_start.py runs the app on 127.0.0.1, port 8501 or the next free one up to
rem 8510, or opens the browser on the app of this folder if it runs already.
".venv\Scripts\python.exe" framescout_start.py
if errorlevel 1 pause
