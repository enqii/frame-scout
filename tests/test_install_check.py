"""The "Check installation" self-test (F15): read-only checks with fake folders, metadata and processes."""
import json
import os
import subprocess
from collections import namedtuple
from pathlib import Path

import pytest

import framescout_core
from framescout_core import install_check
from framescout_core.install_check import (CheckResult, check_disk_space, check_environment, check_installation,
                                           check_lines, check_models, check_packages, check_torch, check_writable,
                                           installed_versions, requirement_names, venv_python, venv_site_packages)

ROOT = Path(__file__).resolve().parent.parent
Usage = namedtuple('Usage', 'total used free')


def make_venv(base, home, version='3.14.9'):
    """A .venv in base whose pyvenv.cfg names home, with an empty python.exe (or bin/python)."""
    python = venv_python(base)
    python.parent.mkdir(parents=True)
    python.write_bytes(b'')
    (base / '.venv' / 'pyvenv.cfg').write_text(f'home = {home}\ninclude-system-site-packages = false\n'
                                               f'version = {version}\n', encoding='utf-8')
    return python


def make_python(folder):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'python.exe').write_bytes(b'')
    return folder


def dist(site, name, version):
    """Fake metadata of an installed package, as pip writes it."""
    info = site / f'{name.replace("-", "_")}-{version}.dist-info'
    info.mkdir(parents=True)
    (info / 'METADATA').write_text(f'Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n', encoding='utf-8')


def problems(results):
    return [r for r in results if r.ok is False]


# --- Python environment ---------------------------------------------------------------

def test_environment_of_this_folder_with_its_private_python_is_fine(tmp_path):
    make_venv(tmp_path, make_python(tmp_path / '.python'))
    [result] = check_environment(tmp_path)
    assert result.ok is True and result.fix == ''


def test_environment_of_an_older_installer_with_an_installed_python_is_fine(tmp_path):
    make_venv(tmp_path, make_python(tmp_path.parent / 'installed' / 'Python314'))
    [result] = check_environment(tmp_path)
    assert result.ok is True
    assert 'installed Python' in result.text


def test_missing_environment_says_to_run_the_installer(tmp_path):
    [result] = check_environment(tmp_path)
    assert result.ok is False
    assert 'Install-FrameScout.bat' in result.fix


def test_environment_whose_python_is_gone_names_a_moved_folder(tmp_path):
    # the folder was moved: pyvenv.cfg still names the .python of the old place
    make_venv(tmp_path, tmp_path.parent / 'old-place' / '.python')
    [result] = check_environment(tmp_path)
    assert result.ok is False
    assert 'moved' in result.text
    assert 'Install-FrameScout.bat' in result.fix


def test_environment_using_the_private_python_of_another_folder_is_a_problem(tmp_path):
    # the folder was copied: .venv still works, but with the .python of the original folder
    base = tmp_path / 'copy'
    base.mkdir()
    make_python(base / '.python')
    make_venv(base, make_python(tmp_path / 'original' / '.python'))
    [result] = check_environment(base)
    assert result.ok is False
    assert str(tmp_path / 'original' / '.python') in result.text
    assert '.venv' in result.fix and 'Install-FrameScout.bat' in result.fix


def link_folder(link, target):
    """A directory symlink, or on Windows without that privilege a junction; skip if neither can be made."""
    try:
        os.symlink(target, link, target_is_directory=True)
    except OSError:
        try:
            import _winapi
            _winapi.CreateJunction(str(target), str(link))
        except (ImportError, OSError):
            pytest.skip('cannot create a symlink or junction here')


def test_environment_created_through_a_link_to_this_folder_is_fine(tmp_path):
    # framescout_check.py passes the resolved folder; pyvenv.cfg names the path the installer
    # ran from, here a link to the same folder: not "another folder" (review)
    base = tmp_path / 'real'
    make_python(base / '.python')
    link_folder(tmp_path / 'link', base)
    make_venv(base, tmp_path / 'link' / '.python')
    [result] = check_environment(base)
    assert result.ok is True


def test_environment_with_an_unreadable_pyvenv_cfg_is_a_problem(tmp_path):
    make_venv(tmp_path, make_python(tmp_path / '.python'))
    (tmp_path / '.venv' / 'pyvenv.cfg').unlink()
    [result] = check_environment(tmp_path)
    assert result.ok is False


# --- package versions -------------------------------------------------------------------

