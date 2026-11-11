"""Program files of two FrameScout versions in one folder (I16, I35, I36).

FrameScout before I15 had the single file framescout_core.py, before I30 framescout_scoring.py;
newer versions have the packages framescout_core/ and framescout_scoring/. A ZIP extracted over
a folder of the other version leaves both, and Python always imports the package: after a
rollback the older app would silently run against the newer code. The packages refuse to load
next to the single file unless the running script carries the marker of a version with the
packages, and the .bat files of the newer version delete the leftover single files of an update.
"""
import ast
import re
import shutil
import subprocess
import sys
import types
from pathlib import Path

import pytest

from framescout_core import (CORE_PACKAGE, LAYOUT_MARKER, OBSOLETE_CORE_FILE, REPLACED_PACKAGES, SCORING_PACKAGE,
                             check_program_files, mixed_versions_message, refused_import)
from framescout_scoring import layout as scoring_layout

ROOT = Path(__file__).resolve().parent.parent
windows_only = pytest.mark.skipif(sys.platform != 'win32', reason='runs a .bat file')
# the scripts that are run (they set the marker) and the modules only imported by them
ENTRY_POINTS = ('app.py', 'framescout_engine.py', 'framescout_eval.py', 'install_torch.py', 'framescout_check.py',
                'framescout_uninstall.py')
# added after I15 (E49), so no older version next to the single file has it
LIBRARY_MODULES = ('framescout_images.py',)
OBSOLETE_SCORING_FILE = f'{SCORING_PACKAGE}.py'


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


MARKER_LINE = f'{LAYOUT_MARKER} = True\n'


def run_script(folder, name, marked=False):
    (folder / name).write_text((MARKER_LINE if marked else '') + 'import framescout_core\nprint("LOADED")\n',
                               encoding='utf-8')
    return subprocess.run([sys.executable, '-B', name], cwd=folder, capture_output=True, text=True,
                          encoding='utf-8', errors='replace')


def mixed_folder(tmp_path):
    folder = tmp_path / 'Fo!to (old) & co'
    folder.mkdir()
    copy_of_the_package(folder)
    (folder / OBSOLETE_CORE_FILE).write_text("raise SystemExit('the single file was imported')\n", encoding='utf-8')
    return folder


@pytest.mark.parametrize('name', ENTRY_POINTS)
def test_an_entry_point_with_the_marker_runs_next_to_the_single_file(tmp_path, name):
    # I35: a ZIP of this version extracted over a folder before I15: the newer entry points
    # work before Install-FrameScout.bat or Start-FrameScout.bat deleted the leftover
    folder = mixed_folder(tmp_path)
    result = run_script(folder, name, marked=True)
    assert 'LOADED' in result.stdout, result.stderr


@pytest.mark.parametrize('name', ['app.py', 'framescout_engine.py', 'install_torch.py'])
def test_an_entry_point_without_the_marker_is_refused_next_to_the_single_file(tmp_path, name):
    # an older version's script (these three existed before I15) must not run against this core
    folder = mixed_folder(tmp_path)
    result = run_script(folder, name)
    assert 'LOADED' not in result.stdout and 'ImportError' in result.stderr
    assert 'the single file was imported' not in result.stderr + result.stdout


def test_the_app_with_the_marker_runs_next_to_the_single_file_under_streamlit(tmp_path):
    # Streamlit runs app.py as a new module __main__ with the script's __file__ (its
    # ScriptRunner); the marker is a global of that module
    folder = mixed_folder(tmp_path)
    for marked, loaded in ((True, True), (False, False)):
        (folder / 'app.py').write_text((MARKER_LINE if marked else '') + 'import framescout_core\nprint("LOADED")\n',
                                       encoding='utf-8')
        runner = ('import os, sys, types\n'
                  'sys.path.insert(0, os.path.dirname(sys.argv[1]))\n'
                  'module = types.ModuleType("__main__")\n'
                  'module.__file__ = sys.argv[1]\n'
                  'sys.modules["__main__"] = module\n'
                  'code = compile(open(sys.argv[1], encoding="utf-8").read(), sys.argv[1], "exec")\n'
                  'exec(code, module.__dict__)\n')
        (tmp_path / 'runner.py').write_text(runner, encoding='utf-8')
        result = subprocess.run([sys.executable, '-B', str(tmp_path / 'runner.py'), str(folder / 'app.py')],
                                cwd=folder, capture_output=True, text=True, encoding='utf-8', errors='replace')
        assert ('LOADED' in result.stdout) is loaded, result.stderr


