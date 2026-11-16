#!/usr/bin/env bash
# Usage: ./Check-FrameScout.sh
# The Linux counterpart of Check-FrameScout.bat (F47): checks the FrameScout installation
# in this folder (F15) and names a fix per problem. Read-only: nothing is written (-B: no
# compiled files), downloaded or repaired.
# It runs with the Python of .venv if that starts, otherwise with the private Python in
# .python (the check needs only the standard library), so it can also say why .venv
# does not work.
# framescout_check.py exits with 0 (no problem) or 2 (problems found, the output says
# which); any other exit code means the check itself could not run with that Python.
# This script exits with the check's 0 or 2, otherwise with 1.
set -u
cd -- "$(dirname -- "$0")" || exit 1
if [ -x .venv/bin/python ] && .venv/bin/python -I -c "import sys" >/dev/null 2>&1; then
  .venv/bin/python -B -E -s framescout_check.py
  RESULT=$?
  if [ "$RESULT" -eq 0 ] || [ "$RESULT" -eq 2 ]; then exit "$RESULT"; fi
  echo
  echo "The check could not run with the Python of .venv; trying the private Python in .python."
  echo
fi
if [ ! -x .python/bin/python3 ]; then
  echo "The Python environment in .venv does not work or is missing, and there is no"
  echo "private Python in .python. Run Install-FrameScout.sh; it installs both."
  exit 1
fi
.python/bin/python3 -B -E -s framescout_check.py
RESULT=$?
if [ "$RESULT" -eq 0 ] || [ "$RESULT" -eq 2 ]; then exit "$RESULT"; fi
echo
echo "The check could not run (see the error above). Close FrameScout and run"
echo "Install-FrameScout.sh; it repairs the Python environment. If that does not help,"
echo "download FrameScout again into a new folder and install it there."
exit 1
