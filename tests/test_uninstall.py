"""The uninstall script (P5): deletes the environment, caches and temporary files, never user data.

Every test works in pytest's tmp_path; nothing touches the real project folder.
"""
import json
import os
import re
import stat
import sys
from pathlib import Path

import pytest

import framescout_uninstall
from framescout_core import (ENVIRONMENT_PROGRAMS, RunLock, outside_leftovers, programs_in_use, protected_folders,
                             remove_items, search_running, uninstall_plan, user_data)
from framescout_core import uninstall as uninstall_module

ROOT = Path(__file__).resolve().parent.parent
windows_only = pytest.mark.skipif(sys.platform != 'win32', reason='junctions and file sharing modes are Windows')


def write(path, data=b'x'):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


@pytest.fixture
def project(tmp_path):
    """An installed FrameScout folder with an environment, caches and the user's data."""
    root = tmp_path / 'FrameScout'
    write(root / 'app.py', b'# program file')
    write(root / 'framescout_core' / '__init__.py', b'# program file')
    write(root / '.venv' / 'Scripts' / 'python.exe', b'p' * 100)
    write(root / '.venv' / 'pyvenv.cfg', b'home = C:\\Python')
    write(root / '.venv' / 'Lib' / 'site-packages' / 'torch' / 'lib.dll', b'd' * 1000)
    write(root / '.cache' / 'huggingface' / 'model.bin', b'm' * 500)
    write(root / '.tmp' / 'pip-build' / 'x.whl', b't' * 10)
    write(root / 'yolo11n.pt', b'y' * 50)
    write(root / '__pycache__' / 'app.cpython-314.pyc')
    write(root / 'framescout_core' / '__pycache__' / 'names.cpython-314.pyc')
    # the user's data
    write(root / 'photos' / 'IMG_0001.jpg', b'photo')
    write(root / 'references' / 'hero' / 'ref.jpg', b'ref')
    write(root / 'results' / 'marks.json', b'{}')
    write(root / 'results' / 'cache.sqlite3', b'c' * 20)
    write(root / 'profiles.json', b'{"profiles": []}')
    write(root / 'settings.json', b'{}')
    write(root / 'run.log', b'log')
    write(root / '.tmp' / 'eval' / 'cosplay' / 'labels.json', b'{}')
    return root


USER_FILES = ('photos/IMG_0001.jpg', 'references/hero/ref.jpg', 'results/marks.json', 'results/cache.sqlite3',
              'profiles.json', 'settings.json', 'run.log', '.tmp/eval/cosplay/labels.json', 'app.py',
              'framescout_core/__init__.py')


def assert_user_data_kept(root):
    for relative in USER_FILES:
        assert (root / relative).is_file(), relative


def plan(root):
    return uninstall_plan(root, protected_folders(root))


def names(items, root):
    return sorted(item.path.relative_to(root).as_posix() for item in items)


# --- uninstall_plan: what is deleted ---

def test_the_plan_lists_the_environment_caches_and_temporary_files(project):
    items, skipped = plan(project)
    assert names(items, project) == ['.cache', '.tmp', '.venv', '__pycache__', 'framescout_core/__pycache__',
                                     'yolo11n.pt']
    assert skipped == []
    sizes = {item.path.name: item.size for item in items}
    assert sizes['.venv'] == 100 + len(b'home = C:\\Python') + 1000
    assert sizes['.cache'] == 500
    assert sizes['.tmp'] == 10  # without .tmp/eval
    assert sizes['yolo11n.pt'] == 50


def test_the_plan_never_lists_user_data(project):
    items, _ = plan(project)
    listed = names(items, project)
    for relative in ('photos', 'references', 'results', 'profiles.json', 'settings.json', 'run.log', 'app.py',
                     'framescout_core'):
        assert relative not in listed


def test_missing_items_are_not_listed(tmp_path):
    write(tmp_path / 'app.py')
    assert plan(tmp_path) == ([], [])


