"""Install-FrameScout.bat (P5 part C, I21): the private Python of new installations.

The .bat is checked as text; nothing is downloaded or run.
"""
import re
from pathlib import Path

from framescout_core import PRIVATE_PYTHON, PYTHON_SHA256, PYTHON_URL, PYTHON_VERSION

ROOT = Path(__file__).resolve().parent.parent


def installer():
    return (ROOT / 'Install-FrameScout.bat').read_text(encoding='utf-8')


def batch_commands(text):
    lines = (line.strip() for line in text.splitlines())
    return [line for line in lines if line and not re.match(r'(?i)(rem\b|::|echo\b|:)', line)]


def block_lines(text):
    """Lines inside a parenthesized block that spans lines (an if or for body)."""
    inside, depth = [], 0
    for line in batch_commands(text):
        if depth and not line.startswith(')'):
            inside.append(line)
        depth += line.count('(') - line.count(')') if line.endswith('(') or line.startswith(')') else 0
    return inside


def setting(name):
    match = re.search(rf'^set "{name}=([^"]*)"$', installer(), re.MULTILINE)
    assert match, name
    return match.group(1)


def index(commands, pattern):
    found = [i for i, line in enumerate(commands) if re.search(pattern, line)]
    assert len(found) == 1, (pattern, found)
    return found[0]


def test_the_installer_pins_the_python_of_framescout_core():
    assert setting('PYTHON_VERSION') == PYTHON_VERSION
    assert setting('PYTHON_URL') == PYTHON_URL
    assert setting('PYTHON_SHA256') == PYTHON_SHA256


def test_the_pinned_python_is_the_full_package_of_python_org():
    # the full package has venv and ensurepip, the embeddable one has neither
    assert PYTHON_URL == f'https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-amd64.zip'
    assert re.fullmatch(r'[0-9a-f]{64}', PYTHON_SHA256)
    assert PYTHON_VERSION.startswith('3.14.')


def test_the_installer_needs_no_installed_python():
    commands = batch_commands(installer())
    assert not any(re.match(r'(?i)py(\.exe)?\s', line) for line in commands)


def test_the_download_is_checked_before_it_is_extracted_and_used():
    commands = batch_commands(installer())
    order = [index(commands, r'^curl\.exe .*"%PYTHON_URL%"'),
             index(commands, r'^powershell\.exe .*Get-FileHash .*\$env:PYTHON_ZIP.*\$env:PYTHON_SHA256'),
             index(commands, r'^tar\.exe -xf "%PYTHON_ZIP%"'),
             index(commands, rf'^move "%PYTHON_UNPACKED%" "{re.escape(PRIVATE_PYTHON)}"'),
             index(commands, rf'^"{re.escape(PRIVATE_PYTHON)}\\python\.exe" -I -m venv \.venv$')]
    assert order == sorted(order)
    # each step stops the installation when it fails
    for i in order:
        assert commands[i + 1].startswith('if errorlevel 1 goto ')
    # Windows PowerShell started from PowerShell 7 finds no Get-FileHash with the inherited module path
    assert commands[order[1] - 1] == 'set "PSModulePath="'


def test_the_python_is_extracted_in_tmp_and_moved_as_a_whole():
    # an interrupted extraction must not leave a .python that looks complete
    assert setting('PYTHON_UNPACKED').startswith('.tmp\\')
    assert setting('PYTHON_ZIP').startswith('.tmp\\')


def test_an_existing_environment_is_kept_without_downloading_python():
    commands = batch_commands(installer())
    keep = index(commands, r'^if exist "\.venv\\Scripts\\python\.exe" goto ')
    reuse = index(commands, rf'^if exist "{re.escape(PRIVATE_PYTHON)}\\python\.exe" goto ')
    assert keep < reuse < index(commands, r'^curl\.exe ')


def test_the_installer_keeps_exclamation_marks_in_paths_and_arguments():
    # with delayed expansion, cmd removes the "!" of a folder like C:\Photos!2026 from %~dp0 and %CD% (I21)
    text = installer()
    assert 'EnableDelayedExpansion' not in text
    assert not any('!' in line for line in batch_commands(text))


def test_the_folder_path_is_never_used_inside_a_block():
    # a ")" in the folder path would end the block early
    for line in block_lines(installer()):
        assert '%CD%' not in line and '%~dp0' not in line, line


def test_block_lines_finds_the_body_of_a_block():
    text = 'if x (\n echo a\n set "A=%CD%"\n)\nset "B=%CD%"\n'
    assert block_lines(text) == ['set "A=%CD%"']
