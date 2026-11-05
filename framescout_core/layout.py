"""Program files of two FrameScout versions in one folder (I16).

FrameScout before I15 had the single file framescout_core.py; newer versions have this
package. A ZIP extracted over a folder of another version leaves both, and Python always
imports the package. After an update that is harmless (Install-FrameScout.bat and
Start-FrameScout.bat delete the leftover file), but after going back to an older version
the older app.py would silently run against this newer core (another ENGINE and cache
signature). The package cannot tell the two cases apart, so __init__.py refuses to load
next to the single file and names both fixes.
"""
import os
import sys

# the single file of FrameScout before I15, next to the package in the FrameScout folder
OBSOLETE_CORE_FILE = 'framescout_core.py'

# Scripts that only versions with the package have and that import no other FrameScout
# module (a test checks that): next to the single file they are never an older version's,
# so the package loads for them. The uninstall has to work in such a folder too (review);
# Uninstall-FrameScout.bat does not delete the single file, which after going back to a
# version before I15 (without an uninstaller) is that version's core.
PACKAGE_ONLY_SCRIPTS = ('framescout_uninstall.py',)


def mixed_versions_message(folder):
    """The error text if `folder` holds OBSOLETE_CORE_FILE (next to the package), else None."""
    if not os.path.isfile(os.path.join(folder, OBSOLETE_CORE_FILE)):
        return None
    return (f'The FrameScout folder {folder} holds framescout_core.py next to the folder '
            'framescout_core: files of two FrameScout versions, left when a ZIP is extracted over '
            'another version. If you updated to a newer version, delete framescout_core.py '
            '(Install-FrameScout.bat and Start-FrameScout.bat do that). If you went back to an older '
            'version, delete the folder framescout_core, which the older version does not use. '
            'Extracting a downloaded ZIP into a new, empty folder avoids this.')


def refused_import(folder, main_file):
    """The error text if the package in `folder` must not load for the script `main_file`, else None.

    `main_file` is the path of the running script (None without one, e.g. python -c).
    """
    problem = mixed_versions_message(folder)
    if problem and main_file and os.path.basename(main_file) in PACKAGE_ONLY_SCRIPTS:
        script_folder = os.path.dirname(os.path.abspath(main_file))
        if os.path.normcase(script_folder) == os.path.normcase(os.path.abspath(folder)):
            return None
    return problem


def refuse_mixed_versions(package_file):
    """Raise ImportError if the package of `package_file` must not load (called by __init__.py)."""
    folder = os.path.dirname(os.path.dirname(os.path.abspath(package_file)))
    problem = refused_import(folder, getattr(sys.modules.get('__main__'), '__file__', None))
    if problem:
        raise ImportError(problem)