def test_a_tmp_folder_with_only_the_evaluation_collections_is_not_listed(project):
    write(project / '.tmp' / 'pip-build' / 'x.whl').unlink()
    (project / '.tmp' / 'pip-build').rmdir()
    assert '.tmp' not in names(plan(project)[0], project)


def test_an_item_holding_a_photo_folder_of_the_settings_is_not_deleted(project):
    photos = project / '.cache' / 'my photos'
    write(photos / 'IMG_0002.jpg')
    (project / 'settings.json').write_text(json.dumps({'photo_folders': [str(photos)]}), encoding='utf-8')
    items, skipped = plan(project)
    assert '.cache' not in names(items, project)
    assert [path.name for path, _ in skipped] == ['.cache']
    assert str(photos) in skipped[0][1]


def test_an_item_holding_a_copy_folder_is_not_deleted(project):
    copies = project / '.tmp' / 'copies'
    (project / 'settings.json').write_text(json.dumps({'copy_folders': {'hero': str(copies)}}), encoding='utf-8')
    items, skipped = plan(project)
    assert '.tmp' not in names(items, project)
    assert [path.name for path, _ in skipped] == ['.tmp']


def test_a_photo_folder_in_the_kept_evaluation_folder_does_not_block_tmp(project):
    folder = project / '.tmp' / 'eval' / 'photos'
    (project / 'settings.json').write_text(json.dumps({'photo_folders': [str(folder)]}), encoding='utf-8')
    assert '.tmp' in names(plan(project)[0], project)


def test_a_relative_photo_folder_counts_from_the_project_folder(project):
    (project / 'settings.json').write_text(json.dumps({'photo_folders': ['.cache/photos']}), encoding='utf-8')
    assert '.cache' not in names(plan(project)[0], project)


def test_an_unreadable_settings_file_blocks_the_plan(project):
    (project / 'settings.json').write_text('{not json', encoding='utf-8')
    with pytest.raises(ValueError):
        protected_folders(project)


def test_the_default_photo_folder_is_protected_without_settings(project):
    (project / 'settings.json').unlink()
    assert protected_folders(project) == [project / 'photos']


@pytest.mark.parametrize('document', [
    {'photo_folders': ['.tmp/shoot', 5]},
    {'photo_folders': '.tmp/shoot'},
    {'photo_folder': 5},
    {'copy_folders': {'hero': 5}},
    {'copy_folders': ['.tmp/copies']},
])
def test_invalid_photo_or_copy_folders_block_the_plan(project, document):
    # the app would fall back to the default folder, so the real folders are unknown (review)
    (project / 'settings.json').write_text(json.dumps(document), encoding='utf-8')
    with pytest.raises(ValueError):
        protected_folders(project)


def test_the_settings_file_is_read_once(project, monkeypatch):
    # photo folders and copy folders come from the same version of the file (review)
    (project / 'settings.json').write_text(json.dumps({'photo_folders': ['a'], 'copy_folders': {'hero': 'b'}}),
                                           encoding='utf-8')
    reads = []
    original = uninstall_module._read_settings_file
    monkeypatch.setattr(uninstall_module, '_read_settings_file', lambda *args: reads.append(1) or original(*args))
    assert protected_folders(project) == [project / 'a', project / 'b']
    assert len(reads) == 1


@pytest.mark.parametrize('folder', ['.', 'ROOT', 'PARENT'])
def test_nothing_inside_a_photo_folder_is_deleted(project, folder):
    # a photo folder that is the project folder or holds it holds every item (review)
    folder = {'ROOT': str(project), 'PARENT': str(project.parent)}.get(folder, folder)
    (project / 'settings.json').write_text(json.dumps({'photo_folders': [folder]}), encoding='utf-8')
    items, skipped = plan(project)
    assert items == []
    assert sorted(path.name for path, _ in skipped) == sorted(
        ['.cache', '.tmp', '.venv', '__pycache__', '__pycache__', 'yolo11n.pt'])
    assert all('inside' in reason for _, reason in skipped)


case_insensitive = pytest.mark.skipif(os.path.normcase('A') == 'A' or not Path(__file__.upper()).exists(),
                                      reason='needs a case-insensitive file system (Windows)')


