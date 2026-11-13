"""The app's folders and files, Markdown escaping, widget keys and opening files on this computer (A46)."""
import functools
import hashlib
import os
import platform
import re
import subprocess
import threading
from pathlib import Path

import streamlit as st

from framescout_core import (EXAMPLE_PROFILES_FILE, EXPORTS_DIR, MARKS_FILE, QUICK_DIR, QUICK_GALLERY, RESULTS_FILE,
                             RUN_LOCK, RUN_STATUS, SETTINGS_FILE, available_decoders, open_command, openable_photo,
                             project_temp_cleanup, reveal_command, supported_extensions)

# the project folder: app.py's folder, one above this package
BASE = Path(__file__).resolve().parent.parent
PROFILES = BASE / 'profiles.json'  # the user's working file, not in the repository
SETTINGS = BASE / SETTINGS_FILE  # the user's settings (A8), not in the repository
EXAMPLE_PROFILES = BASE / EXAMPLE_PROFILES_FILE
REFS = BASE / 'references'
RESULTS = BASE / 'results'
LOG = BASE / 'run.log'
# held by the engine while it runs, and its phase and progress (A4, A5)
LOCK = RESULTS / RUN_LOCK
STATUS = RESULTS / RUN_STATUS
# what the galleries of the last search show (A12) and their thumbnails
RESULTS_JSON = RESULTS / RESULTS_FILE
THUMBS = RESULTS / 'thumbnails'
# the last quick search (F10): its own gallery, result file and thumbnails, apart from the
# profiles' galleries and marks
QUICK = RESULTS / QUICK_DIR
QUICK_JSON = QUICK / RESULTS_FILE
QUICK_THUMBS = QUICK / 'thumbnails'
# the user's marks of gallery photos (A17): user data, never deleted by FrameScout
MARKS = RESULTS / MARKS_FILE
# exported result lists (F5): user data, never deleted by FrameScout
EXPORTS = RESULTS / EXPORTS_DIR


# Markdown characters, escaped in file names shown with st.markdown/st.caption
MARKDOWN_CHARS = re.compile(r'([\\`*_{}\[\]()#+\-.!|<>~$])')


@st.cache_resource
def decoders():
    """The engine's Decoders (E25): it runs in the same Python environment and checks the same way (review)."""
    return available_decoders()


# computed once, when app.py first imports this module in a page run (before A46: in every
# page run, from the same cached Decoders)
DECODERS = decoders()
SUPPORTED = supported_extensions(DECODERS)
UPLOAD_TYPES = sorted(x.lstrip('.') for x in SUPPORTED)


def open_path(path):
    """Open the file or folder path with its default program on the computer the app runs on."""
    if os.name == 'nt':
        os.startfile(str(path))
    else:
        start_launcher(open_command(path, platform.system()))

def start_launcher(cmd):
    """Start cmd (open, xdg-open) without waiting; a thread reaps it, so no zombie stays (review)."""
    process = subprocess.Popen(cmd)
    threading.Thread(target=process.wait, daemon=True).start()

def reveal_path(path):
    """Show the file path in the file manager of the computer the app runs on, selected if possible."""
    if os.name != 'nt':
        start_launcher(reveal_command(path, platform.system()))
        return
    # the shell function behind "explorer /select,", which did not select a file with a
    # comma in its name (checked on Windows 11); COM is initialized for this script thread
    import ctypes
    from ctypes import wintypes
    ole32, shell32 = ctypes.windll.ole32, ctypes.windll.shell32
    shell32.ILCreateFromPathW.restype = ctypes.c_void_p
    shell32.ILCreateFromPathW.argtypes = [wintypes.LPCWSTR]
    shell32.ILFree.argtypes = [ctypes.c_void_p]
    shell32.SHOpenFolderAndSelectItems.argtypes = [ctypes.c_void_p, wintypes.UINT, ctypes.c_void_p, wintypes.DWORD]
    # S_OK or S_FALSE: this call holds a reference to undo; a thread whose COM was
    # initialized in another mode (RPC_E_CHANGED_MODE, negative) must keep it (review)
    initialized = ole32.CoInitialize(None) >= 0
    try:
        item = shell32.ILCreateFromPathW(str(path))
        if not item:
            raise OSError(f'Windows does not find {path}')
        try:
            result = shell32.SHOpenFolderAndSelectItems(item, 0, None, 0)
        finally:
            shell32.ILFree(item)
    finally:
        if initialized:
            ole32.CoUninitialize()
    if result < 0:  # FAILED(); a success code such as S_FALSE is no error (review)
        raise OSError(f'Explorer reported error {result & 0xFFFFFFFF:#010x}')

