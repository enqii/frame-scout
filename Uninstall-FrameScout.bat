@echo off
setlocal
cd /d "%~dp0"
rem Usage: Uninstall-FrameScout.bat [--dry-run]
rem Deletes what the installer and FrameScout create again (.venv, .cache, .tmp, the person
rem detection model, compiled files) after showing the list and asking. Never deletes your
rem photos, references, results, profiles or settings. --dry-run only shows the list.
rem It runs with the Python that created .venv (py launcher, the versions of the installer),
rem not with .venv's own Python, which cannot delete itself while it runs. No cache or TMP
rem variables are set here: .tmp is deleted, and the script reports the user's caches.
rem No delayed expansion: it would remove a "!" from the folder path and the arguments. The
rem folder path is never used inside parentheses, where a ")" in it would end the block.
set "PYTHON_VERSION="
for %%V in (3.14 3.13 3.12) do (
 if not defined PYTHON_VERSION (
  py -%%V -c "import sys" >nul 2>&1
  if not errorlevel 1 set "PYTHON_VERSION=%%V"
 )
)
if defined PYTHON_VERSION goto run
echo Python 3.12 to 3.14 not found, so the uninstall cannot run.
echo To delete the environment by hand, close FrameScout and delete the folders .venv,
echo .cache and .tmp in %CD%
echo (keep .tmp\eval if you labelled photos with the evaluation tool).
pause
exit /b 1
:run
py -%PYTHON_VERSION% -B -E -s framescout_uninstall.py %*
set "EXIT_CODE=%errorlevel%"
pause
exit /b %EXIT_CODE%
