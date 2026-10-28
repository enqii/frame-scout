"""Hugging Face Hub access of the search models: offline once cached, no symlink warning (E16, E33)."""
import types
from pathlib import Path

import pytest

from framescout_core import (HUB_QUIET_ENV, MODELS, hub_cache_dir, hub_file_cached, hub_go_online,
                             import_open_clip, load_with_hub_fallback, model_cached)

DEFAULT = MODELS['vit-b-32-openai']
SIGLIP = MODELS['vit-b-16-siglip']


def cache_file(cache, repo, filename, revision='abc123', ref=True):
    """Lay out one file of repo as huggingface_hub stores it in the cache folder cache."""
    folder = Path(cache) / ('models--' + repo.replace('/', '--'))
    if ref:
        (folder / 'refs').mkdir(parents=True, exist_ok=True)
        (folder / 'refs' / 'main').write_text(revision, encoding='utf-8')
    path = folder / 'snapshots' / revision / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'w')
    return path


# --- where the cache is ---

def test_the_cache_folder_follows_the_variables_of_huggingface_hub(tmp_path):
    home = tmp_path / 'home'
    assert hub_cache_dir({}, home) == home / '.cache' / 'huggingface' / 'hub'
    assert hub_cache_dir({'XDG_CACHE_HOME': str(tmp_path / 'x')}, home) == tmp_path / 'x' / 'huggingface' / 'hub'
    environ = {'XDG_CACHE_HOME': str(tmp_path / 'x'), 'HF_HOME': str(tmp_path / 'hf')}
    assert hub_cache_dir(environ, home) == tmp_path / 'hf' / 'hub'
    environ['HUGGINGFACE_HUB_CACHE'] = str(tmp_path / 'legacy')
    assert hub_cache_dir(environ, home) == tmp_path / 'legacy'
    environ['HF_HUB_CACHE'] = str(tmp_path / 'new')
    assert hub_cache_dir(environ, home) == tmp_path / 'new'


def test_an_empty_variable_counts_as_set_like_in_huggingface_hub(tmp_path):
    # os.getenv("HF_HOME", default) returns "" for an empty variable; never guess another folder
    assert hub_cache_dir({'HF_HOME': ''}, tmp_path) == Path('') / 'hub'


# --- which files are cached ---

def test_a_file_counts_as_cached_only_in_the_snapshot_of_main(tmp_path):
    repo = 'timm/vit_base_patch32_clip_224.openai'
    assert not hub_file_cached(tmp_path, repo, ('open_clip_model.safetensors',))
    cache_file(tmp_path, repo, 'open_clip_model.safetensors', revision='old')
    (tmp_path / ('models--' + repo.replace('/', '--')) / 'refs' / 'main').write_text('new\n', encoding='utf-8')
    assert not hub_file_cached(tmp_path, repo, ('open_clip_model.safetensors',))
    cache_file(tmp_path, repo, 'open_clip_model.safetensors', revision='new')
    assert hub_file_cached(tmp_path, repo, ('open_clip_model.safetensors',))


def test_a_file_without_a_ref_or_a_folder_in_its_place_is_not_cached(tmp_path):
    repo = 'org/model'
    cache_file(tmp_path, repo, 'open_clip_model.safetensors', ref=False)
    assert not hub_file_cached(tmp_path, repo, ('open_clip_model.safetensors',))
    folder = tmp_path / 'models--org--model'
    (folder / 'refs').mkdir()
    (folder / 'refs' / 'main').write_text('abc123', encoding='utf-8')
    (folder / 'snapshots' / 'abc123' / 'open_clip_pytorch_model.bin').mkdir()
    assert not hub_file_cached(tmp_path, repo, ('open_clip_pytorch_model.bin',))
    assert hub_file_cached(tmp_path, repo, ('open_clip_pytorch_model.bin', 'open_clip_model.safetensors'))


def test_an_unreadable_ref_or_a_path_outside_the_snapshots_is_not_cached(tmp_path):
    folder = tmp_path / 'models--org--model'
    (folder / 'refs' / 'main').mkdir(parents=True)  # a folder, not a file
    assert not hub_file_cached(tmp_path, 'org/model', ('w',))
    (folder / 'refs' / 'main').rmdir()
    (folder / 'refs' / 'main').write_text('../../x', encoding='utf-8')
    (tmp_path / 'x').mkdir()
    (tmp_path / 'x' / 'w').write_bytes(b'w')
    assert not hub_file_cached(tmp_path, 'org/model', ('w',))


def test_the_default_model_is_cached_with_its_safetensors_or_bin_weights(tmp_path):
    assert not model_cached(DEFAULT, tmp_path)
    cache_file(tmp_path, DEFAULT.weights_repo, 'open_clip_pytorch_model.bin')
    assert model_cached(DEFAULT, tmp_path)


