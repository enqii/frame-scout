"""The .sh scripts for Linux: the counterparts of the four .bat files.

The scripts are checked as text on every platform; on Linux they also run in a copy of the
folder with stand-ins for the Python scripts they start (nothing is downloaded or installed).
"""
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import install_torch
from framescout_core.cache_dirs import XDG_DERIVED, cache_paths
from framescout_core.install_check import VERSION_FILE_PATTERN
from framescout_core.portable_python import LINUX_PYTHON_SHA256, LINUX_PYTHON_URL, PRIVATE_PYTHON, PYTHON_VERSION
from framescout_core.uninstall import PRIVATE_PYTHON_EXIT_CODE

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ('Install-FrameScout.sh', 'Start-FrameScout.sh', 'Check-FrameScout.sh', 'Uninstall-FrameScout.sh')
# on Windows, "bash" may be the one of WSL or Git, which see other paths
linux_only = pytest.mark.skipif(sys.platform == 'win32', reason='runs a .sh script with bash')
# a folder path with blanks, "!", "&", "$" and parentheses: every use of it must be quoted
ODD_FOLDER = 'Fo!to (x86) & co $HOME'


def text(name):
    return (ROOT / name).read_text(encoding='utf-8')


def commands(name):
    """The lines of the script name without comments, blank lines and echo lines."""
    lines = (line.strip() for line in text(name).splitlines())
    return [line for line in lines if line and not line.startswith(('#', 'echo '))]


def setting(name):
    match = re.search(rf'^{name}="([^"]*)"$', text('Install-FrameScout.sh'), re.MULTILINE)
    assert match, name
    return match.group(1)


def index(lines, pattern):
    found = [i for i, line in enumerate(lines) if re.search(pattern, line)]
    assert len(found) == 1, (pattern, found)
    return found[0]


def test_every_bat_file_has_a_linux_script():
    assert sorted(path.stem for path in ROOT.glob('*.bat')) == sorted(Path(name).stem for name in SCRIPTS)


@pytest.mark.parametrize('name', SCRIPTS)
def test_the_scripts_are_bash_scripts_that_run_in_their_folder(name):
    raw = (ROOT / name).read_bytes()
    # bash stops at the CR of a CRLF line ending (.gitattributes keeps LF in every clone)
    assert b'\r' not in raw
    lines = commands(name)
    assert raw.startswith(b'#!/usr/bin/env bash\n')
    assert lines[:2] == ['set -u', 'cd -- "$(dirname -- "$0")" || exit 1']


