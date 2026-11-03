@echo off
setlocal
cd /d "%~dp0"
rem Checks the FrameScout installation in this folder (F15) and names a fix per problem:
rem the Python environment, the package versions, PyTorch (and CUDA), whether .cache and
rem results can be written, the downloaded model files and the free disk space. Read-only:
rem nothing is written (-B: no compiled files), downloaded or repaired.
rem It runs with the Python of .venv if that starts, otherwise with the private Python in
rem .python (the check needs only the standard library), so it can also say why .venv
rem does not work.
rem No delayed expansion: it would remove a "!" from the folder path. The folder path is
rem never used inside parentheses, where a ")" in it would end the block.
if not exist ".venv\Scripts\python.exe" goto private
".venv\Scripts\python.exe" -I -c "import sys" >nul 2>&1
if errorlevel 1 goto private
".venv\Scripts\python.exe" -B -E -s framescout_check.py
goto end
:private
if not exist ".python\python.exe" goto no_python
".python\python.exe" -B -E -s framescout_check.py
goto end
:no_python
echo The Python environment in .venv does not work or is missing, and there is no
echo private Python in .python. Run Install-FrameScout.bat; it installs both.
:end
pause
