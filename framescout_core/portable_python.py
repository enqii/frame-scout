"""The private Python of a new installation (P5 part C): what Install-FrameScout.bat downloads.

Install-FrameScout.bat downloads python.org's full Windows package (a ZIP, not the
installer) into .tmp, checks its SHA-256, extracts it to PRIVATE_PYTHON in the FrameScout
folder and creates .venv with it, so no Python has to be installed on the PC. The .bat
holds the same values; a test keeps them in sync. An environment that an older installer
created with an installed Python is kept as it is.
"""


# Python version of new installations (user decision 2026-10-27: one tested Python 3.14)
PYTHON_VERSION = '3.14.9'
# python.org's full package for 64-bit Windows and its SHA-256 as published in
# https://www.python.org/ftp/python/3.14.9/windows-3.14.9.json (checked against the
# downloaded file when this was written)
PYTHON_URL = 'https://www.python.org/ftp/python/3.14.9/python-3.14.9-amd64.zip'
PYTHON_SHA256 = '874d01bac04b470c6e1422dfccb9e182b9efe90c6a8adc5fc50d66bf84c40191'
# the folder in the FrameScout folder that holds it; .venv refers to it by its absolute
# path, so the FrameScout folder cannot be moved after the installation
PRIVATE_PYTHON = '.python'