def test_only_a_marked_script_of_the_same_folder_may_load_next_to_the_single_file(tmp_path):
    (tmp_path / OBSOLETE_CORE_FILE).write_text('', encoding='utf-8')
    problem = mixed_versions_message(tmp_path)

    def main(path, **globals_):
        return types.SimpleNamespace(__file__=path, **globals_) if path else types.SimpleNamespace(**globals_)
    assert refused_import(tmp_path, main(str(tmp_path / 'framescout_engine.py'), **{LAYOUT_MARKER: True})) is None
    for main_module in (main(str(tmp_path / 'app.py')),
                        main(str(tmp_path / 'other' / 'app.py'), **{LAYOUT_MARKER: True}),
                        main(str(tmp_path / 'app.py'), **{LAYOUT_MARKER: 'yes'}),
                        main(None, **{LAYOUT_MARKER: True}), None):
        assert refused_import(tmp_path, main_module) == problem, main_module


def module_names(path):
    """The top-level modules a script imports (import, from-import and import_module('<name>'))."""
    tree = ast.parse(path.read_text(encoding='utf-8'))
    names = {alias.name.split('.')[0] for node in ast.walk(tree) if isinstance(node, ast.Import)
             for alias in node.names}
    names |= {node.module.split('.')[0] for node in ast.walk(tree)
              if isinstance(node, ast.ImportFrom) and node.module and not node.level}
    names |= {node.args[0].value.split('.')[0] for node in ast.walk(tree)
              if isinstance(node, ast.Call) and getattr(node.func, 'attr', getattr(node.func, 'id', None)) == 'import_module'
              and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)}
    return names


def test_every_script_that_imports_framescout_is_an_entry_point_or_a_library():
    # a new script must set the marker, or it stops next to an update's leftover (I35)
    importing = {path.name for path in ROOT.glob('*.py')
                 if any(name.startswith('framescout') for name in module_names(path))}
    assert importing == set(ENTRY_POINTS) | set(LIBRARY_MODULES)


@pytest.mark.parametrize('name', ENTRY_POINTS)
def test_every_entry_point_sets_the_marker_before_its_first_framescout_import(name):
    body = ast.parse((ROOT / name).read_text(encoding='utf-8')).body
    first_import = next(i for i, node in enumerate(body)
                        if isinstance(node, (ast.Import, ast.ImportFrom))
                        and any(module.startswith('framescout') for module in module_names_of(node)))
    marker = [i for i, node in enumerate(body) if isinstance(node, ast.Assign)
              and [getattr(target, 'id', None) for target in node.targets] == [LAYOUT_MARKER]
              and isinstance(node.value, ast.Constant) and node.value.value is True]
    assert marker and marker[0] < first_import, name


def module_names_of(node):
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    return [node.module or '']


@pytest.mark.parametrize('name', ENTRY_POINTS)
def test_the_entry_points_import_no_module_an_older_version_has_as_a_single_file(name):
    # After going back to a version before I15, the entry points that version lacks (the
    # check, the uninstall, the evaluation tool) stay as this version's and load this core:
    # they may only import modules that are this version's too, i.e. the two packages (each
    # with its guard) and modules no version before I15 had. An older version's module
    # (e.g. the engine) would be the older one's.
    framescout = {module for module in module_names(ROOT / name) if module.startswith('framescout')}
    assert framescout <= set(REPLACED_PACKAGES) | {Path(module).stem for module in LIBRARY_MODULES}, name


# --- framescout_scoring next to framescout_scoring.py (I36) ---

def copy_of_the_scoring_package(folder):
    shutil.copytree(ROOT / 'framescout_scoring', folder / 'framescout_scoring',
                    ignore=shutil.ignore_patterns('__pycache__'))


def import_scoring(folder, name, marked):
    (folder / name).write_text((MARKER_LINE if marked else '') + 'import framescout_scoring\n'
                               'print(framescout_scoring.__file__)\n', encoding='utf-8')
    return subprocess.run([sys.executable, '-B', name], cwd=folder, capture_output=True, text=True,
                          encoding='utf-8', errors='replace')


