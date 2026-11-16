@echo off
setlocal
cd /d "%~dp0"
rem Usage: Uninstall-FrameScout.bat [--dry-run]
rem Deletes what the installer and FrameScout create again (.venv, the private Python in
rem .python, .cache, .tmp, the person detection model, compiled files) after showing the
rem list and asking. Never deletes your photos, references, results, profiles or settings.
rem --dry-run only shows the list.
rem It runs with the private Python of the installer (.python, P5 part C), never with
rem .venv's own Python, which cannot delete itself while it runs. The private Python cannot
rem delete itself either: the script deletes everything else and ends with exit code 3
rem (framescout_core.uninstall.PRIVATE_PYTHON_EXIT_CODE) only after "yes", never in a dry run or when
rem .python is not to be deleted; then this file deletes .python (I20).
rem No cache or TMP variables are set here: .tmp is deleted, and the script reports the
rem user's caches.
rem No delayed expansion: it would remove a "!" from the folder path and the arguments. The
rem folder path is never used inside parentheses, where a ")" in it would end the block.
if exist ".python\python.exe" goto private
echo There is no private Python in .python to run the uninstall.
echo To delete the environment by hand, close FrameScout and delete the folders .venv,
rem quoted: an "&" in the folder path would end the echo and run the rest as a command
echo .python, .cache and .tmp in "%CD%"
echo (keep .tmp\eval if you labelled photos with the evaluation tool).
pause
exit /b 1
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
