#!/usr/bin/env bash
# Usage: ./Uninstall-FrameScout.sh [--dry-run]
# The Linux counterpart of Uninstall-FrameScout.bat: deletes what the installer and
# FrameScout create again (.venv, the private Python in .python, .cache, .tmp, the person
# detection model, compiled files) after showing the list and asking. Never deletes your
# photos, references, results, profiles or settings. --dry-run only shows the list.
# It runs with the private Python of the installer (.python), never with .venv's own
# Python. The script deletes everything else and ends with exit code 3
# (framescout_core.uninstall.PRIVATE_PYTHON_EXIT_CODE) only after "yes", never in a dry run
# or when .python is not to be deleted; then this file deletes .python, as the .bat does.
# No cache or TMPDIR variables are set here: .tmp is deleted, and the script reports the
# user's caches.
set -u
cd -- "$(dirname -- "$0")" || exit 1
if [ ! -x .python/bin/python3 ]; then
  echo "There is no private Python in .python to run the uninstall."
  echo "To delete the environment by hand, close FrameScout and delete the folders .venv,"
  echo ".python, .cache and .tmp in \"$PWD\""
  echo "(keep .tmp/eval if you labelled photos with the evaluation tool)."
  exit 1
fi
.python/bin/python3 -B -E -s framescout_uninstall.py "$@"
EXIT_CODE=$?
if [ "$EXIT_CODE" -ne 3 ]; then exit "$EXIT_CODE"; fi
# The script has ended, so its Python can go now: bin/python3 first, so a .python whose
# deletion stops halfway never looks complete to the installer.
rm -f .python/bin/python3
rm -rf .python
if [ -e .python ]; then
  echo "The private Python in .python could not be deleted completely. Delete the folder"
  echo ".python yourself."
  exit 1
fi
echo "The private Python (.python) was deleted too."
exit 0
