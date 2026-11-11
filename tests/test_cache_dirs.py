"""Model and config files stay under the project's .cache folder, also for manual runs (E9, I10)."""
import ast
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path, PureWindowsPath

import pytest

from framescout_core import (DEFAULT_MODEL, DEFAULT_YOLO_MODEL, MODELS, cache_folder_paths, cache_paths,
                             default_cache_env, engine_cache_env, find_yolo_weights, open_clip_cache_dir,
                             yolo_weights)

ROOT = Path(__file__).resolve().parent.parent


def test_cache_paths_are_under_the_project_cache(tmp_path):
    paths = cache_paths(tmp_path)
    cache = tmp_path / '.cache'
    assert paths == {'TORCH_HOME': cache / 'torch', 'HF_HOME': cache / 'huggingface',
                     'YOLO_CONFIG_DIR': cache / 'ultralytics', 'XDG_CACHE_HOME': cache}


def test_cache_folder_paths_take_the_cache_folder_itself(tmp_path):
    # I25: the evaluation tool's --cache-dir names the cache folder, not the project folder
    assert cache_folder_paths(tmp_path / 'my-cache') == {
        'TORCH_HOME': tmp_path / 'my-cache' / 'torch', 'HF_HOME': tmp_path / 'my-cache' / 'huggingface',
        'YOLO_CONFIG_DIR': tmp_path / 'my-cache' / 'ultralytics', 'XDG_CACHE_HOME': tmp_path / 'my-cache'}
    assert cache_folder_paths(tmp_path / '.cache') == cache_paths(tmp_path)


def test_default_cache_env_sets_unset_variables(tmp_path):
    environ = {'PATH': 'x'}
    added = default_cache_env(environ, tmp_path)
    assert environ == {'PATH': 'x', **{name: str(path) for name, path in cache_paths(tmp_path).items()}}
    assert sorted(added) == sorted(cache_paths(tmp_path))
    # nothing is created: the libraries create their folders when they need them
    assert not (tmp_path / '.cache').exists()


def test_default_cache_env_keeps_variables_a_user_set(tmp_path):
    environ = {'HF_HOME': r'D:\hf', 'TORCH_HOME': ''}
    added = default_cache_env(environ, tmp_path)
    assert environ['HF_HOME'] == r'D:\hf'
    # an empty value is not a folder: it counts as unset
    assert environ['TORCH_HOME'] == str(tmp_path / '.cache' / 'torch')
    assert 'HF_HOME' not in added and 'TORCH_HOME' in added