CONSTRAINTS = '# comment\nnumpy==2.5.4\npillow==12.3.0\ntorch==2.14.1\ntorchvision==0.29.1\nnot-needed==1.0\n'
REQUIREMENTS = 'torch==2.14.1\ntorchvision==0.29.1\nnumpy>=2\npillow>=12 ; python_version>"3"\n'


def test_installed_versions_reads_the_metadata_of_a_folder(tmp_path):
    dist(tmp_path, 'Pillow', '12.3.0')
    dist(tmp_path, 'open_clip_torch', '3.3.0')
    assert installed_versions(tmp_path) == {'pillow': '12.3.0', 'open-clip-torch': '3.3.0'}


def test_installed_versions_of_a_missing_folder_is_empty(tmp_path):
    assert installed_versions(tmp_path / 'missing') == {}


def test_packages_matching_the_constraints_are_fine(tmp_path):
    for name, version in [('numpy', '2.5.4'), ('Pillow', '12.3.0'), ('torch', '2.14.1+cu130'),
                          ('torchvision', '0.29.1+cu130')]:
        dist(tmp_path, name, version)
    # a pin of a package that is not needed here ("not-needed") is no problem
    [result] = check_packages(tmp_path, CONSTRAINTS, REQUIREMENTS)
    assert result.ok is True


def test_plain_torch_version_of_pypi_counts_as_the_pin(tmp_path):
    for name, version in [('numpy', '2.5.4'), ('pillow', '12.3.0'), ('torch', '2.14.1'), ('torchvision', '0.29.1')]:
        dist(tmp_path, name, version)
    assert check_packages(tmp_path, CONSTRAINTS, REQUIREMENTS)[0].ok is True


def test_other_versions_and_missing_packages_are_named(tmp_path):
    dist(tmp_path, 'numpy', '2.6.0')
    dist(tmp_path, 'torch', '2.13.0+cpu')
    dist(tmp_path, 'torchvision', '0.29.1+cpu')
    [result] = check_packages(tmp_path, CONSTRAINTS, REQUIREMENTS)
    assert result.ok is False
    assert 'numpy 2.6.0 instead of 2.5.4' in result.text
    assert 'torch 2.13.0+cpu instead of 2.14.1' in result.text
    assert 'pillow' in result.text and 'missing' in result.text
    assert 'Install-FrameScout.bat' in result.fix


def test_requirement_names_skip_comments_markers_and_extras():
    assert requirement_names('# comment\n\nnumpy>=2 ; python_version>"3"\nfoo[bar]==1\n') == ['numpy', 'foo']


def test_the_real_constraints_and_requirements_can_be_read(tmp_path):
    constraints = (ROOT / 'constraints.txt').read_text(encoding='utf-8')
    requirements = (ROOT / 'requirements.txt').read_text(encoding='utf-8')
    [result] = check_packages(tmp_path, constraints, requirements)
    # nothing installed in tmp_path: every requirement is missing
    assert result.ok is False
    assert 'torch' in result.text and 'streamlit' in result.text


# --- PyTorch ------------------------------------------------------------------------------

def fake_run(stdout='', returncode=0, stderr='', raises=None, calls=None):
    def run(command, **kwargs):
        if calls is not None:
            calls.append((command, kwargs))
        if raises:
            raise raises
        return subprocess.CompletedProcess(command, returncode, stdout, stderr)
    return run


def probe(available, cuda='13.0', gpu='NVIDIA GeForce RTX 4070', torch='2.14.1+cu130'):
    return 'some warning\n' + json.dumps({'torch': torch, 'cuda': cuda, 'available': available,
                                          'gpu': gpu if available else None}) + '\n'


def test_torch_runs_in_a_subprocess_of_the_environment_without_writing(tmp_path):
    calls = []
    python = tmp_path / 'python.exe'
    [result] = check_torch(python, {'X': '1'}, '2.14.1+cpu', run=fake_run(probe(False, None, torch='2.14.1+cpu'),
                                                                           calls=calls))
    assert result.ok is True and 'CPU' in result.text
    [(command, kwargs)] = calls
    assert command[0] == str(python)
    assert '-B' in command  # no compiled files are written
    assert kwargs['env'] == {'X': '1'} and kwargs['timeout'] == install_check.TORCH_CHECK_TIMEOUT


def test_cuda_build_that_finds_the_gpu_is_fine_and_names_it(tmp_path):
    [result] = check_torch(tmp_path / 'python.exe', {}, '2.14.1+cu130', run=fake_run(probe(True)))
    assert result.ok is True
    assert 'NVIDIA GeForce RTX 4070' in result.text


