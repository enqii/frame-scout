"""The single file framescout_scoring.py of an older version next to this package (I36).

FrameScout before I30 had the single file framescout_scoring.py. A ZIP of such a version
extracted over a newer folder leaves this package, which Python imports instead of the older
version's file: the older engine would silently score with this newer code. So the package
refuses to load next to the single file, like framescout_core next to framescout_core.py
(framescout_core.layout, I16), unless the running script carries the marker of a version with
the packages (I35).

Written out instead of imported from framescout_core: after going back to an older version,
framescout_core may be that version's, without these functions. A test checks that the
marker and the message equal framescout_core.layout's.
"""
import os
import sys

PACKAGE = 'framescout_scoring'
LAYOUT_MARKER = 'FRAMESCOUT_PACKAGES'


def scoring_leftover_message(folder):
    """The error text if `folder` holds framescout_scoring.py (next to this package), else None."""
    if not os.path.isfile(os.path.join(folder, f'{PACKAGE}.py')):
        return None
    return (f'The FrameScout folder {folder} holds {PACKAGE}.py next to the folder {PACKAGE}: files of two '
            'FrameScout versions, left when a ZIP is extracted over another version. If you updated to a newer '
            f'version, delete {PACKAGE}.py (Install-FrameScout.bat and Start-FrameScout.bat do that). If you went '
            f'back to an older version, delete the folder {PACKAGE}, which the older version does not use. '
            'Extracting a downloaded ZIP into a new, empty folder avoids this.')


def scoring_import_refused(folder, main_module):
    """The error text if this package in `folder` must not load for the running script `main_module`, else None."""
    problem = scoring_leftover_message(folder)
    main_file = getattr(main_module, '__file__', None)
    if problem and main_file and getattr(main_module, LAYOUT_MARKER, None) is True:
        script_folder = os.path.dirname(os.path.abspath(main_file))
        if os.path.normcase(script_folder) == os.path.normcase(os.path.abspath(folder)):
            return None
    return problem


def refuse_scoring_leftover(package_file):
    """Raise ImportError if the package of `package_file` must not load (called by __init__.py)."""
    folder = os.path.dirname(os.path.dirname(os.path.abspath(package_file)))
    problem = scoring_import_refused(folder, sys.modules.get('__main__'))
    if problem:
        raise ImportError(problem)
