"""Model downloads and library config files under the project's .cache folder (E9, I10).

The .bat files, the app and the evaluation tool set the cache variables for the engine;
a manual engine run gets the same folders from default_cache_env, so nothing lands in the
user profile and the uninstall stays clean.
"""
import os
from pathlib import Path

from .signature import DEFAULT_YOLO_MODEL

CACHE_DIR = '.cache'


def cache_paths(base):
    """The cache variables and their folders under base/.cache, as the .bat files set them."""
    cache = Path(base) / CACHE_DIR
    return {'TORCH_HOME': cache / 'torch', 'HF_HOME': cache / 'huggingface',
            'YOLO_CONFIG_DIR': cache / 'ultralytics', 'XDG_CACHE_HOME': cache}


def default_cache_env(environ, base):
    """Set the cache variables that are unset or empty in environ to base/.cache (I10).

    A value the user set is kept. Must run before torch, huggingface_hub and Ultralytics
    are imported (they read some of the variables on import). Creates no folder; returns
    the names it set.
    """
    added = []
    for name, path in cache_paths(base).items():
        if not environ.get(name):
            environ[name] = str(path)
            added.append(name)
    return added


def yolo_weights(name, base, cwd, environ, log=None, replace=os.replace):
    """The path the detector loads its weights from, and downloads them to on first use (E9).

    Ultralytics downloads an official weights file given by its bare name into the working
    folder, which put yolo11n.pt into the project folder. A bare name is therefore looked up
    in the folder of YOLO_CONFIG_DIR in environ (base/.cache/ultralytics if unset; a value
    the user set is kept, review); the default file an older version downloaded into base is
    moved there once, unless a copy is there already (kept and used where it is if it cannot
    be moved; log, if given, gets a line about it). A file of that name in the working folder
    cwd is used as before; any other path or URL is used as given.
    """
    if Path(name).name != name:
        return name
    folder = environ.get('YOLO_CONFIG_DIR') or cache_paths(base)['YOLO_CONFIG_DIR']
    cached = Path(folder) / name
    if cached.is_file():
        return str(cached)
    legacy = Path(base) / name
    if name == DEFAULT_YOLO_MODEL and legacy.is_file():
        try:
            cached.parent.mkdir(parents=True, exist_ok=True)
            replace(legacy, cached)
        except OSError as exc:
            if cached.is_file() or not legacy.is_file():  # another search moved it meanwhile
                return str(cached)
            if log:
                log(f'Could not move {legacy} to {cached}, using it where it is: {exc}')
            return str(legacy)
        return str(cached)
    if (Path(cwd) / name).is_file():
        return name
    return str(cached)