def test_the_scoring_package_wins_over_its_leftover_single_file_for_a_marked_script(tmp_path):
    # I30: a newer ZIP over a version with framescout_scoring.py leaves that file unused, since
    # Python imports the package of the same folder
    copy_of_the_scoring_package(tmp_path)
    (tmp_path / 'framescout_scoring.py').write_text("raise SystemExit('the single file was imported')\n",
                                                    encoding='utf-8')
    result = import_scoring(tmp_path, 'framescout_engine.py', marked=True)
    assert result.returncode == 0, result.stderr
    assert Path(result.stdout.strip()).resolve() == (tmp_path / 'framescout_scoring' / '__init__.py').resolve()


def test_the_scoring_package_refuses_an_older_script_next_to_its_single_file(tmp_path):
    # I36: an older ZIP (with framescout_scoring.py) over a newer folder: the older engine
    # would silently score with the newer package
    folder = tmp_path / 'Fo!to (old) & co'
    folder.mkdir()
    copy_of_the_scoring_package(folder)
    (folder / 'framescout_scoring.py').write_text("raise SystemExit('the single file was imported')\n",
                                                  encoding='utf-8')
    result = import_scoring(folder, 'framescout_engine.py', marked=False)
    assert result.returncode == 1
    assert 'ImportError' in result.stderr and 'delete the folder framescout_scoring' in result.stderr
    assert 'the single file was imported' not in result.stderr + result.stdout


def test_the_scoring_package_loads_without_its_single_file(tmp_path):
    copy_of_the_scoring_package(tmp_path)
    assert import_scoring(tmp_path, 'framescout_engine.py', marked=False).returncode == 0


def test_the_scoring_guard_says_what_the_core_guard_says(tmp_path):
    # written out in framescout_scoring, which must not import framescout_core (that may be an
    # older version's after going back)
    assert scoring_layout.LAYOUT_MARKER == LAYOUT_MARKER
    assert scoring_layout.PACKAGE == SCORING_PACKAGE
    assert scoring_layout.scoring_leftover_message(tmp_path) is None
    (tmp_path / 'framescout_scoring.py').write_text('', encoding='utf-8')
    assert scoring_layout.scoring_leftover_message(tmp_path) == mixed_versions_message(tmp_path, SCORING_PACKAGE)
    for main_module in (types.SimpleNamespace(__file__=str(tmp_path / 'framescout_engine.py'), **{LAYOUT_MARKER: True}),
                        types.SimpleNamespace(__file__=str(tmp_path / 'framescout_engine.py')),
                        types.SimpleNamespace(__file__=str(tmp_path / 'x' / 'app.py'), **{LAYOUT_MARKER: True}),
                        None):
        assert (scoring_layout.scoring_import_refused(tmp_path, main_module)
                == refused_import(tmp_path, main_module, SCORING_PACKAGE)), main_module


def test_the_scoring_package_imports_no_framescout_module():
    for path in (ROOT / 'framescout_scoring').glob('*.py'):
        assert not any(name.startswith('framescout') for name in module_names(path)), path.name


# --- the .bat files of this version delete the leftovers of an update ---

# each replaced single file and the label its cleanup in the .bat files jumps to
LEFTOVERS = {CORE_PACKAGE: 'obsolete_done', SCORING_PACKAGE: 'obsolete_scoring_done'}
leftovers = pytest.mark.parametrize('package', sorted(LEFTOVERS))


def cleanup_commands(name, package=CORE_PACKAGE):
    """All commands, the index of the first cleanup command and the cleanup lines with echo."""
    single_file, label = f'{package}.py', LEFTOVERS[package]
    text = (ROOT / name).read_text(encoding='utf-8')
    commands = batch_commands(text)
    first = next(i for i, line in enumerate(commands) if single_file in line)
    lines = [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith('rem ')]
    start = next(i for i, line in enumerate(lines) if single_file in line)
    return commands, first, lines[start:lines.index(f':{label}', start)]


def test_the_cleanups_cover_every_replaced_single_file():
    assert set(LEFTOVERS) == set(REPLACED_PACKAGES)


