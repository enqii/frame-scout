#!/usr/bin/env bash
# Usage: ./Install-FrameScout.sh [cpu|cuda]
# The Linux counterpart of Install-FrameScout.bat (F47): same steps, same exit codes.
# Without an argument, an installed CUDA build of PyTorch is kept; otherwise GPU support
# is offered if an NVIDIA graphics driver is found. "cpu" or "cuda" switches the build.
set -u
cd -- "$(dirname -- "$0")" || exit 1
TORCH_VARIANT="$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')"
if [ -n "$TORCH_VARIANT" ] && [ "$TORCH_VARIANT" != cpu ] && [ "$TORCH_VARIANT" != cuda ]; then
  echo "Usage: ./Install-FrameScout.sh [cpu|cuda]"
  echo "  cpu    PyTorch for the CPU"
  echo "  cuda   PyTorch with CUDA support for an NVIDIA GPU"
  echo "Without an argument, FrameScout keeps an installed CUDA build, otherwise it asks"
  echo "if an NVIDIA graphics driver is found."
  exit 1
fi
# I42: each version has one framescout-version-<version>.txt. A ZIP extracted over the
# folder of another version leaves both files, and files of two versions must not run
# together: stop before anything is downloaded or installed. Start-FrameScout.sh has the
# same lines (a test compares them).
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
export PIP_CACHE_DIR="$PWD/.cache/pip"
# Model downloads and library settings go to .cache, unless the user set a variable
# (A36): as for a manual engine run, that one wins. With the user's XDG_CACHE_HOME, torch and
# Hugging Face use its folders, so these two lines come first. Start-FrameScout.sh has the same lines.
if [ -z "${TORCH_HOME:-}" ] && [ -z "${XDG_CACHE_HOME:-}" ]; then export TORCH_HOME="$PWD/.cache/torch"; fi
if [ -z "${HF_HOME:-}" ] && [ -z "${XDG_CACHE_HOME:-}" ]; then export HF_HOME="$PWD/.cache/huggingface"; fi
if [ -z "${YOLO_CONFIG_DIR:-}" ]; then export YOLO_CONFIG_DIR="$PWD/.cache/ultralytics"; fi
if [ -z "${XDG_CACHE_HOME:-}" ]; then export XDG_CACHE_HOME="$PWD/.cache"; fi
export TMPDIR="$PWD/.tmp"
mkdir -p .tmp || exit 1

# New installations get a private Python in .python, as on Windows: python.org has no
# Linux build, so it is the standalone build of python-build-standalone, checked against
# its published SHA-256, so no Python has to be installed. framescout_core.portable_python
# pins the same values (a test). .venv refers to .python by its path: the folder cannot be
# moved afterwards.
PYTHON_VERSION="3.14.9"
PYTHON_URL="https://github.com/astral-sh/python-build-standalone/releases/download/20261021/cpython-3.14.9%2B20261021-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz"
PYTHON_SHA256="561e91c1cadf30e84aec94d1917384ae3267e5f3e6e135e51fd1578bb19f4064"
PYTHON_ARCHIVE=".tmp/python-$PYTHON_VERSION-linux.tar.gz"
PYTHON_UNPACKED=".tmp/python-$PYTHON_VERSION"

failed() {
  for line in "$@"; do echo "$line"; done
  exit 1
}

# A .python is reused only if it is complete and the pinned version (I24): a leftover of an
# uninstall that stopped halfway, or the Python of an older pin, is downloaded again.
private_python_works() {
  [ -x .python/bin/python3 ] && .python/bin/python3 -I -c "import sys, platform, venv, ensurepip; sys.exit(platform.python_version() not in sys.argv[1:])" "$PYTHON_VERSION" >/dev/null 2>&1
}

