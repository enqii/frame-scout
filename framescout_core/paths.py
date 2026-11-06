"""Where the shipped files lie in the FrameScout folder (I31).

I31 moved the loose files of the root folder into requirements/ (the installer's requirement
files) and assets/ (files the programs read). Every program, message and test builds these
paths from the constants here, so a later move changes one place. Relative to the FrameScout
folder; a leaf module (no other FrameScout import), so any module of the package can use it.
Messages for the user name a path in its Windows form (windows_path).
"""
from pathlib import Path, PureWindowsPath

REQUIREMENTS_DIR = Path('requirements')
REQUIREMENTS_FILE = REQUIREMENTS_DIR / 'requirements.txt'
CONSTRAINTS_FILE = REQUIREMENTS_DIR / 'constraints.txt'
ASSETS_DIR = Path('assets')
EXAMPLE_PROFILES_FILE = ASSETS_DIR / 'profiles.example.json'
EVAL_PAGE_FILE = ASSETS_DIR / 'framescout_eval_page.html'


def windows_path(path):
    """The relative path as Windows Explorer and cmd show it (requirements\\constraints.txt) on any system."""
    return str(PureWindowsPath(path))
