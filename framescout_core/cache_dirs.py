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


def yolo_weights(name, base, cwd, replace=os.replace):
    """The path the detector loads its weights from, and downloads them to on first use (E9).

    Ultralytics downloads an official weights file given by its bare name into the working
    folder, which put yolo11n.pt into the project folder. A bare name is therefore looked up
    in base/.cache/ultralytics; the default file an older version downloaded into base is
    moved there once (kept and used where it is if it cannot be moved). A file of that name
    in the working folder cwd is used as before; any other path or URL is used as given.
    """
    if Path(name).name != name:
        return name
    cached = cache_paths(base)['YOLO_CONFIG_DIR'] / name
    if cached.is_file():
        return str(cached)
    legacy = Path(base) / name
    if name == DEFAULT_YOLO_MODEL and legacy.is_file():
        try:
            cached.parent.mkdir(parents=True, exist_ok=True)
            replace(legacy, cached)
        except OSError:
            # e.g. in use, or another search moved it meanwhile
            return str(cached) if cached.is_file() or not legacy.is_file() else str(legacy)
        return str(cached)
    if (Path(cwd) / name).is_file():
        return name
    return str(cached)