@case_insensitive
def test_a_kept_entry_in_another_case_is_kept(project):
    # settings name .tmp\eval\shots, the folder on disk is .tmp\Eval (review)
    (project / '.tmp' / 'eval').rename(project / '.tmp' / 'Eval')
    shot = write(project / '.tmp' / 'Eval' / 'shots' / 'IMG_0003.jpg', b'shot')
    (project / 'settings.json').write_text(json.dumps({'photo_folders': ['.tmp/eval/shots']}), encoding='utf-8')
    items, skipped = plan(project)
    tmp = next(item for item in items if item.path.name == '.tmp')
    assert tmp.size == 10 and skipped == []
    assert remove_items(items) == []
    assert shot.is_file() and (project / '.tmp' / 'Eval' / 'cosplay' / 'labels.json').is_file()
    assert not (project / '.tmp' / 'pip-build').exists()


@case_insensitive
def test_a_tmp_folder_with_only_kept_entries_in_another_case_is_not_listed(project):
    (project / '.tmp' / 'pip-build' / 'x.whl').unlink()
    (project / '.tmp' / 'pip-build').rmdir()
    (project / '.tmp' / 'eval').rename(project / '.tmp' / 'EVAL')
    assert '.tmp' not in names(plan(project)[0], project)


def failing_scandir(monkeypatch, folder):
    original = os.scandir

    def scandir(path='.'):
        if isinstance(path, (str, os.PathLike)) and Path(path) == folder:  # shutil may pass a file descriptor
            raise PermissionError(13, 'Access is denied', str(path))
        return original(path)
    monkeypatch.setattr(uninstall_module.os, 'scandir', scandir)


def test_an_unlistable_item_with_kept_entries_is_skipped(project, monkeypatch):
    failing_scandir(monkeypatch, project / '.tmp')
    items, skipped = plan(project)
    assert '.tmp' not in names(items, project) and '.cache' in names(items, project)
    assert [path.name for path, _ in skipped] == ['.tmp'] and 'cannot be listed' in skipped[0][1]


def test_an_unlistable_item_does_not_stop_the_other_items(project, monkeypatch):
    items, _ = plan(project)
    failing_scandir(monkeypatch, project / '.tmp')
    failures = remove_items(items)
    assert [path for path, _ in failures] == [project / '.tmp']
    assert not (project / '.venv').exists() and not (project / 'yolo11n.pt').exists()
    assert (project / '.tmp' / 'eval' / 'cosplay' / 'labels.json').is_file()


# --- remove_items ---

def test_removing_the_plan_keeps_the_user_data(project):
    items, _ = plan(project)
    assert remove_items(items) == []
    for item in items:
        assert not os.path.lexists(item.path) or item.path.name == '.tmp'
    assert sorted(p.name for p in (project / '.tmp').iterdir()) == ['eval']
    assert_user_data_kept(project)


def test_an_emptied_tmp_folder_is_removed(project):
    (project / '.tmp' / 'eval' / 'cosplay' / 'labels.json').unlink()
    (project / '.tmp' / 'eval' / 'cosplay').rmdir()
    (project / '.tmp' / 'eval').rmdir()
    assert remove_items(plan(project)[0]) == []
    assert not (project / '.tmp').exists()


def test_read_only_files_are_removed(project):
    path = project / '.cache' / 'huggingface' / 'model.bin'
    os.chmod(path, stat.S_IREAD)
    single = project / 'yolo11n.pt'
    os.chmod(single, stat.S_IREAD)
    assert remove_items(plan(project)[0]) == []
    assert not path.exists() and not single.exists()


def test_the_environment_python_goes_first(project, monkeypatch):
    # an environment whose removal stops halfway must not look complete to the installer
    def fail(path, failures):
        failures.append((Path(path), OSError('in use')))
    monkeypatch.setattr(uninstall_module, '_remove_tree', fail)
    items = [item for item in plan(project)[0] if item.path.name == '.venv']
    failures = remove_items(items)
    assert [path.name for path, _ in failures] == ['.venv']
    assert not (project / '.venv' / 'Scripts' / 'python.exe').exists()
    assert (project / '.venv' / 'pyvenv.cfg').exists()


