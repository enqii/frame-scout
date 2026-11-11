"""Program files of two FrameScout versions in one folder (I16, I35, I36).

FrameScout before I15 had the single file framescout_core.py, before I30 framescout_scoring.py;
newer versions have the packages framescout_core and framescout_scoring. A ZIP extracted over
a folder of another version leaves both, and Python always imports the package. After an
update that is harmless (Install-FrameScout.bat and Start-FrameScout.bat delete the leftover
files), but after going back to an older version the older app.py would silently run against
this newer core (another ENGINE and cache signature). So __init__.py refuses to load next to
the single file and names both fixes, unless the running script is of a version with the
packages: every entry point of such a version (app.py, the engine, install_torch.py, the
evaluation tool, the check and the uninstall) sets LAYOUT_MARKER as a global before it imports
a FrameScout module (I35). An older version's script lacks it. framescout_scoring has the same
guard (I36), written out there, since after going back to an older version this package may be
that version's.
"""
import os
import sys

# the packages that replaced a single file <package>.py of an older version
CORE_PACKAGE = 'framescout_core'
SCORING_PACKAGE = 'framescout_scoring'
REPLACED_PACKAGES = (CORE_PACKAGE, SCORING_PACKAGE)
# the single file of FrameScout before I15, next to the package in the FrameScout folder
OBSOLETE_CORE_FILE = f'{CORE_PACKAGE}.py'
# the global that the entry points of a version with the packages set to True (I35); the
# scripts write it out, since they set it before they import a FrameScout module (a test checks that)
LAYOUT_MARKER = 'FRAMESCOUT_PACKAGES'


def leftover_text(package):
    """What a single file <package>.py next to the folder `package` is (for the check and the guard)."""
    return (f'{package}.py next to the folder {package}: files of two FrameScout versions, left when a '
            'ZIP is extracted over another version.')


def leftover_fix(package):
    """The two fixes for leftover_text(package): the user knows whether they updated or went back."""
    return (f'If you updated to a newer version, delete {package}.py (Install-FrameScout.bat and '
            f'Start-FrameScout.bat do that). If you went back to an older version, delete the folder '
            f'{package}, which the older version does not use.')


def mixed_versions_message(folder, package=CORE_PACKAGE):
    """The error text if `folder` holds the single file <package>.py (next to the package), else None."""
    if not os.path.isfile(os.path.join(folder, f'{package}.py')):
        return None
    return (f'The FrameScout folder {folder} holds {leftover_text(package)} {leftover_fix(package)} '
            'Extracting a downloaded ZIP into a new, empty folder avoids this.')


def marked_script(folder, main_module):
    """True if `main_module` (the running script's module) is an entry point with LAYOUT_MARKER in `folder`."""
    main_file = getattr(main_module, '__file__', None)
    if not main_file or getattr(main_module, LAYOUT_MARKER, None) is not True:
        return False
    script_folder = os.path.dirname(os.path.abspath(main_file))
    return os.path.normcase(script_folder) == os.path.normcase(os.path.abspath(folder))


def refused_import(folder, main_module, package=CORE_PACKAGE):
    """The error text if the package in `folder` must not load for the running script, else None.

    `main_module` is sys.modules['__main__'] (Streamlit's module of app.py while the app runs;
    without a script, e.g. python -c, it has no __file__).
    """
    problem = mixed_versions_message(folder, package)
    if problem and marked_script(folder, main_module):
        return None
    return problem


def refuse_mixed_versions(package_file):
    """Raise ImportError if the package of `package_file` must not load (called by __init__.py)."""
    folder = os.path.dirname(os.path.dirname(os.path.abspath(package_file)))
    problem = refused_import(folder, sys.modules.get('__main__'))
    if problem:
        raise ImportError(problem)
