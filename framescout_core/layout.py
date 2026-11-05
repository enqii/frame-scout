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

# the single file of FrameScout before I15, next to the package in the FrameScout folder
OBSOLETE_CORE_FILE = 'framescout_core.py'


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