def gallery_action(action, path, what):
    """Run action(path) for a gallery button; a failure becomes a note above the gallery."""
    if path is None:
        st.session_state.gallery_notice = f'{what} no longer exists.'
        return
    try:
        action(path)
    except OSError as exc:
        st.session_state.gallery_notice = f'{what} could not be opened: {exc}'

def open_photo(path):
    # only an existing image file: never start a program named in results.json
    gallery_action(open_path, openable_photo(path), f'The photo {path}')

def show_photo(path):
    gallery_action(reveal_path, openable_photo(path), f'The photo {path}')

def open_gallery(name):
    page = RESULTS / name  # a plain file name, checked by read_results
    gallery_action(open_path, page if page.is_file() else None, f'The gallery {page}')

def open_results_folder():
    gallery_action(open_path, RESULTS if RESULTS.is_dir() else None, f'The results folder {RESULTS}')

def open_quick_gallery():
    page = QUICK / QUICK_GALLERY
    gallery_action(open_path, page if page.is_file() else None, f'The gallery {page}')

def open_quick_folder():
    gallery_action(open_path, QUICK if QUICK.is_dir() else None, f'The quick search folder {QUICK}')

@functools.lru_cache(maxsize=1)
def pictures_folder():
    """Return the user's Pictures folder (also when Windows has moved it, e.g. to OneDrive)."""
    if os.name == 'nt':
        import ctypes
        import uuid
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [('Data1', wintypes.DWORD), ('Data2', wintypes.WORD), ('Data3', wintypes.WORD),
                        ('Data4', ctypes.c_ubyte * 8)]

        # FOLDERID_Pictures
        folder_id = GUID.from_buffer_copy(uuid.UUID('33E28130-4E1E-4676-835A-98395C3BC3BB').bytes_le)
        found = ctypes.c_void_p()
        shell32 = ctypes.windll.shell32
        shell32.SHGetKnownFolderPath.argtypes = [ctypes.POINTER(GUID), wintypes.DWORD, wintypes.HANDLE,
                                                 ctypes.POINTER(ctypes.c_void_p)]
        ctypes.windll.ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
        try:
            if shell32.SHGetKnownFolderPath(ctypes.byref(folder_id), 0, None, ctypes.byref(found)) == 0:
                return Path(ctypes.wstring_at(found.value))
        finally:
            ctypes.windll.ole32.CoTaskMemFree(found)  # also on failure (documented), None is allowed
    return Path.home() / 'Pictures'

def widget_id(*parts):
    """A short stable key part for widgets of a profile or photo (names and paths may hold any character)."""
    return hashlib.sha256('\0'.join(parts).encode('utf-8')).hexdigest()[:16]

def version_key(path):
    """(path, mtime_ns, size, file id) of path: the cache key of the files saved by replacing them.

    With the file id, which changes with every atomic replace, so two saves of the same size
    within the time resolution of the file system (2 s on FAT) still count as a change.
    """
    stat = Path(path).stat()
    return str(path), stat.st_mtime_ns, stat.st_size, stat.st_ino


def file_key(path):
    """(path, mtime_ns, size) of path, the cache key of the functions above."""
    stat = Path(path).stat()
    return str(path), stat.st_mtime_ns, stat.st_size


def plain(text):
    """Return text with its Markdown characters escaped, e.g. a file name for st.markdown/st.caption."""
    return MARKDOWN_CHARS.sub(r'\\\1', text)


@st.cache_resource(show_spinner=False)
def clean_project_folder():
    """Once per app start: remove the temporary files a killed app left in the project folder (E44)."""
    try:
        return project_temp_cleanup(BASE)
    except OSError:  # e.g. a read-only project folder: never stops the app
        return None