def test_importing_framescout_core_imports_no_third_party_module():
    # review: the engine calls default_cache_env after importing framescout_core, which is safe
    # only while framescout_core loads nothing that reads the cache variables on import
    script = ('import sys\nbefore = set(sys.modules)\nimport framescout_core\n'
              'new = {m.split(".")[0] for m in set(sys.modules) - before}\n'
              'print(sorted(new - set(sys.stdlib_module_names) - {"framescout_core"}))')
    result = subprocess.run([sys.executable, '-c', script], cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == '[]'


def test_yolo_weights_default_goes_to_the_cache(tmp_path):
    base, cwd = tmp_path / 'project', tmp_path / 'elsewhere'
    base.mkdir(), cwd.mkdir()
    # not downloaded yet: Ultralytics downloads to the path it is given, not to the working folder
    assert yolo_weights(DEFAULT_YOLO_MODEL, base, cwd, {}) == str(base / '.cache' / 'ultralytics' / DEFAULT_YOLO_MODEL)
    assert not (base / '.cache').exists()


def test_yolo_weights_follow_a_yolo_config_dir_the_user_set(tmp_path):
    # review: like default_cache_env, a folder the user (or framescout_eval) set is kept
    base, own = tmp_path / 'project', tmp_path / 'own'
    base.mkdir()
    environ = {'YOLO_CONFIG_DIR': str(own)}
    assert yolo_weights(DEFAULT_YOLO_MODEL, base, base, environ) == str(own / DEFAULT_YOLO_MODEL)
    legacy = base / DEFAULT_YOLO_MODEL
    legacy.write_bytes(b'weights')
    assert yolo_weights(DEFAULT_YOLO_MODEL, base, base, environ) == str(own / DEFAULT_YOLO_MODEL)
    assert (own / DEFAULT_YOLO_MODEL).read_bytes() == b'weights' and not legacy.exists()


def test_yolo_weights_uses_the_cached_file(tmp_path):
    cached = tmp_path / '.cache' / 'ultralytics' / DEFAULT_YOLO_MODEL
    cached.parent.mkdir(parents=True)
    cached.write_bytes(b'w')
    (tmp_path / DEFAULT_YOLO_MODEL).write_bytes(b'old')  # e.g. left by an older version
    assert yolo_weights(DEFAULT_YOLO_MODEL, tmp_path, tmp_path, {}) == str(cached)
    # review: a second copy is not deleted (it may not be ours to delete); the uninstall removes it
    assert (tmp_path / DEFAULT_YOLO_MODEL).read_bytes() == b'old'


def test_yolo_weights_moves_the_old_download_from_the_project_folder(tmp_path):
    legacy = tmp_path / DEFAULT_YOLO_MODEL
    legacy.write_bytes(b'weights')
    cached = tmp_path / '.cache' / 'ultralytics' / DEFAULT_YOLO_MODEL
    # no new download, and the project folder is clean again; also when started in it
    for cwd in (tmp_path / 'other', tmp_path):
        assert yolo_weights(DEFAULT_YOLO_MODEL, tmp_path, cwd, {}) == str(cached)
        assert cached.read_bytes() == b'weights' and not legacy.exists()
        cached.replace(legacy)


def test_yolo_weights_uses_the_old_download_if_it_cannot_be_moved(tmp_path):
    legacy = tmp_path / DEFAULT_YOLO_MODEL
    legacy.write_bytes(b'weights')
    lines = []

    def refuse(source, target):
        raise PermissionError('in use')

    assert yolo_weights(DEFAULT_YOLO_MODEL, tmp_path, tmp_path, {}, lines.append, replace=refuse) == str(legacy)
    assert legacy.exists()
    # review: not silently
    assert len(lines) == 1 and str(legacy) in lines[0] and 'in use' in lines[0]


def test_yolo_weights_moved_by_another_search_meanwhile(tmp_path):
    legacy = tmp_path / DEFAULT_YOLO_MODEL
    legacy.write_bytes(b'weights')
    cached = tmp_path / '.cache' / 'ultralytics' / DEFAULT_YOLO_MODEL
    lines = []

    def other_search_was_faster(source, target):
        Path(source).replace(target)
        raise FileNotFoundError(source)

    assert yolo_weights(DEFAULT_YOLO_MODEL, tmp_path, tmp_path, {}, lines.append,
                        replace=other_search_was_faster) == str(cached)
    assert lines == []


def test_yolo_weights_leaves_other_files_of_the_project_folder(tmp_path):
    # only the file FrameScout itself downloaded is moved; a user's own weights stay put
    own = tmp_path / 'custom.pt'
    own.write_bytes(b'mine')
    assert yolo_weights('custom.pt', tmp_path, tmp_path, {}) == 'custom.pt'
    assert own.exists()


def test_yolo_weights_in_the_working_folder_are_used_as_before(tmp_path):
    base, cwd = tmp_path / 'project', tmp_path / 'elsewhere'
    base.mkdir(), cwd.mkdir()
    (cwd / 'yolo11s.pt').write_bytes(b'w')
    assert yolo_weights('yolo11s.pt', base, cwd, {}) == 'yolo11s.pt'
    # another official name that is not there yet is downloaded into the cache too
    assert yolo_weights('yolo11m.pt', base, cwd, {}) == str(base / '.cache' / 'ultralytics' / 'yolo11m.pt')


def test_yolo_weights_in_the_working_folder_win_over_a_cached_copy(tmp_path):
    # E41: a copy the user put into the working folder is deliberate, so it wins over the cache
    base, cwd, own = tmp_path / 'project', tmp_path / 'elsewhere', tmp_path / 'own'
    base.mkdir(), cwd.mkdir()
    for name in (DEFAULT_YOLO_MODEL, 'yolo11s.pt'):
        for folder in (base / '.cache' / 'ultralytics', own):
            folder.mkdir(parents=True, exist_ok=True)
            (folder / name).write_bytes(b'cached')
        (cwd / name).write_bytes(b'mine')
        for environ in ({}, {'YOLO_CONFIG_DIR': str(own)}):
            cached = Path(environ.get('YOLO_CONFIG_DIR') or base / '.cache' / 'ultralytics') / name
            assert find_yolo_weights(name, base, cwd, environ) == (cwd / name, cached)
            assert yolo_weights(name, base, cwd, environ) == name
            # nothing moved or replaced
            assert (cwd / name).read_bytes() == b'mine' and cached.read_bytes() == b'cached'


def test_the_default_weights_in_the_project_folder_stay_an_older_download(tmp_path):
    # E41: started in the project folder, the default file there is what an older version
    # downloaded (E9), not a copy of the user: a cached copy still wins and it is not used
    cached = tmp_path / '.cache' / 'ultralytics' / DEFAULT_YOLO_MODEL
    cached.parent.mkdir(parents=True)
    cached.write_bytes(b'w')
    (tmp_path / DEFAULT_YOLO_MODEL).write_bytes(b'old')
    assert find_yolo_weights(DEFAULT_YOLO_MODEL, tmp_path, tmp_path, {}) == (cached, cached)
    # another name in the project folder is the user's own copy, used as given
    (tmp_path / 'yolo11s.pt').write_bytes(b'mine')
    cached.with_name('yolo11s.pt').write_bytes(b'w')
    assert yolo_weights('yolo11s.pt', tmp_path, tmp_path, {}) == 'yolo11s.pt'


def test_the_project_folder_is_told_by_its_path_not_by_the_file(tmp_path, monkeypatch):
    # review: samefile stats a file another search may be moving into the cache meanwhile, and
    # on volumes without a unique file index (exFAT, network shares) two files compare equal
    base, cwd = tmp_path / 'project', tmp_path / 'elsewhere'
    (base / 'sub').mkdir(parents=True), cwd.mkdir()
    (base / DEFAULT_YOLO_MODEL).write_bytes(b'old')
    (cwd / DEFAULT_YOLO_MODEL).write_bytes(b'mine')
    cached = base / '.cache' / 'ultralytics' / DEFAULT_YOLO_MODEL

    def no_stat(self, other):
        raise AssertionError('samefile is not needed')

    monkeypatch.setattr(Path, 'samefile', no_stat)
    assert find_yolo_weights(DEFAULT_YOLO_MODEL, base, cwd, {}) == (cwd / DEFAULT_YOLO_MODEL, cached)
    # another spelling of the project folder is still the project folder
    assert find_yolo_weights(DEFAULT_YOLO_MODEL, base, base / 'sub' / '..', {}) == (base / DEFAULT_YOLO_MODEL, cached)


def test_engine_cache_env_keeps_the_variables_a_user_set(tmp_path):
    # A36: the app gives the engine the cache variables as a manual run gets them
    environ = {'PATH': 'x', 'HF_HOME': r'D:\hf', 'TORCH_HOME': ''}
    env = engine_cache_env(environ, tmp_path)
    paths = cache_paths(tmp_path)
    assert env == {'PATH': 'x', 'HF_HOME': r'D:\hf', 'TORCH_HOME': str(paths['TORCH_HOME']),
                   'YOLO_CONFIG_DIR': str(paths['YOLO_CONFIG_DIR']), 'XDG_CACHE_HOME': str(paths['XDG_CACHE_HOME'])}
    # a copy: the caller's environment is not changed
    assert environ == {'PATH': 'x', 'HF_HOME': r'D:\hf', 'TORCH_HOME': ''}
    assert not (tmp_path / '.cache').exists()


def test_find_yolo_weights_looks_where_yolo_weights_does_without_moving(tmp_path):
    # the free disk space check asks whether the detector needs a download (F3 review)
    base, cwd = tmp_path / 'project', tmp_path / 'elsewhere'
    base.mkdir(), cwd.mkdir()
    cached = base / '.cache' / 'ultralytics' / DEFAULT_YOLO_MODEL
    assert find_yolo_weights(DEFAULT_YOLO_MODEL, base, cwd, {}) == (None, cached)
    own = tmp_path / 'own'
    assert find_yolo_weights(DEFAULT_YOLO_MODEL, base, cwd, {'YOLO_CONFIG_DIR': str(own)}) == (
        None, own / DEFAULT_YOLO_MODEL)
    (cwd / 'yolo11s.pt').write_bytes(b'w')
    assert find_yolo_weights('yolo11s.pt', base, cwd, {}) == (cwd / 'yolo11s.pt', cached.with_name('yolo11s.pt'))
    legacy = base / DEFAULT_YOLO_MODEL
    legacy.write_bytes(b'weights')
    assert find_yolo_weights(DEFAULT_YOLO_MODEL, base, cwd, {}) == (legacy, cached)
    assert legacy.exists() and not cached.parent.exists()  # nothing moved or created
    cached.parent.mkdir(parents=True)
    cached.write_bytes(b'w')
    assert find_yolo_weights(DEFAULT_YOLO_MODEL, base, cwd, {}) == (cached, cached)


def test_yolo_weights_paths_and_urls_are_used_as_given(tmp_path):
    names = [str(tmp_path / 'w.pt'), 'models/w.pt', 'https://example.org/w.pt']
    if os.name == 'nt':
        # a backslash separates folders on Windows only; elsewhere it is part of a bare file
        # name, as Path and Ultralytics see it there (E40)
        names.append(r'models\w.pt')
    for name in names:
        assert yolo_weights(name, tmp_path, tmp_path, {}) == name


def test_open_clip_downloads_from_a_url_into_the_project_cache(tmp_path):
    # E39: open_clip fetches weights without a Hub repository from their URL into
    # ~/.cache/clip unless it gets cache_dir; a Hub model gets none, or its weights would
    # leave the Hugging Face cache (HF_HOME) and be downloaded again
    url_model = replace(MODELS[DEFAULT_MODEL], weights_repo='')
    assert open_clip_cache_dir(url_model, {'XDG_CACHE_HOME': str(tmp_path / 'own')}, tmp_path) == str(
        tmp_path / 'own' / 'clip')
    assert open_clip_cache_dir(url_model, {}, tmp_path) == str(tmp_path / '.cache' / 'clip')
    for model in MODELS.values():
        assert open_clip_cache_dir(model, {'XDG_CACHE_HOME': str(tmp_path)}, tmp_path) is None


BAT_FILES = ('Start-FrameScout.bat', 'Install-FrameScout.bat')


def cache_lines(name):
    """The lines of the .bat file name that set one of the cache variables of cache_paths."""
    lines = [line.strip() for line in (ROOT / name).read_text(encoding='utf-8').splitlines()]
    return [line for line in lines if any(f'"{variable}=' in line for variable in cache_paths(ROOT))]


def test_the_bat_files_set_only_the_cache_variables_a_user_did_not_set():
    # A36: as for a manual engine run (default_cache_env), a variable the user set wins
    expected = [f'if not defined {variable} set "{variable}=%CD%\\{PureWindowsPath(path.relative_to(ROOT))}"'
                for variable, path in cache_paths(ROOT).items()]
    for name in BAT_FILES:
        assert sorted(cache_lines(name)) == sorted(expected), name


@pytest.mark.skipif(sys.platform != 'win32', reason='runs a .bat file')
def test_the_cache_lines_of_the_bat_files_keep_a_variable_the_user_set(tmp_path):
    # the lines themselves, run by cmd.exe in a folder with a space, "!" and ")" in its name
    folder = tmp_path / 'Fo!to (old) & co'
    folder.mkdir()
    names = list(cache_paths(ROOT))
    script = folder / 'cache.bat'
    script.write_text('\r\n'.join(['@echo off', 'setlocal', 'cd /d "%~dp0"', *cache_lines('Start-FrameScout.bat'),
                                   # quoted: the "&" of the folder path would end the echo
                                   *[f'echo "{name}=%{name}%"' for name in names]]) + '\r\n', encoding='utf-8')
    env = {k: v for k, v in os.environ.items() if k.upper() not in names}
    env['HF_HOME'] = str(tmp_path / 'own-hf')
    result = subprocess.run(['cmd.exe', '/d', '/c', '.\\cache.bat'], cwd=folder, env=env, capture_output=True,
                            text=True, errors='replace', timeout=60)
    assert result.returncode == 0, result.stderr
    expected = {name: str(path) for name, path in cache_paths(folder).items()}
    expected['HF_HOME'] = env['HF_HOME']
    assert result.stdout.splitlines() == [f'"{name}={expected[name]}"' for name in names]


def test_the_engine_passes_the_url_cache_folder_to_open_clip():
    tree = ast.parse((ROOT / 'framescout_engine.py').read_text(encoding='utf-8'))
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and getattr(node.func, 'attr', None) == 'create_model_and_transforms']
    assert len(calls) == 1 and 'cache_dir' in {keyword.arg for keyword in calls[0].keywords}
    assert any(isinstance(node, ast.Call) and getattr(node.func, 'id', None) == 'open_clip_cache_dir'
               for node in ast.walk(tree))