download_python() {
  # first, so that an existing .python is kept when the download cannot happen anyway
  if [ "$(uname -m)" != x86_64 ]; then
    failed "FrameScout's private Python for Linux is built for 64-bit x86 processors (x86_64);" \
           "this computer has $(uname -m)."
  fi
  if ! command -v curl >/dev/null 2>&1; then
    failed "Downloading Python needs the program curl. Install it (e.g. sudo apt install curl)" \
           "and run the installer again."
  fi
  if [ -e .python ] || [ -L .python ]; then
    echo "The private Python in .python is incomplete or not Python $PYTHON_VERSION, so it is"
    echo "downloaded again."
    rm -rf .python
    if [ -e .python ] || [ -L .python ]; then
      failed "The folder .python has to be downloaded again but cannot be deleted. Delete the" \
             "folder .python in this folder and run the installer again."
    fi
  fi
  echo "Downloading Python $PYTHON_VERSION (about 37 MB) from GitHub (python-build-standalone) ..."
  if ! curl -fL --retry 3 -o "$PYTHON_ARCHIVE" "$PYTHON_URL"; then
    failed "Downloading Python failed. Check the internet connection (and the proxy settings, if" \
           "you use a proxy) and run the installer again."
  fi
  if [ "$(sha256sum "$PYTHON_ARCHIVE" | cut -d ' ' -f 1)" != "$PYTHON_SHA256" ]; then
    rm -f "$PYTHON_ARCHIVE"
    failed "The downloaded Python does not match the checksum (SHA-256) that its publisher" \
           "publishes, so it is not used. Run the installer again; if this happens again," \
           "something changes the download on its way (e.g. a proxy)."
  fi
  rm -rf "$PYTHON_UNPACKED"
  mkdir -p "$PYTHON_UNPACKED" || exit 1
  if ! tar -xzf "$PYTHON_ARCHIVE" -C "$PYTHON_UNPACKED" || [ ! -x "$PYTHON_UNPACKED/python/bin/python3" ]; then
    failed "Extracting Python failed. See the error message above, then run the installer again."
  fi
  # Moved as a whole: an interrupted extraction never leaves a .python that looks complete.
  if ! mv "$PYTHON_UNPACKED/python" .python; then
    failed "Moving the extracted Python to .python failed (see the message above). Run the" \
           "installer again."
  fi
  rm -rf "$PYTHON_UNPACKED" "$PYTHON_ARCHIVE"
}

create_venv() {
  echo "Creating the Python environment with the private Python in .python"
  # --clear: a .venv that gets here does not work
  if ! .python/bin/python3 -I -m venv --clear .venv; then
    # a half-created .venv could pass the check below on the next run
    rm -rf .venv
    failed "Creating the virtual environment failed. See the error message above. If it fails" \
           "again, delete the folder .python (the installer downloads it again) and run the" \
           "installer again."
  fi
}

venv_works() {
  [ -x .venv/bin/python ] && .venv/bin/python -I -c "import pip" >/dev/null 2>&1
}

# An existing environment that starts and has pip is kept.
if ! venv_works; then
  if [ -e .venv ]; then
    # Its Python is gone (.python deleted, the folder moved) or venv stopped before pip was
    # installed. It is used again if it works with the private Python, otherwise it is
    # created again.
    echo "The Python environment in .venv does not work: its Python or pip is missing. The"
    echo "installer repairs it."
  fi
  if ! private_python_works; then
    download_python
  fi
  # a .venv of the private Python works again now that .python is complete again
  if ! venv_works; then
    create_venv
  fi
fi

# requirements/constraints.txt pins every package, including the dependencies of the
# dependencies, to the version of the verified runs (I12); requirements/requirements.txt
# names the direct dependencies. PIP_CONSTRAINT applies the pins to the pip call of
# install_torch.py too (I18). Relative: pip splits its value at spaces.
export PIP_CONSTRAINT="requirements/constraints.txt"
# PyTorch first (CPU or CUDA build); requirements.txt pins the same version. Exit code 3:
# the user stopped on low disk space (F3), not a failure. Exactly 3, unlike the .bat's
# "errorlevel 3": a process killed by a signal (OOM killer, Ctrl+C) exits with 128 + n.
.venv/bin/python install_torch.py ${TORCH_VARIANT:+"$TORCH_VARIANT"}
TORCH_RESULT=$?
if [ "$TORCH_RESULT" -eq 3 ]; then
  failed "Installation stopped. Free some disk space, then run Install-FrameScout.sh again."
fi
if [ "$TORCH_RESULT" -ne 0 ]; then
  failed "Installing PyTorch failed. See the error message above."
fi
if ! .venv/bin/python -m pip install --no-cache-dir -r requirements/requirements.txt -c requirements/constraints.txt; then
  failed "Installation failed. See the error message above."
fi
if ! .venv/bin/python -c "import torch,open_clip,ultralytics,streamlit,pillow_heif,rawpy;print('FrameScout: import test OK');print('PyTorch', torch.__version__, '- CUDA available:', torch.cuda.is_available())"; then
  failed "The import test failed. See the error message above."
fi
exit 0