@leftovers
def test_install_and_start_delete_the_single_file_the_same_way(package):
    single_file, label = f'{package}.py', LEFTOVERS[package]
    _, _, start = cleanup_commands('Start-FrameScout.bat', package)
    _, _, install = cleanup_commands('Install-FrameScout.bat', package)
    assert start == install
    # only next to the package: the folder of an older version keeps its single file
    assert any(f'{package}\\__init__.py' in line for line in start)
    assert sum(line.startswith('del ') for line in start) == 1
    # a directory of that name is no leftover: del would ask and delete the files in it (review)
    directory = start.index(f'if exist "{single_file}\\*" goto {label}')
    assert directory < next(i for i, line in enumerate(start) if line.startswith('del '))
    # a read-only file is deleted too, and a file that stays stops the .bat (review)
    deletion = start.index(f'del /f "{single_file}"')
    assert start[deletion + 1] == f'if not exist "{single_file}" goto {label}'
    assert start[-2:] == ['pause', 'exit /b 1']


def test_the_scoring_cleanup_is_the_core_cleanup_for_its_file():
    for name in ('Start-FrameScout.bat', 'Install-FrameScout.bat'):
        _, _, core = cleanup_commands(name, CORE_PACKAGE)
        _, _, scoring = cleanup_commands(name, SCORING_PACKAGE)
        assert [line.replace(CORE_PACKAGE, SCORING_PACKAGE).replace(':obsolete_done', ':obsolete_scoring_done')
                .replace('goto obsolete_done', 'goto obsolete_scoring_done') for line in core] == scoring, name


@leftovers
def test_the_uninstaller_does_not_delete_the_single_file(package):
    # after going back to an older version (before I15 without an uninstaller), this version's
    # Uninstall-FrameScout.bat stays in the folder, and the single file is that version's
    text = (ROOT / 'Uninstall-FrameScout.bat').read_text(encoding='utf-8')
    assert not any(f'{package}.py' in line for line in batch_commands(text))


@leftovers
def test_the_single_file_is_deleted_before_python_runs(package):
    for name in ('Start-FrameScout.bat', 'Install-FrameScout.bat'):
        commands, first, _ = cleanup_commands(name, package)
        python = next(i for i, line in enumerate(commands) if 'python.exe' in line)
        assert first < python, name


@leftovers
def test_the_cleanup_keeps_exclamation_marks_and_stays_out_of_blocks(package):
    # no delayed expansion, and no "(" block a ")" of the folder path could end
    for name in ('Start-FrameScout.bat', 'Install-FrameScout.bat'):
        _, _, cleanup = cleanup_commands(name, package)
        assert not any('!' in line or '(' in line for line in cleanup), name


def run_start(folder):
    shutil.copy(ROOT / 'Start-FrameScout.bat', folder)
    # relative to the current directory (cmd may not search it), so no quoting of the
    # folder path is needed; %~dp0 is still the full path
    return subprocess.run(['cmd.exe', '/d', '/c', '.\\Start-FrameScout.bat'], cwd=folder, input='\n\n',
                          capture_output=True, text=True, errors='replace')


def folder_with_the_package(folder, package=CORE_PACKAGE):
    (folder / package).mkdir(parents=True)
    (folder / package / '__init__.py').write_text('', encoding='utf-8')
    return folder


@windows_only
@leftovers
def test_start_deletes_the_single_file_next_to_the_package(tmp_path, package):
    single_file = f'{package}.py'
    folder = folder_with_the_package(tmp_path / 'Fo!to (old) & co', package)
    (folder / single_file).write_text('', encoding='utf-8')
    result = run_start(folder)
    assert not (folder / single_file).exists()
    assert (folder / package / '__init__.py').exists()
    assert f'Deleting {single_file}' in result.stdout
    # no .venv here: the start stops as before
    assert 'run Install-FrameScout.bat first' in result.stdout and result.returncode == 1


@windows_only
def test_start_deletes_both_single_files(tmp_path):
    folder = tmp_path
    for package in REPLACED_PACKAGES:
        folder_with_the_package(folder, package)
        (folder / f'{package}.py').write_text('', encoding='utf-8')
    result = run_start(folder)
    assert not any((folder / f'{package}.py').exists() for package in REPLACED_PACKAGES), result.stdout
    assert 'run Install-FrameScout.bat first' in result.stdout


