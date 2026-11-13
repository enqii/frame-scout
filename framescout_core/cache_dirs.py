"""Model downloads and library config files under the project's .cache folder (E9, I10).

The .bat files, the app (engine_cache_env) and a manual engine run (default_cache_env in
its main()) set the cache variables a user did not set, so nothing lands in the user
profile and the uninstall stays clean; a variable the user set wins (A36, E42). The
evaluation tool sets all of them to its --cache-dir.
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


# the variables torch and huggingface_hub derive from XDG_CACHE_HOME when they are unset
XDG_DERIVED = ('TORCH_HOME', 'HF_HOME')


def default_cache_env(environ, base):
    """Set the cache variables that are unset or empty in environ to base/.cache (I10).

    A value the user set is kept. With an XDG_CACHE_HOME of the user, TORCH_HOME and HF_HOME
    stay unset, so torch and huggingface_hub use its torch and huggingface folders as they do
    without FrameScout (review; an empty one is removed, as cmd.exe has no empty variables).
    Must run before torch, huggingface_hub and Ultralytics are imported (they read some of
    the variables on import). Creates no folder; returns the names it set, each to its
    folder in cache_paths(base).
    """
    user_cache = environ.get('XDG_CACHE_HOME')
    added = []
    for name, path in cache_paths(base).items():
        if environ.get(name):
            continue
        if user_cache and name in XDG_DERIVED:
            environ.pop(name, None)
        else:
            environ[name] = str(path)
            added.append(name)
    return added


def engine_cache_env(environ, base):
    """A copy of environ with the cache variables default_cache_env sets for base (A36).

    The environment the app gives the engine it starts: a variable the user set is kept,
    as for a manual engine run. environ itself is not changed.
    """
    env = dict(environ)
    default_cache_env(env, base)
    return env


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
    folder, which put yolo11n.pt into the project folder. A file of that name in the working
    folder cwd wins, as a copy the user put there deliberately (E41); otherwise the bare name
    is looked up in the folder of YOLO_CONFIG_DIR in environ (base/.cache/ultralytics if
    unset; a value the user set is kept, review). The default file an older version
    downloaded into base is no such copy, also when cwd is base: it is moved into that folder
    once, unless a copy is there already (kept and used where it is if it cannot be moved;
    log, if given, gets a line about it). Any other path or URL is used as given.
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


def detector_weights_line(weights, cwd):
    """The run log line that names the weights file the detector loads (E60).

    weights is what yolo_weights returned: the cache signature records --yolo-model only as
    given, so a copy of the same name in the working folder (E41) or a relative path from
    another working folder is told apart only by this line. A relative path is shown as the
    absolute one in cwd; a URL as given; a file that is not there yet gets a note that it is
    downloaded on first use.
    """
    if '://' in weights:
        return f'Person detector weights: {weights}'
    path = Path(os.path.abspath(Path(cwd) / weights))
    note = '' if path.is_file() else ' (not there yet, downloaded on first use)'
    return f'Person detector weights: {path}{note}'


def find_yolo_weights(name, base, cwd, environ):
    """Return (found, cached) for the bare weights file name, without moving or downloading anything.

    found is the file the detector loads, looked up as yolo_weights does: a file in the
    working folder cwd (E41; not the default file of an older version's download in base,
    also when cwd is base), the one in the folder of YOLO_CONFIG_DIR in environ
    (base/.cache/ultralytics if unset), that older download (yolo_weights moves it); None if
    there is none, so it is downloaded on first use. cached is the path in that cache
    folder, where a download goes. The free disk space check uses it too (F3 review).
    """
    folder = environ.get('YOLO_CONFIG_DIR') or cache_paths(base)['YOLO_CONFIG_DIR']
    cached = Path(folder) / name
    legacy = Path(base) / name if name == DEFAULT_YOLO_MODEL else None
    own = Path(cwd) / name
    # the project folder is told by its path, not by the file's identity (samefile): that
    # stats a file another search may be moving into the cache, and some Windows volumes
    # (exFAT, network shares) report no unique file index (review)
    if own.is_file() and not (legacy is not None and _same_folder(cwd, base)):
        return own, cached
    if cached.is_file():
        return cached, cached
    if legacy is not None and legacy.is_file():
        return legacy, cached
    return None, cached


def _same_folder(a, b):
    """Whether the folders a and b are the same folder, by their resolved paths."""
    try:
        return Path(a).resolve() == Path(b).resolve()
    except (OSError, RuntimeError):  # e.g. a symbolic link loop
        return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))