def test_cuda_build_without_a_usable_gpu_is_a_problem(tmp_path):
    [result] = check_torch(tmp_path / 'python.exe', {}, '2.14.1+cu130', run=fake_run(probe(False)))
    assert result.ok is False
    assert 'driver' in result.fix


@pytest.mark.parametrize('run', [fake_run(returncode=1, stderr='Traceback ...\nOSError: [WinError 126] c10.dll\n'),
                                 fake_run(returncode=3221225477),
                                 fake_run('not json\n'),
                                 fake_run(raises=subprocess.TimeoutExpired('python', 1)),
                                 fake_run(raises=OSError('cannot start'))])
def test_torch_that_does_not_import_is_a_problem(tmp_path, run):
    [result] = check_torch(tmp_path / 'python.exe', {}, '2.14.1+cpu', run=run)
    assert result.ok is False
    assert 'Install-FrameScout.bat' in result.fix


def test_import_error_names_the_last_line_of_the_traceback(tmp_path):
    run = fake_run(returncode=1, stderr='Traceback ...\nOSError: [WinError 126] c10.dll\n')
    [result] = check_torch(tmp_path / 'python.exe', {}, '2.14.1+cpu', run=run)
    assert 'OSError: [WinError 126] c10.dll' in result.text


def test_torch_not_installed_is_not_imported(tmp_path):
    calls = []
    [result] = check_torch(tmp_path / 'python.exe', {}, None, run=fake_run(calls=calls))
    assert result.ok is False and calls == []


# --- writable folders -------------------------------------------------------------------

def test_writable_folder_is_fine_and_left_as_it_was(tmp_path):
    (tmp_path / 'results').mkdir()
    [result] = check_writable(tmp_path / 'results', 'results')
    assert result.ok is True
    assert list((tmp_path / 'results').iterdir()) == []


def test_missing_folder_is_checked_on_its_parent_and_not_created(tmp_path):
    [result] = check_writable(tmp_path / '.cache', '.cache')
    assert result.ok is True
    assert not (tmp_path / '.cache').exists()
    assert list(tmp_path.iterdir()) == []


def test_folder_that_cannot_be_written_is_a_problem(tmp_path, monkeypatch):
    def refuse(**kwargs):
        raise PermissionError('Access is denied')
    monkeypatch.setattr(install_check.tempfile, 'TemporaryFile', refuse)
    [result] = check_writable(tmp_path, 'results')
    assert result.ok is False
    assert 'Access is denied' in result.text and result.fix


# --- model weights and disk space -----------------------------------------------------------

def test_models_lists_what_is_downloaded_as_information(tmp_path, monkeypatch):
    key = framescout_core.DEFAULT_MODEL
    monkeypatch.setattr(install_check, 'downloaded_models', lambda base, environ: {key})
    [result] = check_models(tmp_path, {})
    assert result.ok is None
    assert framescout_core.MODELS[key].label in result.text
    assert 'person detection' in result.text and 'Not downloaded yet' in result.text


def test_models_names_cached_person_detector(tmp_path, monkeypatch):
    monkeypatch.setattr(install_check, 'downloaded_models', lambda base, environ: set())
    weights = tmp_path / '.cache' / 'ultralytics' / framescout_core.DEFAULT_YOLO_MODEL
    weights.parent.mkdir(parents=True)
    weights.write_bytes(b'')
    [result] = check_models(tmp_path, {})
    assert 'Downloaded: person detection' in result.text


def test_enough_disk_space_is_fine(tmp_path):
    [result] = check_disk_space(tmp_path, disk_usage=lambda path: Usage(100 * 2 ** 30, 50 * 2 ** 30, 50 * 2 ** 30))
    assert result.ok is True and '50.0 GB' in result.text


def test_little_disk_space_is_a_problem(tmp_path):
    [result] = check_disk_space(tmp_path, disk_usage=lambda path: Usage(100 * 2 ** 30, 100 * 2 ** 30, 2 ** 20))
    assert result.ok is False and result.fix


# --- the whole check --------------------------------------------------------------------------

