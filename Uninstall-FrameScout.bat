@echo off
setlocal
cd /d "%~dp0"
rem Usage: Uninstall-FrameScout.bat [--dry-run]
rem Deletes what the installer and FrameScout create again (.venv, the private Python in
rem .python, .cache, .tmp, the person detection model, compiled files) after showing the
rem list and asking. Never deletes your photos, references, results, profiles or settings.
rem --dry-run only shows the list.
rem It runs with the private Python of the installer (.python, P5 part C), or for an
rem installation of an older installer with the installed Python that created .venv (the
rem "home" in .venv\pyvenv.cfg, so no py launcher is needed (I4), else the py launcher with
rem the versions of those installers), never with .venv's own Python, which
rem cannot delete itself while it runs. The private Python cannot delete itself either: the
rem script deletes everything else and ends with exit code 3
rem (framescout_core.PRIVATE_PYTHON_EXIT_CODE) only after "yes", never in a dry run or when
rem .python is not to be deleted; then this file deletes .python (I20).
rem No cache or TMP variables are set here: .tmp is deleted, and the script reports the
rem user's caches.
rem No delayed expansion: it would remove a "!" from the folder path and the arguments. The
rem folder path is never used inside parentheses, where a ")" in it would end the block.
if exist ".python\python.exe" goto private
rem The line "home = <folder>" of pyvenv.cfg: tokens split at "=" and blanks, the rest of the
rem line (with its blanks) is the folder. A for variable is not parsed again, so a ")" or "&"
rem in it does no harm; %BASE_PYTHON% is used outside of blocks only.
set "BASE_PYTHON="
if not exist ".venv\pyvenv.cfg" goto launcher
for /f "usebackq tokens=1,* delims== " %%A in (".venv\pyvenv.cfg") do if /i "%%A"=="home" set "BASE_PYTHON=%%B\python.exe"
if not defined BASE_PYTHON goto launcher
"%BASE_PYTHON%" -I -c "import sys; sys.exit(sys.version_info < (3, 12))" >nul 2>&1
if errorlevel 1 goto launcher
"%BASE_PYTHON%" -B -E -s framescout_uninstall.py %*
set "EXIT_CODE=%errorlevel%"
goto end
:launcher
set "PYTHON_VERSION="
for %%V in (3.14 3.13 3.12) do (
 if not defined PYTHON_VERSION (
  py -%%V -c "import sys" >nul 2>&1
  if not errorlevel 1 set "PYTHON_VERSION=%%V"
 )
)
if defined PYTHON_VERSION goto installed
echo No Python 3.12 or newer found to run the uninstall: there is no private Python in
echo .python, the Python that created .venv is gone, and the py launcher finds none.
echo To delete the environment by hand, close FrameScout and delete the folders .venv,
echo .python, .cache and .tmp in %CD%
echo (keep .tmp\eval if you labelled photos with the evaluation tool).
pause
exit /b 1
:installed
py -%PYTHON_VERSION% -B -E -s framescout_uninstall.py %*
set "EXIT_CODE=%errorlevel%"
goto end
:private
".python\python.exe" -B -E -s framescout_uninstall.py %*
set "EXIT_CODE=%errorlevel%"
if not "%EXIT_CODE%"=="3" goto end
rem The script has ended, so its Python can go now: python.exe first, so a .python whose
rem deletion stops halfway never looks complete to the installer.
del /f /q ".python\python.exe" ".python\pythonw.exe" >nul 2>&1
rmdir /s /q ".python"
if exist ".python" goto python_left
echo The private Python (.python) was deleted too.
set "EXIT_CODE=0"
goto end
:python_left
echo The private Python in .python could not be deleted completely. Close the programs
echo that use it and delete the folder .python yourself.
set "EXIT_CODE=1"
:end
pause
exit /b %EXIT_CODE%