def test_failures_are_reported_and_the_rest_is_removed(project, monkeypatch):
    original = os.remove

    def remove(path, *args, **kwargs):
        if Path(path).name == 'yolo11n.pt':
            raise OSError('locked')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(uninstall_module.os, 'remove', remove)
    monkeypatch.setattr(uninstall_module.os, 'chmod', lambda *args: None)
    failures = remove_items(plan(project)[0])
    assert [path.name for path, _ in failures] == ['yolo11n.pt']
    assert not (project / '.cache').exists()


def test_a_locked_file_is_reported_once_without_its_folders(project, monkeypatch):
    # its folders cannot be removed because it is still there: only the file is the culprit (review)
    original = os.unlink
    calls = []

    def unlink(path, *args, **kwargs):
        if Path(path).name == 'model.bin':
            calls.append(path)
            raise PermissionError(13, 'The process cannot access the file', str(path))
        return original(path, *args, **kwargs)
    monkeypatch.setattr(uninstall_module.os, 'unlink', unlink)
    items = [item for item in plan(project)[0] if item.path.name == '.cache']
    failures = remove_items(items)
    assert [path.name for path, _ in failures] == ['model.bin']
    assert len(calls) == 1  # not read-only: no second try


@windows_only
def test_a_read_only_folder_is_removed(project):
    folder = project / '.cache' / 'huggingface'
    os.chmod(folder, stat.S_IREAD)
    assert remove_items([item for item in plan(project)[0] if item.path.name == '.cache']) == []
    assert not (project / '.cache').exists()


@windows_only
def test_a_junction_inside_a_folder_is_removed_without_its_target(project, tmp_path):
    import _winapi
    target = tmp_path / 'elsewhere'
    write(target / 'keep.jpg')
    _winapi.CreateJunction(str(target), str(project / '.cache' / 'linked'))
    write(target / 'tmp-keep.jpg')
    _winapi.CreateJunction(str(target), str(project / '.tmp' / 'linked'))
    items, _ = plan(project)
    assert {item.path.name: item.size for item in items}['.cache'] == 500  # not followed
    assert remove_items(items) == []
    assert not (project / '.cache').exists()
    assert (target / 'keep.jpg').is_file() and (target / 'tmp-keep.jpg').is_file()


@windows_only
def test_a_linked_cache_folder_loses_only_its_link(project, tmp_path):
    import _winapi
    import shutil
    target = tmp_path / 'D-drive-cache'
    shutil.move(project / '.cache', target)
    _winapi.CreateJunction(str(target), str(project / '.cache'))
    items, _ = plan(project)
    cache = next(item for item in items if item.path.name == '.cache')
    assert cache.link and cache.size == 0 and 'only the link' in cache.label
    assert remove_items([cache]) == []
    assert not os.path.lexists(project / '.cache')
    assert (target / 'huggingface' / 'model.bin').is_file()


# --- running FrameScout blocks the uninstall ---

def test_a_running_search_is_detected(project):
    lock = RunLock(project / 'results' / 'run.lock')
    assert lock.acquire(timeout=1)
    try:
        assert search_running(project)
    finally:
        lock.release()
    assert not search_running(project)


@windows_only
def test_a_running_environment_python_is_detected(project):
    import _winapi
    exe = project / ENVIRONMENT_PROGRAMS[0]
    assert programs_in_use(project) == []
    # a running program is open without write sharing; this handle does the same
    handle = _winapi.CreateFile(str(exe), _winapi.GENERIC_READ, 0, 0, _winapi.OPEN_EXISTING, 0, 0)
    try:
        assert programs_in_use(project) == [exe]
    finally:
        _winapi.CloseHandle(handle)


@windows_only
def test_a_read_only_environment_python_is_not_taken_for_a_running_one(project):
    # opening a read-only file for writing fails too, but it does not tell that it runs (review)
    exe = project / ENVIRONMENT_PROGRAMS[0]
    os.chmod(exe, stat.S_IREAD)
    try:
        assert programs_in_use(project) == []
    finally:
        os.chmod(exe, stat.S_IWRITE | stat.S_IREAD)


