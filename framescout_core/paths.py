"""Where the shipped files lie in the FrameScout folder.

The shipped files lie in requirements/ (the installer's requirement files) and assets/
(files the programs read), not loose in the root folder. Every program, message and test builds these
paths from the constants here, so a later move changes one place. Relative to the FrameScout
folder; a leaf module (no other FrameScout import), so any module of the package can use it.
Messages for the user name a path as this system shows it (str of the Path) and a script by
the name it has on this system (script). WINDOWS is the one test for the platform the
Windows/Linux decisions of the package use.
"""
import os
from pathlib import Path

REQUIREMENTS_DIR = Path('requirements')
REQUIREMENTS_FILE = REQUIREMENTS_DIR / 'requirements.txt'
CONSTRAINTS_FILE = REQUIREMENTS_DIR / 'constraints.txt'
ASSETS_DIR = Path('assets')
EXAMPLE_PROFILES_FILE = ASSETS_DIR / 'profiles.example.json'
EVAL_PAGE_FILE = ASSETS_DIR / 'framescout_eval_page.html'


# Windows (the .bat files, the environment's Scripts folder) or else Linux
WINDOWS = os.name == 'nt'
# the scripts the user runs (Install-, Start-, Check-, Uninstall-FrameScout): .bat files on
# Windows, .sh scripts of the same names on Linux
SCRIPT_SUFFIX = '.bat' if WINDOWS else '.sh'


def script(name, suffix=SCRIPT_SUFFIX):
    """The file name of the FrameScout script name ("Install", "Start", ...) on this system, e.g. Install-FrameScout.bat."""
    return f'{name}-FrameScout{suffix}'
