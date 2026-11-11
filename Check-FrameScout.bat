@echo off
setlocal
cd /d "%~dp0"
rem Checks the FrameScout installation in this folder (F15) and names a fix per problem:
rem leftover program files of another FrameScout version (I34), the Python environment,
rem the package versions, PyTorch (and CUDA), whether .cache and results can be written,
rem the downloaded model files and the free disk space. Read-only:
rem nothing is written (-B: no compiled files), downloaded or repaired.
rem It runs with the Python of .venv if that starts, otherwise with the private Python in
rem .python (the check needs only the standard library), so it can also say why .venv
rem does not work.
rem framescout_check.py exits with 0 (no problem) or 2 (problems found, the output says
rem which); any other exit code means the check itself could not run with that Python.
rem No delayed expansion: it would remove a "!" from the folder path. The folder path is
rem never used inside parentheses, where a ")" in it would end the block.
if not exist ".venv\Scripts\python.exe" goto private
".venv\Scripts\python.exe" -I -c "import sys" >nul 2>&1
if errorlevel 1 goto private
".venv\Scripts\python.exe" -B -E -s framescout_check.py
if "%errorlevel%"=="0" goto end
if "%errorlevel%"=="2" goto end
echo.
echo The check could not run with the Python of .venv; trying the private Python in .python.
echo.
:private
if not exist ".python\python.exe" goto no_python
".python\python.exe" -B -E -s framescout_check.py
if "%errorlevel%"=="0" goto end
if "%errorlevel%"=="2" goto end
goto failed
:no_python
echo The Python environment in .venv does not work or is missing, and there is no
echo private Python in .python. Run Install-FrameScout.bat; it installs both.
goto end
:failed
echo.
echo The check could not run (see the error above). Close FrameScout and run
echo Install-FrameScout.bat; it repairs the Python environment. If that does not help,
echo download FrameScout again into a new folder and install it there.
:end
pause