def test_a_hugging_face_tokenizer_must_be_cached_too(tmp_path):
    cache_file(tmp_path, SIGLIP.weights_repo, 'open_clip_model.safetensors')
    assert not model_cached(SIGLIP, tmp_path)
    cache_file(tmp_path, SIGLIP.tokenizer_repo, 'tokenizer_config.json')
    assert not model_cached(SIGLIP, tmp_path)
    cache_file(tmp_path, SIGLIP.tokenizer_repo, 'spiece.model')
    assert model_cached(SIGLIP, tmp_path)


# --- importing open_clip ---

class Importer:
    def __init__(self):
        self.seen = []

    def __call__(self, name, environ):
        self.seen.append((name, dict(environ)))
        return types.SimpleNamespace(name=name)


def import_with(environ, cache, model=DEFAULT):
    importer = Importer()
    module, offline = import_open_clip(environ, lambda name: importer(name, environ), model, cache=cache)
    assert module.name == 'open_clip' and len(importer.seen) == 1
    return offline, importer.seen[0][1]


def test_open_clip_is_imported_offline_once_the_model_is_cached(tmp_path):
    cache_file(tmp_path, DEFAULT.weights_repo, 'open_clip_model.safetensors')
    environ = {}
    offline, seen = import_with(environ, tmp_path)
    # huggingface_hub reads the variables when it is imported, so they are set before
    assert offline and seen['HF_HUB_OFFLINE'] == '1'
    assert all(seen[name] == value for name, value in HUB_QUIET_ENV.items())


def test_the_first_run_imports_open_clip_online_without_the_warnings(tmp_path):
    environ = {}
    offline, seen = import_with(environ, tmp_path)
    assert not offline and 'HF_HUB_OFFLINE' not in seen
    assert seen['HF_HUB_DISABLE_SYMLINKS_WARNING'] == '1' and seen['HF_HUB_DISABLE_TELEMETRY'] == '1'


@pytest.mark.parametrize('name', ['HF_HUB_OFFLINE', 'TRANSFORMERS_OFFLINE'])
@pytest.mark.parametrize('value', ['0', '1'])
def test_an_offline_mode_the_user_set_is_kept(tmp_path, name, value):
    cache_file(tmp_path, DEFAULT.weights_repo, 'open_clip_model.safetensors')
    offline, seen = import_with({name: value}, tmp_path)
    assert not offline and seen.get('HF_HUB_OFFLINE') == (value if name == 'HF_HUB_OFFLINE' else None)


def test_quiet_variables_the_user_set_are_kept(tmp_path):
    offline, seen = import_with({'HF_HUB_DISABLE_TELEMETRY': '0'}, tmp_path)
    assert seen['HF_HUB_DISABLE_TELEMETRY'] == '0' and seen['HF_HUB_DISABLE_SYMLINKS_WARNING'] == '1'


def test_the_cache_folder_defaults_to_the_one_of_the_environment(tmp_path):
    cache_file(tmp_path / 'hub', DEFAULT.weights_repo, 'open_clip_model.safetensors')
    importer = Importer()
    environ = {'HF_HOME': str(tmp_path)}
    _, offline = import_open_clip(environ, lambda name: importer(name, environ), DEFAULT)
    assert offline


# --- falling back to a download ---

def test_a_failed_offline_load_goes_online_and_loads_again():
    calls, notes, online = [], [], []

    def load():
        calls.append(len(online))
        if not online:
            raise FileNotFoundError('not in the cache')
        return 'model'

    assert load_with_hub_fallback(load, True, lambda: online.append(1), notes.append) == 'model'
    assert calls == [0, 1] and online == [1]
    assert len(notes) == 1 and 'download' in notes[0] and 'not in the cache' in notes[0]


def test_an_online_load_error_is_not_retried():
    def load():
        raise FileNotFoundError('no network')

    with pytest.raises(FileNotFoundError):
        load_with_hub_fallback(load, False, lambda: pytest.fail('went online'), lambda text: None)


def test_an_offline_load_without_errors_stays_offline():
    assert load_with_hub_fallback(lambda: 'model', True, lambda: pytest.fail('went online'),
                                  lambda text: pytest.fail(text)) == 'model'


def test_going_online_switches_the_imported_libraries_back():
    hub = types.SimpleNamespace(HF_HUB_OFFLINE=True)
    transformers_hub = types.SimpleNamespace(_is_offline_mode=True)
    environ = {'HF_HUB_OFFLINE': '1'}
    hub_go_online(environ, {'huggingface_hub.constants': hub, 'transformers.utils.hub': transformers_hub})
    assert environ['HF_HUB_OFFLINE'] == '0'
    assert hub.HF_HUB_OFFLINE is False and transformers_hub._is_offline_mode is False


def test_going_online_works_without_the_libraries_or_their_flags():
    environ = {}
    hub_go_online(environ, {'transformers.utils.hub': types.SimpleNamespace()})
    assert environ['HF_HUB_OFFLINE'] == '0'