def test_check_installation_runs_every_check_and_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(install_check, 'downloaded_models', lambda base, environ: set())
    make_venv(tmp_path, make_python(tmp_path / '.python'))
    site = venv_site_packages(tmp_path)
    site.mkdir(parents=True)
    dist(site, 'torch', '2.14.1+cpu')
    (tmp_path / 'constraints.txt').write_text('torch==2.14.1\n', encoding='utf-8')
    (tmp_path / 'requirements.txt').write_text('torch==2.14.1\n', encoding='utf-8')
    before = sorted(p for p in tmp_path.rglob('*'))
    calls = []
    results = check_installation(tmp_path, {'PATH': 'x'}, run=fake_run(probe(False, None, torch='2.14.1+cpu'),
                                                                        calls=calls))
    assert [r.name for r in results] == ['Python environment', 'Packages', 'PyTorch', 'Cache folder (.cache)',
                                         'Results folder (results)', 'Model files', 'Free disk space']
    assert problems(results) == []
    assert sorted(p for p in tmp_path.rglob('*')) == before
    # the engine's cache variables point into the folder, a value of the user is overridden as the app does
    env = calls[0][1]['env']
    assert env['PATH'] == 'x' and env['HF_HOME'] == str(tmp_path / '.cache' / 'huggingface')


def test_check_installation_skips_pytorch_without_an_environment(tmp_path, monkeypatch):
    monkeypatch.setattr(install_check, 'downloaded_models', lambda base, environ: set())
    calls = []
    results = check_installation(tmp_path, {}, run=fake_run(calls=calls))
    assert calls == []
    # one problem, the environment; the packages and PyTorch are not checked
    assert [r.name for r in problems(results)] == ['Python environment']
    assert {r.name: r.ok for r in results}['Packages'] is None
    assert {r.name: r.ok for r in results}['PyTorch'] is None


def test_check_installation_does_not_import_pytorch_of_an_environment_of_another_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(install_check, 'downloaded_models', lambda base, environ: set())
    base = tmp_path / 'copy'
    make_venv(base, make_python(tmp_path / 'original' / '.python'))
    calls = []
    results = check_installation(base, {}, run=fake_run(calls=calls))
    assert calls == []
    assert {r.name: r.ok for r in results}['Packages'] is True  # checked: .venv has a Python
    assert {r.name: r.ok for r in results}['PyTorch'] is None


def test_check_lines_give_status_text_and_fix():
    lines = check_lines([CheckResult('A', True, 'fine', ''), CheckResult('B', False, 'broken', 'Do this.'),
                         CheckResult('C', None, 'note', '')])
    assert lines == ['[OK]      A: fine', '[PROBLEM] B: broken', '          Fix: Do this.', '[INFO]    C: note']


def test_check_script_prints_the_results_and_exits_2_on_a_problem(monkeypatch, capsys):
    # exit code 1 is Python's own for an uncaught exception: Check-FrameScout.bat tells the
    # two apart (review)
    import framescout_check
    monkeypatch.setattr(framescout_check, 'check_installation',
                        lambda base, environ: [CheckResult('A', True, 'fine', ''),
                                               CheckResult('B', False, 'broken', 'Do this.')])
    assert framescout_check.main([]) == framescout_check.PROBLEMS_FOUND == 2
    out = capsys.readouterr().out
    assert '[PROBLEM] B: broken' in out and '1 problem' in out
    monkeypatch.setattr(framescout_check, 'check_installation',
                        lambda base, environ: [CheckResult('A', True, 'fine', '')])
    assert framescout_check.main([]) == 0
    assert 'No problems found' in capsys.readouterr().out


def test_check_script_prints_characters_the_output_encoding_lacks(monkeypatch):
    # redirected output on Windows uses the ANSI code page: a folder name outside it must
    # not end the check with a UnicodeEncodeError (review)
    import io
    import framescout_check
    buffer = io.BytesIO()
    monkeypatch.setattr(framescout_check.sys, 'stdout', io.TextIOWrapper(buffer, encoding='cp1252'))
    monkeypatch.setattr(framescout_check, 'check_installation',
                        lambda base, environ: [CheckResult('A', False, 'C:\\写真 cannot be written', 'Do this.')])
    assert framescout_check.main([]) != 0
    framescout_check.sys.stdout.flush()
    assert b'[PROBLEM] A: C:\\?? cannot be written' in buffer.getvalue()


def test_check_bat_runs_the_check_script_without_writing_compiled_files():
    text = (ROOT / 'Check-FrameScout.bat').read_text(encoding='utf-8')
    assert 'framescout_check.py' in text and '-B' in text
    assert 'setlocal enabledelayedexpansion' not in text.lower()
    assert all(ord(c) < 128 for c in text)
    # a check that could not run (any exit code but 0 and PROBLEMS_FOUND) falls back to the
    # private Python and then names the installer (review)
    assert text.count('"%errorlevel%"=="2"') == 2 and 'goto failed' in text and ':failed' in text