@windows_only
def test_a_running_read_only_environment_python_is_detected_after_clearing_the_attribute(project):
    import _winapi
    exe = project / ENVIRONMENT_PROGRAMS[0]
    os.chmod(exe, stat.S_IREAD)
    handle = _winapi.CreateFile(str(exe), _winapi.GENERIC_READ, 0, 0, _winapi.OPEN_EXISTING, 0, 0)
    try:
        assert programs_in_use(project) == []  # read-only: cannot tell
        assert programs_in_use(project, clear_read_only=True) == [exe]
    finally:
        _winapi.CloseHandle(handle)
    assert os.stat(exe).st_mode & stat.S_IWRITE


def test_the_check_after_the_confirmation_clears_the_read_only_attribute(project, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(framescout_uninstall, 'programs_in_use',
                        lambda root, clear_read_only=False: calls.append(clear_read_only) or [])
    code, _, _ = run(project, tmp_path, 'yes')
    assert code == 0 and calls == [False, True]


# --- user_data and outside_leftovers: listed only ---

def test_user_data_lists_what_exists_without_walking_it(project, monkeypatch):
    # photos/ and results/ may hold many thousands of files, never deleted: no sizes (review)
    monkeypatch.setattr(uninstall_module, '_tree_size', lambda *args: pytest.fail('walked the user data'))
    rows = [path.relative_to(project).as_posix() for path, _ in user_data(project)]
    assert rows == ['photos', 'references', 'results', 'profiles.json', 'settings.json', 'run.log', '.tmp/eval']


def test_caches_in_the_user_profile_are_listed(project, tmp_path):
    home = tmp_path / 'home'
    write(home / '.cache' / 'huggingface' / 'hub' / 'model.bin', b'h' * 7)
    write(home / 'AppData' / 'Roaming' / 'Ultralytics' / 'settings.json')
    found = outside_leftovers(project, {}, home)
    assert [(path, size) for path, _, size in found] == [(home / '.cache' / 'huggingface', 7),
                                                       (home / 'AppData' / 'Roaming' / 'Ultralytics', 1)]


def test_cache_variables_are_followed_but_not_into_the_project(project, tmp_path):
    torch_home = write(tmp_path / 'torch-cache' / 'hub' / 'w.pt').parent.parent
    environ = {'TORCH_HOME': str(torch_home), 'HF_HOME': str(project / '.cache' / 'huggingface'),
               'APPDATA': str(tmp_path / 'nothing')}
    assert [path for path, _, _ in outside_leftovers(project, environ, tmp_path / 'home')] == [torch_home]


# --- main: the dialog ---

def run(project, tmp_path, answer=None, argv=()):
    lines, questions = [], []

    def ask(question):
        questions.append(question)
        if answer is None:
            raise EOFError
        return answer
    code = framescout_uninstall.main(list(argv), root=project, environ={}, home=tmp_path / 'home', ask=ask,
                                     out=lines.append)
    return code, '\n'.join(lines), questions


def test_only_yes_deletes(project, tmp_path):
    for answer in (None, '', 'no', 'y', 'ja'):
        code, text, questions = run(project, tmp_path, answer)
        assert code == 0 and 'nothing was deleted' in text and len(questions) == 1
        assert (project / '.venv').exists()
    code, text, _ = run(project, tmp_path, ' YES ')
    assert code == 0 and 'Done:' in text
    assert not (project / '.venv').exists() and not (project / '.cache').exists()
    assert_user_data_kept(project)


def test_the_list_shows_deleted_and_kept_items(project, tmp_path):
    code, text, _ = run(project, tmp_path, 'no')
    deleted, kept = text.split('Kept (your data')
    for name in ('.venv', '.cache', '.tmp', 'yolo11n.pt', '__pycache__'):
        assert name in deleted
    for name in ('photos', 'references', 'results', 'profiles.json', 'settings.json', 'run.log'):
        assert re.search(rf'^\s+{re.escape(name)}', kept, re.MULTILINE), name
    assert 'eval' in deleted  # "temporary files (except .tmp/eval)"


def test_a_dry_run_never_asks_or_deletes(project, tmp_path):
    code, text, questions = run(project, tmp_path, 'yes', ['--dry-run'])
    assert code == 0 and questions == [] and 'Dry run' in text
    assert (project / '.venv').exists()


def test_a_running_search_stops_the_uninstall(project, tmp_path):
    lock = RunLock(project / 'results' / 'run.lock')
    assert lock.acquire(timeout=1)
    try:
        code, text, questions = run(project, tmp_path, 'yes')
    finally:
        lock.release()
    assert code == 1 and 'search is running' in text and questions == []
    assert (project / '.venv').exists()


def test_a_start_while_the_question_waits_stops_the_uninstall(project, tmp_path, monkeypatch):
    answers = iter([False, True])
    monkeypatch.setattr(framescout_uninstall, 'search_running', lambda root: next(answers))
    code, text, _ = run(project, tmp_path, 'yes')
    assert code == 1 and 'search is running' in text
    assert (project / '.venv').exists()


def test_an_unreadable_settings_file_stops_the_uninstall(project, tmp_path):
    (project / 'settings.json').write_text('{not json', encoding='utf-8')
    code, text, questions = run(project, tmp_path, 'yes')
    assert code == 1 and 'settings.json cannot be read' in text and questions == []
    assert (project / '.venv').exists()


def test_failures_end_with_exit_code_1(project, tmp_path, monkeypatch):
    monkeypatch.setattr(framescout_uninstall, 'remove_items', lambda items: [(project / '.venv', OSError('busy'))])
    code, text, _ = run(project, tmp_path, 'yes')
    assert code == 1 and 'could not be deleted' in text and 'run the uninstall again' in text


def test_nothing_to_delete(tmp_path):
    root = tmp_path / 'FrameScout'
    write(root / 'app.py')
    code, text, questions = run(root, tmp_path, 'yes')
    assert code == 0 and 'Nothing to delete' in text and questions == []


def test_a_photo_folder_holding_the_project_stops_the_uninstall(project, tmp_path):
    (project / 'settings.json').write_text(json.dumps({'photo_folders': [str(project)]}), encoding='utf-8')
    code, text, questions = run(project, tmp_path, 'yes')
    assert code == 1 and questions == [] and 'Nothing to delete' not in text
    assert f'Not deleted: .venv{os.sep} is inside the folder {project}' in text
    assert 'photo folders' in text  # how to get past it
    assert (project / '.venv').exists()


# --- Uninstall-FrameScout.bat ---

def batch_commands(text):
    lines = (line.strip() for line in text.splitlines())
    return [line for line in lines if line and not re.match(r'(?i)(rem\b|::|echo\b|:)', line)]


def uninstaller():
    return (ROOT / 'Uninstall-FrameScout.bat').read_text(encoding='utf-8')


def test_the_uninstaller_runs_the_script_outside_the_environment():
    commands = batch_commands(uninstaller())
    runs = [line for line in commands if 'framescout_uninstall.py' in line]
    assert len(runs) == 1 and runs[0].startswith('py -') and runs[0].endswith('%*')
    assert not any('.venv' in line for line in commands)  # .venv's Python cannot delete itself


def test_the_uninstaller_looks_for_the_python_versions_of_the_installer():
    pattern = r'for %%V in \(([\d. ]+)\) do'
    installer = (ROOT / 'Install-FrameScout.bat').read_text(encoding='utf-8')
    assert re.search(pattern, uninstaller()).group(1) == re.search(pattern, installer).group(1)


def test_the_uninstaller_does_not_point_temporary_files_into_the_project():
    # .tmp is deleted, and the user's cache folders are what the script reports
    for line in batch_commands(uninstaller()):
        assert not re.match(r'(?i)set "(TMP|TEMP|TORCH_HOME|HF_HOME|XDG_CACHE_HOME|YOLO_CONFIG_DIR|PIP_\w+)=', line)
