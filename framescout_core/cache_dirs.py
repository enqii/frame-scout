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
    return cache_folder_paths(Path(base) / CACHE_DIR)


def cache_folder_paths(cache):
    """The cache variables and their folders under the cache folder cache itself (I25).

    The evaluation tool's --cache-dir names the cache folder, not the project folder.
    """
    cache = Path(cache)
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


def open_clip_cache_dir(model, environ, base):
    """The cache_dir the engine passes open_clip for the SearchModel model, or None (E39).

    open_clip fetches weights that have no Hugging Face Hub repository from their URL into
    ~/.cache/clip unless it gets a cache_dir, whatever TORCH_HOME or XDG_CACHE_HOME say. Such
    a model therefore gets the folder clip in XDG_CACHE_HOME of environ (base/.cache if
    unset). A model with weights_repo gets None: open_clip would hand cache_dir on to
    huggingface_hub, so its weights would leave the Hub cache (HF_HOME) and be downloaded
    again.
    """
    if model.weights_repo:
        return None
    return str(Path(environ.get('XDG_CACHE_HOME') or cache_paths(base)['XDG_CACHE_HOME']) / 'clip')


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
    found, cached = find_yolo_weights(name, base, cwd, environ)
    if found is None or found == cached:
        return str(cached)
    legacy = Path(base) / name
    if name == DEFAULT_YOLO_MODEL and found == legacy:
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
    return name  # the file in the working folder


def find_yolo_weights(name, base, cwd, environ):
    """Return (found, cached) for the bare weights file name, without moving or downloading anything.

    found is the file the detector loads, looked up as yolo_weights does: in the folder of
    YOLO_CONFIG_DIR in environ (base/.cache/ultralytics if unset), the default file an older
    version downloaded into base (yolo_weights moves it), a file in the working folder cwd;
    None if there is none, so it is downloaded on first use. cached is the path in that
    cache folder, where a download goes. The free disk space check uses it too (F3 review).
    """
    folder = environ.get('YOLO_CONFIG_DIR') or cache_paths(base)['YOLO_CONFIG_DIR']
    cached = Path(folder) / name
    if cached.is_file():
        return cached, cached
    legacy = Path(base) / name
    if name == DEFAULT_YOLO_MODEL and legacy.is_file():
        return legacy, cached
    if (Path(cwd) / name).is_file():
        return Path(cwd) / name, cached
    return None, cached