@linux_only
@pytest.mark.parametrize('name', SCRIPTS)
def test_the_scripts_are_executable_and_valid_bash(name):
    assert os.access(ROOT / name, os.X_OK)
    result = subprocess.run(['bash', '-n', str(ROOT / name)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


# --- the private Python ---

def test_the_linux_installer_pins_the_python_of_framescout_core():
    assert setting('PYTHON_VERSION') == PYTHON_VERSION
    assert setting('PYTHON_URL') == LINUX_PYTHON_URL
    assert setting('PYTHON_SHA256') == LINUX_PYTHON_SHA256
    assert re.fullmatch(r'[0-9a-f]{64}', LINUX_PYTHON_SHA256)
    # a version bump changes PYTHON_VERSION and the URL; every other name uses $PYTHON_VERSION
    assert text('Install-FrameScout.sh').count(PYTHON_VERSION) == 2


def test_the_installer_needs_no_installed_python():
    assert not any(re.match(r'(python3?|py)\s', line) for line in commands('Install-FrameScout.sh'))


VENV_CREATE = rf'{re.escape(PRIVATE_PYTHON)}/bin/python3 -I -m venv --clear \.venv;'


def test_the_download_is_checked_before_it_is_extracted_and_used():
    lines = commands('Install-FrameScout.sh')
    order = [index(lines, r'^if ! curl .* -o "\$PYTHON_ARCHIVE" "\$PYTHON_URL"; then$'),
             index(lines, r'^if \[ "\$\(sha256sum "\$PYTHON_ARCHIVE" \| cut .*\)" != "\$PYTHON_SHA256" \]; then$'),
             index(lines, r'^if ! tar -xzf "\$PYTHON_ARCHIVE" -C "\$PYTHON_UNPACKED" '),
             index(lines, rf'^if ! mv "\$PYTHON_UNPACKED/python" {re.escape(PRIVATE_PYTHON)}; then$'),
             index(lines, VENV_CREATE)]
    assert order == sorted(order)
    # each step stops the installation when it fails
    for i in order:
        assert lines[i + 1].startswith(('failed ', 'rm -')), lines[i + 1]
    checksum = order[1]
    assert lines[checksum + 1:checksum + 3] == ['rm -f "$PYTHON_ARCHIVE"', 'failed "The downloaded Python does not '
                                                'match the checksum (SHA-256) that its publisher" \\']


def test_an_existing_private_python_is_kept_when_the_download_cannot_happen():
    lines = commands('Install-FrameScout.sh')
    start = index(lines, r'^download_python\(\) \{$')
    prerequisites = [index(lines, r'^if \[ "\$\(uname -m\)" != x86_64 \]; then$'),
                     index(lines, r'^if ! command -v curl >/dev/null 2>&1; then$')]
    assert start < min(prerequisites) and max(prerequisites) < index(lines, r'^rm -rf \.python$')


def test_the_python_is_extracted_in_tmp_and_moved_as_a_whole():
    # an interrupted extraction must not leave a .python that looks complete
    assert setting('PYTHON_ARCHIVE').startswith('.tmp/')
    assert setting('PYTHON_UNPACKED').startswith('.tmp/')


def test_a_failed_function_ends_the_installer():
    script = text('Install-FrameScout.sh')
    assert re.search(r'^failed\(\) \{\n  for line in "\$@"; do echo "\$line"; done\n  exit 1\n\}$', script, re.MULTILINE)


def test_an_existing_private_python_is_reused_only_if_complete_and_pinned():
    lines = commands('Install-FrameScout.sh')
    check = index(lines, r'^\[ -x \.python/bin/python3 \] && \.python/bin/python3 -I -c "import sys, platform, venv, '
                         r'ensurepip; sys\.exit\(platform\.python_version\(\) not in sys\.argv\[1:\]\)" '
                         r'"\$PYTHON_VERSION" >/dev/null 2>&1$')
    assert lines[check - 1] == 'private_python_works() {'


def test_the_python_check_accepts_only_the_pinned_version():
    code = re.search(r'-c "([^"]+)" "\$PYTHON_VERSION"', text('Install-FrameScout.sh')).group(1)
    # only the version comparison: the Python of the tests may lack ensurepip (Debian's
    # system Python without python3-venv); the test above pins the imports
    code = code.replace(', venv, ensurepip;', ';', 1)
    assert 'ensurepip' not in code
    assert subprocess.run([sys.executable, '-I', '-c', code, platform.python_version()]).returncode == 0
    assert subprocess.run([sys.executable, '-I', '-c', code, '3.0.0']).returncode == 1


def test_a_working_environment_is_kept_without_downloading_python():
    lines = commands('Install-FrameScout.sh')
    assert lines[index(lines, r'^venv_works\(\) \{$') + 1] == \
        '[ -x .venv/bin/python ] && .venv/bin/python -I -c "import pip" >/dev/null 2>&1'
    start = lines.index('if ! venv_works; then')
    body = lines[start:index(lines, r'^export PIP_CONSTRAINT=')]
    assert body[1] == 'if [ -e .venv ]; then'  # only a message for a broken one
    # a .venv of the private Python works again once .python is downloaded again
    assert body[-7:] == ['if ! private_python_works; then', 'download_python', 'fi',
                         'if ! venv_works; then', 'create_venv', 'fi', 'fi']


def test_a_half_created_environment_is_removed():
    lines = commands('Install-FrameScout.sh')
    assert lines[index(lines, VENV_CREATE) + 1] == 'rm -rf .venv'


def test_the_packages_are_installed_with_the_constraints():
    lines = commands('Install-FrameScout.sh')
    constraint = index(lines, r'^export PIP_CONSTRAINT="requirements/constraints\.txt"$')
    torch = index(lines, r'^\.venv/bin/python install_torch\.py \$\{TORCH_VARIANT:\+"\$TORCH_VARIANT"\}$')
    pip = index(lines, r'^if ! \.venv/bin/python -m pip install --no-cache-dir -r requirements/requirements\.txt '
                       r'-c requirements/constraints\.txt; then$')
    assert constraint < torch < pip
    # exit code 3 of install_torch.py: the user stopped on low disk space, not a failure;
    # exactly 3, since a process killed by a signal (OOM killer, Ctrl+C) exits with 128 + n
    assert lines[torch + 1:torch + 4] == ['TORCH_RESULT=$?',
                                          f'if [ "$TORCH_RESULT" -eq {install_torch.STOPPED_EXIT_CODE} ]; then',
                                          'failed "Installation stopped. Free some disk space, then run '
                                          'Install-FrameScout.sh again."']


# --- version files and cache variables, the same lines in install and start ---

def version_check(name):
    lines = commands(name)
    start = index(lines, r'^shopt -s nullglob$')
    assert VERSION_FILE_PATTERN in lines[start + 1]
    end = lines.index('fi', start)
    return lines, start, lines[start:end + 1]


def test_install_and_start_check_the_version_files_the_same_way():
    _, _, install = version_check('Install-FrameScout.sh')
    _, _, start = version_check('Start-FrameScout.sh')
    assert install == start
    assert start[-2:] == ['exit 1', 'fi']


@pytest.mark.parametrize('name', ('Install-FrameScout.sh', 'Start-FrameScout.sh'))
def test_the_version_check_comes_before_anything_runs(name):
    lines, start, _ = version_check(name)
    first_run = min(i for i, line in enumerate(lines) if re.search(r'python|curl|mkdir', line))
    assert start < first_run


def cache_lines(name):
    return [line for line in commands(name) if any(f'export {variable}=' in line for variable in cache_paths(ROOT))]


def test_the_scripts_set_only_the_cache_variables_a_user_did_not_set():
    # as in the .bat files: a variable the user set wins; the lines of the variables
    # derived from XDG_CACHE_HOME come before the line that sets it
    expected = []
    for variable, path in cache_paths(ROOT).items():
        condition = f'[ -z "${{{variable}:-}}" ]'
        if variable in XDG_DERIVED:
            condition += ' && [ -z "${XDG_CACHE_HOME:-}" ]'
        expected.append(f'if {condition}; then export {variable}="$PWD/{path.relative_to(ROOT).as_posix()}"; fi')
    for name in ('Install-FrameScout.sh', 'Start-FrameScout.sh'):
        lines = cache_lines(name)
        assert sorted(lines) == sorted(expected), name
        assert lines[-1] == expected[-1] and 'export XDG_CACHE_HOME=' in expected[-1], name
        assert commands(name)[index(commands(name), re.escape(lines[-1])) + 1:][:2] == [
            'export TMPDIR="$PWD/.tmp"', 'mkdir -p .tmp || exit 1']


def run_cache_lines(folder, environ):
    """The four cache variables after the cache lines of Start-FrameScout.sh ran in folder with environ."""
    names = list(cache_paths(ROOT))
    script = folder / 'cache.sh'
    script.write_text('\n'.join(['cd -- "$(dirname -- "$0")" || exit 1', *cache_lines('Start-FrameScout.sh'),
                                 *[f'printf "%s\\n" "{name}=${{{name}:-}}"' for name in names]]) + '\n',
                      encoding='utf-8')
    env = {k: v for k, v in os.environ.items() if k not in names}
    env.update(environ)
    result = subprocess.run(['bash', str(script)], env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    return {name: value for name, value in (line.split('=', 1) for line in result.stdout.splitlines()) if value}


@linux_only
def test_the_cache_lines_keep_a_variable_the_user_set(tmp_path):
    folder = tmp_path / ODD_FOLDER
    folder.mkdir()
    expected = {name: str(path) for name, path in cache_paths(folder).items()}
    assert run_cache_lines(folder, {}) == expected
    expected['HF_HOME'] = str(tmp_path / 'own-hf')
    assert run_cache_lines(folder, {'HF_HOME': expected['HF_HOME']}) == expected
    own = str(tmp_path / 'own cache')
    assert run_cache_lines(folder, {'XDG_CACHE_HOME': own}) == {'YOLO_CONFIG_DIR': expected['YOLO_CONFIG_DIR'],
                                                                'XDG_CACHE_HOME': own}


# --- the scripts run in a copy of the folder (Linux) ---

def copy_script(folder, name, versions=('1.5.0',)):
    shutil.copy(ROOT / name, folder)
    for version in versions:
        (folder / f'framescout-version-{version}.txt').write_text('', encoding='utf-8')


def run(folder, name, *args, environ=None):
    env = dict(os.environ, **(environ or {}))
    return subprocess.run(['bash', str(folder / name), *args], cwd=folder.parent, env=env, input='',
                          capture_output=True, text=True, timeout=60)


def stand_in_python(folder, relative):
    """A link at folder/relative to the Python of the tests: deleting it never deletes that Python."""
    link = folder / relative
    link.parent.mkdir(parents=True)
    link.symlink_to(sys.executable)
    return link


def stand_in_script(folder, name):
    """A stand-in for the Python script name that reports how it ran and exits with $FS_TEST_EXIT."""
    (folder / name).write_text(
        'import os, sys\n'
        'print("STAND-IN", sys.executable, sys.argv[1:], sys.flags.dont_write_bytecode,'
        ' sys.flags.ignore_environment, sys.flags.no_user_site)\n'
        'sys.exit(int(os.environ.get("FS_TEST_EXIT", "0")))\n', encoding='utf-8')


@pytest.fixture
def folder(tmp_path):
    folder = tmp_path / ODD_FOLDER
    folder.mkdir()
    return folder


@linux_only
@pytest.mark.parametrize('name', ('Install-FrameScout.sh', 'Start-FrameScout.sh'))
def test_the_scripts_stop_with_the_version_files_of_two_versions(folder, name):
    copy_script(folder, name, versions=('1.5.0', '1.6.0'))
    result = run(folder, name)
    assert result.returncode == 1 and 'two FrameScout versions' in result.stdout
    assert 'profiles.json, settings.json' in result.stdout and 'run Install-FrameScout.sh there' in result.stdout
    assert not (folder / '.tmp').exists()  # nothing ran


@linux_only
def test_install_rejects_an_unknown_build(folder):
    copy_script(folder, 'Install-FrameScout.sh')
    result = run(folder, 'Install-FrameScout.sh', 'gpu')
    assert result.returncode == 1 and 'Usage: ./Install-FrameScout.sh [cpu|cuda]' in result.stdout
    assert not (folder / '.tmp').exists()


@linux_only
def test_start_needs_the_environment(folder):
    copy_script(folder, 'Start-FrameScout.sh')
    result = run(folder, 'Start-FrameScout.sh')
    assert result.returncode == 1 and 'run Install-FrameScout.sh first' in result.stdout
    assert (folder / '.tmp').is_dir()


@linux_only
def test_start_runs_the_start_script_with_the_environment(folder):
    copy_script(folder, 'Start-FrameScout.sh')
    stand_in_python(folder, '.venv/bin/python')
    stand_in_script(folder, 'framescout_start.py')
    result = run(folder, 'Start-FrameScout.sh', environ={'FS_TEST_EXIT': '4', 'XDG_CACHE_HOME': ''})
    assert f'STAND-IN {folder}/.venv/bin/python [] 0 0 0' in result.stdout, result.stdout + result.stderr
    assert result.returncode == 4


@linux_only
@pytest.mark.parametrize('code', (0, 2))
def test_check_runs_with_the_environment_and_passes_its_result_on(folder, code):
    copy_script(folder, 'Check-FrameScout.sh')
    stand_in_python(folder, '.venv/bin/python')
    stand_in_python(folder, f'{PRIVATE_PYTHON}/bin/python3')
    stand_in_script(folder, 'framescout_check.py')
    result = run(folder, 'Check-FrameScout.sh', environ={'FS_TEST_EXIT': str(code)})
    assert result.stdout.splitlines() == [f'STAND-IN {folder}/.venv/bin/python [] 1 1 1']
    assert result.returncode == code


@linux_only
def test_check_tries_the_private_python_when_the_environment_cannot_run_it(folder):
    copy_script(folder, 'Check-FrameScout.sh')
    stand_in_python(folder, '.venv/bin/python')
    stand_in_python(folder, f'{PRIVATE_PYTHON}/bin/python3')
    stand_in_script(folder, 'framescout_check.py')
    result = run(folder, 'Check-FrameScout.sh', environ={'FS_TEST_EXIT': '5'})
    runs = [line for line in result.stdout.splitlines() if line.startswith('STAND-IN')]
    assert runs == [f'STAND-IN {folder}/.venv/bin/python [] 1 1 1',
                    f'STAND-IN {folder}/{PRIVATE_PYTHON}/bin/python3 [] 1 1 1']
    assert 'trying the private Python' in result.stdout and 'The check could not run' in result.stdout
    assert result.returncode == 1


@linux_only
def test_check_without_any_python_names_the_installer(folder):
    copy_script(folder, 'Check-FrameScout.sh')
    result = run(folder, 'Check-FrameScout.sh')
    assert result.returncode == 1 and 'Run Install-FrameScout.sh; it installs both.' in result.stdout


@linux_only
def test_the_uninstaller_names_the_manual_steps_without_the_private_python(folder):
    copy_script(folder, 'Uninstall-FrameScout.sh')
    result = run(folder, 'Uninstall-FrameScout.sh')
    assert result.returncode == 1 and 'There is no private Python in .python' in result.stdout
    assert f'.python, .cache and .tmp in "{folder}"' in result.stdout and result.stderr == ''


@linux_only
def test_the_uninstaller_runs_the_script_with_the_private_python(folder):
    copy_script(folder, 'Uninstall-FrameScout.sh')
    python = stand_in_python(folder, f'{PRIVATE_PYTHON}/bin/python3')
    stand_in_script(folder, 'framescout_uninstall.py')
    result = run(folder, 'Uninstall-FrameScout.sh', '--dry-run', 'a b', environ={'FS_TEST_EXIT': '5'})
    assert f"STAND-IN {python} ['--dry-run', 'a b'] 1 1 1" in result.stdout, result.stdout + result.stderr
    assert result.returncode == 5  # the script's exit code is passed on
    assert python.is_symlink()  # deleted only after exit code 3


@linux_only
def test_the_uninstaller_deletes_the_private_python_after_the_script_asked_for_it(folder):
    copy_script(folder, 'Uninstall-FrameScout.sh')
    stand_in_python(folder, f'{PRIVATE_PYTHON}/bin/python3')
    stand_in_script(folder, 'framescout_uninstall.py')
    result = run(folder, 'Uninstall-FrameScout.sh', environ={'FS_TEST_EXIT': str(PRIVATE_PYTHON_EXIT_CODE)})
    assert result.returncode == 0 and 'The private Python (.python) was deleted too.' in result.stdout
    assert not (folder / PRIVATE_PYTHON).exists()
    assert Path(sys.executable).is_file()  # the link was deleted, not the Python it points to


def test_the_uninstaller_deletes_nothing_else_and_python3_first():
    lines = commands('Uninstall-FrameScout.sh')
    run_line = index(lines, rf'^{re.escape(PRIVATE_PYTHON)}/bin/python3 -B -E -s framescout_uninstall\.py "\$@"$')
    assert lines[run_line + 1:run_line + 3] == ['EXIT_CODE=$?',
                                                f'if [ "$EXIT_CODE" -ne {PRIVATE_PYTHON_EXIT_CODE} ]; then exit '
                                                '"$EXIT_CODE"; fi']
    removals = [line for line in lines if line.startswith('rm ')]
    # the installer's check looks for bin/python3: a .python whose deletion stopped halfway never looks complete
    assert removals == [f'rm -f {PRIVATE_PYTHON}/bin/python3', f'rm -rf {PRIVATE_PYTHON}']
    assert not any(re.match(r'export ', line) for line in lines)  # no cache or temp variables
