"""One version file per FrameScout version (I42).

The folder holds one framescout-version-<version>.txt. A ZIP extracted over the folder of
another version leaves the other version's file too, so Install-FrameScout.bat and
Start-FrameScout.bat stop when they find more than one, before any Python runs, and the
installation check reports it.
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from framescout_core import VERSION_FILE_PATTERN, check_program_files

ROOT = Path(__file__).resolve().parent.parent
windows_only = pytest.mark.skipif(sys.platform != 'win32', reason='runs a .bat file')
BATCH_FILES = ('Install-FrameScout.bat', 'Start-FrameScout.bat')
END_LABEL = ':version_checked'


def test_the_repository_has_one_version_file_named_by_its_version():
    [version_file] = ROOT.glob(VERSION_FILE_PATTERN)
    assert re.fullmatch(r'framescout-version-\d+\.\d+\.\d+\.txt', version_file.name)


def version_check(name):
    """The lines of the version check in a .bat file (without rem lines), up to its end label."""
    lines = [line.strip() for line in (ROOT / name).read_text(encoding='utf-8').splitlines()]
    lines = [line for line in lines if line and not line.lower().startswith('rem ')]
    start = next(i for i, line in enumerate(lines) if VERSION_FILE_PATTERN in line)
    return lines, start - 1, lines[start - 1:lines.index(END_LABEL) + 1]


def test_install_and_start_check_the_version_files_the_same_way():
    _, _, install = version_check('Install-FrameScout.bat')
    _, _, start = version_check('Start-FrameScout.bat')
    assert install == start
    assert start[0] == 'set "VERSION_FILES=0"'
    assert start[-3:] == ['pause', 'exit /b 1', END_LABEL]


@pytest.mark.parametrize('name', BATCH_FILES)
def test_the_version_check_comes_before_anything_runs(name):
    lines, first, check = version_check(name)
    assert lines.index('cd /d "%~dp0"') < first
    assert first < min(i for i, line in enumerate(lines) if 'python' in line.lower() or 'curl' in line.lower())
    # no delayed expansion: it would remove a "!" of the folder path (I21)
    assert not any('!' in line for line in check)


def run_start(folder):
    shutil.copy(ROOT / 'Start-FrameScout.bat', folder)
    # relative to the current directory (cmd may not search it), so no quoting of the
    # folder path is needed; %~dp0 is still the full path
    return subprocess.run(['cmd.exe', '/d', '/c', '.\\Start-FrameScout.bat'], cwd=folder, input='\n\n',
                          capture_output=True, text=True, errors='replace')


@windows_only
@pytest.mark.parametrize('versions', [(), ('1.5.0',)])
def test_start_runs_with_one_version_file(tmp_path, versions):
    folder = tmp_path / 'Fo!to (new) & co'
    folder.mkdir()
    for version in versions:
        (folder / f'framescout-version-{version}.txt').write_text('', encoding='utf-8')
    result = run_start(folder)
    # no .venv here: the start gets past the check and stops at the missing environment
    assert 'two FrameScout versions' not in result.stdout
    assert 'run Install-FrameScout.bat first' in result.stdout and result.returncode == 1


@windows_only
def test_start_stops_with_the_version_files_of_two_versions(tmp_path):
    folder = tmp_path / 'Fo!to (old) & co'
    folder.mkdir()
    for version in ('1.5.0', '1.6.0'):
        (folder / f'framescout-version-{version}.txt').write_text('', encoding='utf-8')
    result = run_start(folder)
    assert 'two FrameScout versions' in result.stdout and 'new, empty folder' in result.stdout
    # the user's data stays in this folder: the message names what to copy (review)
    assert 'profiles.json, settings.json' in result.stdout
    assert 'run Install-FrameScout.bat first' not in result.stdout and result.returncode == 1


def test_the_check_reports_the_version_files_of_two_versions(tmp_path):
    [fine] = check_program_files(tmp_path)
    assert fine.ok is True
    (tmp_path / 'framescout-version-1.5.0.txt').write_text('', encoding='utf-8')
    [fine] = check_program_files(tmp_path)
    assert fine.ok is True
    (tmp_path / 'framescout-version-1.6.0.txt').write_text('', encoding='utf-8')
    [problem] = check_program_files(tmp_path)
    assert problem.ok is False
    assert 'framescout-version-1.5.0.txt' in problem.text and 'framescout-version-1.6.0.txt' in problem.text
    assert 'new, empty folder' in problem.fix and 'profiles.json' in problem.fix
