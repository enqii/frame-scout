#!/usr/bin/env bash
# Usage: ./Start-FrameScout.sh
# The Linux counterpart of Start-FrameScout.bat (F47).
set -u
cd -- "$(dirname -- "$0")" || exit 1
# I42: each version has one framescout-version-<version>.txt. A ZIP extracted over the
# folder of another version leaves both files, and files of two versions must not run
# together: stop before any Python runs. Install-FrameScout.sh has the same lines (a test
# compares them).
shopt -s nullglob
VERSION_FILES=(framescout-version-*.txt)
shopt -u nullglob
if [ "${#VERSION_FILES[@]}" -gt 1 ]; then
  echo "This folder holds files of two FrameScout versions (more than one"
  echo "framescout-version-*.txt), left when a ZIP is extracted over another version."
  echo "Extract the ZIP of the version you want into a new, empty folder and copy your"
  echo "data from this folder into it: profiles.json, settings.json and the folders photos,"
  echo "references, results and .cache (downloaded models, so they are not downloaded"
  echo "again). Then run Install-FrameScout.sh there."
  exit 1
fi
# Model downloads and library settings go to .cache, unless the user set a variable
# (A36): as for a manual engine run, that one wins. With the user's XDG_CACHE_HOME, torch and
# Hugging Face use its folders, so these two lines come first. Install-FrameScout.sh has the same lines.
if [ -z "${TORCH_HOME:-}" ] && [ -z "${XDG_CACHE_HOME:-}" ]; then export TORCH_HOME="$PWD/.cache/torch"; fi
if [ -z "${HF_HOME:-}" ] && [ -z "${XDG_CACHE_HOME:-}" ]; then export HF_HOME="$PWD/.cache/huggingface"; fi
if [ -z "${YOLO_CONFIG_DIR:-}" ]; then export YOLO_CONFIG_DIR="$PWD/.cache/ultralytics"; fi
if [ -z "${XDG_CACHE_HOME:-}" ]; then export XDG_CACHE_HOME="$PWD/.cache"; fi
export TMPDIR="$PWD/.tmp"
mkdir -p .tmp || exit 1
if [ ! -x .venv/bin/python ]; then
  echo "The Python environment is missing. Please run Install-FrameScout.sh first."
  exit 1
fi
# F22: framescout_start.py runs the app on 127.0.0.1, port 8501 or the next free one up to
# 8510, or opens the browser on the app of this folder if it runs already.
exec .venv/bin/python framescout_start.py
