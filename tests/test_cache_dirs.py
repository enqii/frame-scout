"""Model and config files stay under the project's .cache folder, also for manual runs (E9, I10)."""
import subprocess
import sys
from pathlib import Path

from framescout_core import DEFAULT_YOLO_MODEL, cache_paths, default_cache_env, yolo_weights

ROOT = Path(__file__).resolve().parent.parent


def test_cache_paths_are_under_the_project_cache(tmp_path):
    paths = cache_paths(tmp_path)
    cache = tmp_path / '.cache'
    assert paths == {'TORCH_HOME': cache / 'torch', 'HF_HOME': cache / 'huggingface',
                     'YOLO_CONFIG_DIR': cache / 'ultralytics', 'XDG_CACHE_HOME': cache}


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


def test_yolo_weights_paths_and_urls_are_used_as_given(tmp_path):
    for name in (str(tmp_path / 'w.pt'), r'models\w.pt', 'models/w.pt', 'https://example.org/w.pt'):
        assert yolo_weights(name, tmp_path, tmp_path, {}) == name
