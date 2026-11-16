"""The private Python of a new installation (P5 part C, F47): what the installers download.

Install-FrameScout.bat downloads python.org's full Windows package (a ZIP, not the
installer) into .tmp, checks its SHA-256, extracts it to PRIVATE_PYTHON in the FrameScout
folder and creates .venv with it, so no Python has to be installed on the PC.
Install-FrameScout.sh does the same on Linux with a standalone build of the same version.
The scripts hold the same values; tests keep them in sync.
"""


# Python version of new installations, the same on Windows and Linux (user decisions
# 2026-10-27: one tested Python 3.14; 2026-11-16: Linux gets the same private Python)
PYTHON_VERSION = '3.14.9'
# python.org's full package for 64-bit Windows and its SHA-256 as published in
# https://www.python.org/ftp/python/3.14.9/windows-3.14.9.json (checked against the
# downloaded file when this was written)
PYTHON_URL = 'https://www.python.org/ftp/python/3.14.9/python-3.14.9-amd64.zip'
PYTHON_SHA256 = '874d01bac04b470c6e1422dfccb9e182b9efe90c6a8adc5fc50d66bf84c40191'
# python.org publishes no Linux build: the standalone build of python-build-standalone
# (the "install_only_stripped" archive for 64-bit x86 Linux with glibc, which unpacks to
# python/) and its SHA-256 as published in the release's SHA256SUMS (checked against the
# downloaded file when this was written)
LINUX_PYTHON_RELEASE = '20261021'
LINUX_PYTHON_URL = ('https://github.com/astral-sh/python-build-standalone/releases/download/20261021/'
                    'cpython-3.14.9%2B20261021-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz')
LINUX_PYTHON_SHA256 = '561e91c1cadf30e84aec94d1917384ae3267e5f3e6e135e51fd1578bb19f4064'
# the folder in the FrameScout folder that holds it; .venv refers to it by its absolute
# path, so the FrameScout folder cannot be moved after the installation
PRIVATE_PYTHON = '.python'