@windows_only
@leftovers
def test_start_keeps_the_single_file_without_the_package(tmp_path, package):
    single_file = f'{package}.py'
    (tmp_path / single_file).write_text('', encoding='utf-8')
    result = run_start(tmp_path)
    assert (tmp_path / single_file).exists()
    assert single_file not in result.stdout


@windows_only
@leftovers
@pytest.mark.parametrize('content', [None, 'kept.txt'])
def test_start_keeps_a_folder_named_like_the_single_file(tmp_path, package, content):
    # del "framescout_core.py" would ask and then delete the files in such a folder (review)
    single_file = f'{package}.py'
    folder = folder_with_the_package(tmp_path, package)
    (folder / single_file).mkdir()
    if content:
        (folder / single_file / content).write_text('x', encoding='utf-8')
    result = run_start(folder)
    assert (folder / single_file).is_dir()
    assert content is None or (folder / single_file / content).exists()
    assert 'Deleting' not in result.stdout and 'run Install-FrameScout.bat first' in result.stdout


@windows_only
@leftovers
def test_start_deletes_a_read_only_single_file(tmp_path, package):
    import stat
    single_file = f'{package}.py'
    folder = folder_with_the_package(tmp_path, package)
    (folder / single_file).write_text('', encoding='utf-8')
    (folder / single_file).chmod(stat.S_IREAD)
    result = run_start(folder)
    assert not (folder / single_file).exists(), result.stdout + result.stderr
    assert 'run Install-FrameScout.bat first' in result.stdout


@windows_only
@leftovers
def test_start_stops_when_the_single_file_cannot_be_deleted(tmp_path, package):
    single_file = f'{package}.py'
    folder = folder_with_the_package(tmp_path, package)
    # Python opens files without delete sharing on Windows: like a file open in an editor
    with open(folder / single_file, 'w', encoding='utf-8'):
        result = run_start(folder)
    assert (folder / single_file).exists()
    assert f'{single_file} could not be deleted' in result.stdout and result.returncode == 1
    # it stops before it looks for the environment
    assert 'run Install-FrameScout.bat first' not in result.stdout


# --- the check reports the leftovers instead of a traceback (I34) ---

@leftovers
def test_the_check_reports_a_single_file_next_to_its_package(tmp_path, package):
    folder_with_the_package(tmp_path, package)
    [fine] = check_program_files(tmp_path)
    assert fine.ok is True
    (tmp_path / f'{package}.py').write_text('', encoding='utf-8')
    [problem] = check_program_files(tmp_path)
    assert problem.ok is False and f'{package}.py next to the folder {package}' in problem.text
    assert f'delete {package}.py' in problem.fix and f'delete the folder {package}' in problem.fix


def test_the_check_reports_both_single_files_and_ignores_other_cases(tmp_path):
    for package in REPLACED_PACKAGES:
        folder_with_the_package(tmp_path, package)
        (tmp_path / f'{package}.py').write_text('', encoding='utf-8')
    assert [result.ok for result in check_program_files(tmp_path)] == [False, False]
    # a folder named like the file, or the file without its package, is no leftover
    other = tmp_path / 'other'
    folder_with_the_package(other, CORE_PACKAGE)
    (other / OBSOLETE_CORE_FILE).mkdir()
    (other / OBSOLETE_SCORING_FILE).write_text('', encoding='utf-8')
    assert [result.ok for result in check_program_files(other)] == [True]


def test_check_bat_shows_a_check_line_instead_of_a_traceback_next_to_the_single_file(tmp_path):
    # I34: the check of this version runs next to the leftover and names it as a problem
    folder = mixed_folder(tmp_path)
    shutil.copy(ROOT / 'framescout_check.py', folder)
    result = subprocess.run([sys.executable, '-B', '-E', '-s', 'framescout_check.py'], cwd=folder,
                            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120)
    assert 'Traceback' not in result.stderr, result.stderr
    assert result.returncode == 2
    assert f'[PROBLEM] Program files: The FrameScout folder holds {OBSOLETE_CORE_FILE}' in result.stdout
