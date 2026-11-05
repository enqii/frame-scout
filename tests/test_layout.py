"""Program files of two FrameScout versions in one folder (I16).

FrameScout before I15 had the single file framescout_core.py, newer versions have the
package framescout_core/. A ZIP extracted over a folder of the other version leaves both,
and Python always imports the package: after a rollback the older app would silently run
against the newer core. The package refuses to load next to the single file, and the
.bat files of the newer version delete the leftover single file of an update.
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from framescout_core import OBSOLETE_CORE_FILE, mixed_versions_message

ROOT = Path(__file__).resolve().parent.parent
windows_only = pytest.mark.skipif(sys.platform != 'win32', reason='runs a .bat file')


def batch_commands(text):
    lines = (line.strip() for line in text.splitlines())
    return [line for line in lines if line and not re.match(r'(?i)(rem\b|::|echo\b|:)', line)]


def test_the_obsolete_file_is_the_single_file_of_older_versions():
    assert OBSOLETE_CORE_FILE == 'framescout_core.py'
    assert not (ROOT / OBSOLETE_CORE_FILE).exists()


def test_a_folder_without_the_single_file_is_fine(tmp_path):
    (tmp_path / 'framescout_core').mkdir()
    assert mixed_versions_message(tmp_path) is None


def test_the_single_file_next_to_the_package_is_reported(tmp_path):
    (tmp_path / OBSOLETE_CORE_FILE).write_text('', encoding='utf-8')
    message = mixed_versions_message(tmp_path)
    assert str(tmp_path) in message and OBSOLETE_CORE_FILE in message
    # the user knows whether they updated or went back: both fixes are named
    assert 'delete framescout_core.py' in message and 'delete the folder framescout_core' in message
    assert 'new, empty folder' in message


def test_a_folder_named_like_the_single_file_is_not_reported(tmp_path):
    (tmp_path / OBSOLETE_CORE_FILE).mkdir()
    assert mixed_versions_message(tmp_path) is None


def copy_of_the_package(folder):
    shutil.copytree(ROOT / 'framescout_core', folder / 'framescout_core',
                    ignore=shutil.ignore_patterns('__pycache__'))


def import_core(folder):
    # the script folder (here the current directory of -c) comes first on sys.path, as for app.py
    return subprocess.run([sys.executable, '-B', '-c', 'import framescout_core'], cwd=folder,
                          capture_output=True, text=True, encoding='utf-8', errors='replace')


def test_the_package_refuses_to_load_next_to_the_single_file(tmp_path):
    # e.g. an older ZIP extracted over a newer folder: the older app.py imports the package
    folder = tmp_path / 'Fo!to (old)'
    folder.mkdir()
    copy_of_the_package(folder)
    (folder / OBSOLETE_CORE_FILE).write_text("raise SystemExit('the single file was imported')\n",
                                             encoding='utf-8')
    result = import_core(folder)
    assert result.returncode == 1
    assert 'ImportError' in result.stderr and 'delete the folder framescout_core' in result.stderr
    assert 'the single file was imported' not in result.stderr + result.stdout


def test_the_package_loads_without_the_single_file(tmp_path):
    copy_of_the_package(tmp_path)
    result = import_core(tmp_path)
    assert result.returncode == 0, result.stderr


# --- the .bat files of this version delete the leftover of an update ---

def cleanup_commands(name):
    """All commands, the index of the first cleanup command and the cleanup lines with echo."""
    text = (ROOT / name).read_text(encoding='utf-8')
    commands = batch_commands(text)
    first = next(i for i, line in enumerate(commands) if OBSOLETE_CORE_FILE in line)
    lines = [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith('rem ')]
    start = next(i for i, line in enumerate(lines) if OBSOLETE_CORE_FILE in line)
    return commands, first, lines[start:lines.index(':obsolete_done', start)]


def test_install_and_start_delete_the_single_file_the_same_way():
    _, _, start = cleanup_commands('Start-FrameScout.bat')
    _, _, install = cleanup_commands('Install-FrameScout.bat')
    assert start == install
    # only next to the package: the folder of an older version keeps its core
    assert any('framescout_core\\__init__.py' in line for line in start)
    assert sum(line.startswith('del ') for line in start) == 1
    # a directory of that name is no leftover: del would ask and delete the files in it (review)
    directory = start.index(f'if exist "{OBSOLETE_CORE_FILE}\\*" goto obsolete_done')
    assert directory < next(i for i, line in enumerate(start) if line.startswith('del '))
    # a read-only file is deleted too, and a file that stays stops the .bat (review)
    deletion = start.index(f'del /f "{OBSOLETE_CORE_FILE}"')
    assert start[deletion + 1] == f'if not exist "{OBSOLETE_CORE_FILE}" goto obsolete_done'
    assert start[-2:] == ['pause', 'exit /b 1']


def test_the_uninstaller_does_not_delete_the_single_file():
    # after going back to a version before I15 (which had no uninstaller), this version's
    # Uninstall-FrameScout.bat stays in the folder, and the single file is that version's core
    text = (ROOT / 'Uninstall-FrameScout.bat').read_text(encoding='utf-8')
    assert not any(OBSOLETE_CORE_FILE in line for line in batch_commands(text))


def test_the_single_file_is_deleted_before_python_runs():
    for name in ('Start-FrameScout.bat', 'Install-FrameScout.bat'):
        commands, first, _ = cleanup_commands(name)
        python = next(i for i, line in enumerate(commands) if 'python.exe' in line)
        assert first < python, name


def test_the_cleanup_keeps_exclamation_marks_and_stays_out_of_blocks():
    # no delayed expansion, and no "(" block a ")" of the folder path could end
    for name in ('Start-FrameScout.bat', 'Install-FrameScout.bat'):
        _, _, cleanup = cleanup_commands(name)
        assert not any('!' in line or '(' in line for line in cleanup), name


def run_start(folder):
    shutil.copy(ROOT / 'Start-FrameScout.bat', folder)
    # relative to the current directory (cmd may not search it), so no quoting of the
    # folder path is needed; %~dp0 is still the full path
    return subprocess.run(['cmd.exe', '/d', '/c', '.\\Start-FrameScout.bat'], cwd=folder, input='\n\n',
                          capture_output=True, text=True, errors='replace')


@windows_only
def test_start_deletes_the_single_file_next_to_the_package(tmp_path):
    folder = tmp_path / 'Fo!to (old) & co'
    (folder / 'framescout_core').mkdir(parents=True)
    (folder / 'framescout_core' / '__init__.py').write_text('', encoding='utf-8')
    (folder / OBSOLETE_CORE_FILE).write_text('', encoding='utf-8')
    result = run_start(folder)
    assert not (folder / OBSOLETE_CORE_FILE).exists()
    assert (folder / 'framescout_core' / '__init__.py').exists()
    assert OBSOLETE_CORE_FILE in result.stdout
    # no .venv here: the start stops as before
    assert 'run Install-FrameScout.bat first' in result.stdout and result.returncode == 1


@windows_only
def test_start_keeps_the_single_file_without_the_package(tmp_path):
    (tmp_path / OBSOLETE_CORE_FILE).write_text('', encoding='utf-8')
    result = run_start(tmp_path)
    assert (tmp_path / OBSOLETE_CORE_FILE).exists()
    assert OBSOLETE_CORE_FILE not in result.stdout


def folder_with_the_package(folder):
    (folder / 'framescout_core').mkdir(parents=True)
    (folder / 'framescout_core' / '__init__.py').write_text('', encoding='utf-8')
    return folder


@windows_only
@pytest.mark.parametrize('content', [None, 'kept.txt'])
def test_start_keeps_a_folder_named_like_the_single_file(tmp_path, content):
    # del "framescout_core.py" would ask and then delete the files in such a folder (review)
    folder = folder_with_the_package(tmp_path)
    (folder / OBSOLETE_CORE_FILE).mkdir()
    if content:
        (folder / OBSOLETE_CORE_FILE / content).write_text('x', encoding='utf-8')
    result = run_start(folder)
    assert (folder / OBSOLETE_CORE_FILE).is_dir()
    assert content is None or (folder / OBSOLETE_CORE_FILE / content).exists()
    assert 'Deleting' not in result.stdout and 'run Install-FrameScout.bat first' in result.stdout


@windows_only
def test_start_deletes_a_read_only_single_file(tmp_path):
    import stat
    folder = folder_with_the_package(tmp_path)
    (folder / OBSOLETE_CORE_FILE).write_text('', encoding='utf-8')
    (folder / OBSOLETE_CORE_FILE).chmod(stat.S_IREAD)
    result = run_start(folder)
    assert not (folder / OBSOLETE_CORE_FILE).exists(), result.stdout + result.stderr
    assert 'run Install-FrameScout.bat first' in result.stdout


@windows_only
def test_start_stops_when_the_single_file_cannot_be_deleted(tmp_path):
    folder = folder_with_the_package(tmp_path)
    # Python opens files without delete sharing on Windows: like a file open in an editor
    with open(folder / OBSOLETE_CORE_FILE, 'w', encoding='utf-8'):
        result = run_start(folder)
    assert (folder / OBSOLETE_CORE_FILE).exists()
    assert 'could not be deleted' in result.stdout and result.returncode == 1
    # it stops before it looks for the environment
    assert 'run Install-FrameScout.bat first' not in result.stdout
