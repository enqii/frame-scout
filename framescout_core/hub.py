"""Loading the search models without a Hugging Face Hub request once they are cached (E16, E31, E33).

open_clip loads the weights (and SigLIP its tokenizer) through huggingface_hub, which asks
the Hub for the file on every run even when it is in the cache. The engine therefore
imports open_clip in offline mode when every file the model needs is cached, and goes
online again only if loading fails (an incomplete cache). huggingface_hub reads these
variables when it is imported, so they are set before open_clip is imported.
"""
import os
from pathlib import Path

# Set unless the user set them: no "cache-system uses symlinks" warning in run.log on Windows
# without Developer Mode (E33; the files are stored as copies either way) and no telemetry.
HUB_QUIET_ENV = {'HF_HUB_DISABLE_SYMLINKS_WARNING': '1', 'HF_HUB_DISABLE_TELEMETRY': '1'}
# open_clip's weights file of a Hub repo, the safetensors one first (open_clip.pretrained)
WEIGHTS_FILES = ('open_clip_model.safetensors', 'open_clip_pytorch_model.bin')
# what a Hugging Face tokenizer needs at least: its config and its vocabulary
TOKENIZER_FILES = (('tokenizer_config.json',), ('tokenizer.json', 'spiece.model'))
# huggingface_hub turns offline mode on by either variable
OFFLINE_VARIABLES = ('HF_HUB_OFFLINE', 'TRANSFORMERS_OFFLINE')


def hub_cache_dir(environ, home=None):
    """Return the folder huggingface_hub keeps its cache in, as huggingface_hub.constants finds it."""
    for name in ('HF_HUB_CACHE', 'HUGGINGFACE_HUB_CACHE'):
        if name in environ:
            return Path(os.path.expandvars(os.path.expanduser(environ[name])))
    home = Path(home) if home is not None else Path.home()
    hf_home = environ.get('HF_HOME', os.path.join(environ.get('XDG_CACHE_HOME', home / '.cache'), 'huggingface'))
    return Path(os.path.expandvars(os.path.expanduser(hf_home))) / 'hub'


def hub_file_cached(cache, repo, filenames):
    """Return whether one of filenames of the model repo is in the cache folder cache.

    Offline, huggingface_hub takes the file from the snapshot that refs/main names, so only
    that snapshot counts.
    """
    folder = Path(cache) / ('models--' + repo.replace('/', '--'))
    try:
        revision = (folder / 'refs' / 'main').read_text(encoding='utf-8').strip()
    except (OSError, UnicodeDecodeError):
        return False
    snapshots = folder / 'snapshots'
    # one folder name inside snapshots: no separator, and not '.' or '..'
    if revision in ('', '.', '..') or Path(revision).name != revision:
        return False
    return any((snapshots / revision / name).is_file() for name in filenames)


def model_cached(model, cache):
    """Return whether every Hub file the SearchModel model needs is in the cache folder cache."""
    if not hub_file_cached(cache, model.weights_repo, WEIGHTS_FILES):
        return False
    return not model.tokenizer_repo or all(hub_file_cached(cache, model.tokenizer_repo, names)
                                           for names in TOKENIZER_FILES)


def _set_hub_constants(modules, values):
    """Set the huggingface_hub constants values (name: bool) if huggingface_hub is imported already.

    huggingface_hub reads its constants on every request (constants.is_offline_mode(),
    constants.HF_HUB_DISABLE_SYMLINKS_WARNING); older transformers versions keep their own
    copy of the offline flag (_is_offline_mode), which is switched as well when it exists.
    """
    constants = modules.get('huggingface_hub.constants')
    if constants is not None:
        for name, value in values.items():
            setattr(constants, name, value)
    transformers_hub = modules.get('transformers.utils.hub')
    if 'HF_HUB_OFFLINE' in values and transformers_hub is not None and hasattr(transformers_hub, '_is_offline_mode'):
        transformers_hub._is_offline_mode = values['HF_HUB_OFFLINE']


def import_open_clip(environ, import_module, model, cache=None, modules=None):
    """Import open_clip, offline when the model is cached; return (open_clip, offline).

    environ is os.environ, import_module is importlib.import_module and model the SearchModel
    to load; cache is the Hub cache folder (default: the one of environ). Offline mode is
    turned on only if the user set neither HF_HUB_OFFLINE nor TRANSFORMERS_OFFLINE; then
    offline is True and a failed load may go online again (load_with_hub_fallback).
    modules is sys.modules: if something imported huggingface_hub before, it has read the
    variables already, so its constants are set as well.
    """
    values = {}
    for name, value in HUB_QUIET_ENV.items():
        if name not in environ:
            environ[name] = value
            values[name] = True
    offline = (not any(name in environ for name in OFFLINE_VARIABLES)
               and model_cached(model, hub_cache_dir(environ) if cache is None else cache))
    if offline:
        environ['HF_HUB_OFFLINE'] = '1'
        values['HF_HUB_OFFLINE'] = True
    if modules is not None:
        _set_hub_constants(modules, values)
    return import_module('open_clip'), offline


def hub_go_online(environ, modules):
    """Turn offline mode off again in environ and in the imported libraries (modules is sys.modules)."""
    environ['HF_HUB_OFFLINE'] = '0'
    _set_hub_constants(modules, {'HF_HUB_OFFLINE': False})


def hub_file_error(exc):
    """Return whether the exception exc comes from a file missing in the cache (an OSError in its chain).

    huggingface_hub raises LocalEntryNotFoundError (a FileNotFoundError) or OfflineModeIsEnabled
    (a ConnectionError) offline, transformers an OSError; open_clip wraps the weights error in a
    RuntimeError raised while handling it, so the whole __cause__/__context__ chain counts.
    """
    seen = set()
    while exc is not None and id(exc) not in seen:
        if isinstance(exc, OSError):
            return True
        seen.add(id(exc))
        exc = exc.__cause__ or exc.__context__
    return False


def load_with_hub_fallback(load, offline, go_online, out):
    """Return load(); if a cache file is missing in offline mode, call go_online(), say so with out(text) and load again.

    Without offline mode, and for any other error (e.g. out of memory, a broken weights file),
    the error is raised as it is.
    """
    if not offline:
        return load()
    try:
        return load()
    except Exception as exc:
        if not hub_file_error(exc):
            raise
        out('The model files in the cache are incomplete or could not be loaded offline '
            f'({type(exc).__name__}: {exc}); they are downloaded again (needs internet access).')
        go_online()
        return load()  # an error here keeps the offline one as its context in the traceback
