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


def section(text, label):
    """The commands from :label up to the next label."""
    lines = [line.strip() for line in text.splitlines()]
    start = lines.index(f':{label}') + 1
    end = next((i for i in range(start, len(lines)) if re.match(r':\w', lines[i])), len(lines))
    return batch_commands('\n'.join(lines[start:end]))


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


VENV_CHECK = r'^"\.venv\\Scripts\\python\.exe" -I -c "import pip" >nul 2>&1$'
VENV_CREATE = rf'^"{re.escape(PRIVATE_PYTHON)}\\python\.exe" -I -m venv --clear \.venv$'


def test_the_download_is_checked_before_it_is_extracted_and_used():
    commands = batch_commands(installer())
    order = [index(commands, r'^curl\.exe .*"%PYTHON_URL%"'),
             index(commands, r'^powershell\.exe .*Get-FileHash .*\$env:PYTHON_ZIP.*\$env:PYTHON_SHA256'),
             index(commands, r'^tar\.exe -xf "%PYTHON_ZIP%"'),
             index(commands, rf'^move "%PYTHON_UNPACKED%" "{re.escape(PRIVATE_PYTHON)}"'),
             index(commands, VENV_CREATE)]
    assert order == sorted(order)
    # each step stops the installation when it fails (the move is tried again first)
    for i in (order[0], order[2], order[4]):
        assert commands[i + 1].startswith('if errorlevel 1 goto ')
    assert commands[order[3] + 1] == 'if not errorlevel 1 goto python_moved'
    assert 'if not "%HASH_RESULT%"=="0" goto checksum_failed' in commands[order[1]:order[2]]


def test_the_module_path_is_cleared_only_for_the_checksum():
    # Windows PowerShell started from PowerShell 7 finds no Get-FileHash with the inherited
    # module path; pip, install_torch.py and their children get the user's value back (review)
    commands = batch_commands(installer())
    check = index(commands, r'^powershell\.exe .*Get-FileHash ')
    assert commands[check - 2:check] == ['set "PSMODULEPATH_SAVED=%PSModulePath%"', 'set "PSModulePath="']
    assert commands[check + 1:check + 4] == ['set "HASH_RESULT=%errorlevel%"',
                                             'set "PSModulePath=%PSMODULEPATH_SAVED%"',
                                             'set "PSMODULEPATH_SAVED="']
    assert sum('PSModulePath=' in line for line in commands) == 2


def test_the_python_is_extracted_in_tmp_and_moved_as_a_whole():
    # an interrupted extraction must not leave a .python that looks complete
    assert setting('PYTHON_UNPACKED').startswith('.tmp\\')
    assert setting('PYTHON_ZIP').startswith('.tmp\\')


def test_the_move_is_tried_again_while_a_virus_scanner_holds_the_new_files():
    # "Access is denied" for a moment after the extraction (review)
    retry = section(installer(), 'move_python')
    assert retry[0] == 'set /a MOVE_TRIES+=1'
    assert retry[1].startswith('move "%PYTHON_UNPACKED%" ')
    assert 'if %MOVE_TRIES% geq 5 goto move_failed' in retry
    # ping waits also when the console input is redirected, timeout does not
    assert any(re.match(r'^ping -n \d+ 127\.0\.0\.1 >nul$', line) for line in retry)
    assert retry[-1] == 'goto move_python'
    assert 'set "MOVE_TRIES=0"' in batch_commands(installer())


def test_a_working_environment_is_kept_without_downloading_python():
    # also one that an older installer created with an installed Python
    commands = batch_commands(installer())
    new = index(commands, r'^if not exist "\.venv\\Scripts\\python\.exe" goto python$')
    check = next(i for i, line in enumerate(commands) if re.match(VENV_CHECK, line))
    assert new < check < index(commands, r'^curl\.exe ')
    assert commands[check + 1] == 'if not errorlevel 1 goto packages'
    assert commands[check + 2] == 'set "VENV_BROKEN=1"'


def test_an_environment_whose_python_is_back_is_kept():
    # a .venv of the private Python works again once .python is downloaded again (review)
    venv = section(installer(), 'venv')
    assert venv[0] == 'if not defined VENV_BROKEN goto venv_create'
    assert re.match(VENV_CHECK, venv[1])
    assert venv[2] == 'if not errorlevel 1 goto packages'


def test_a_broken_environment_is_created_again():
    # its Python is gone (.python deleted, the folder moved) or pip is missing (review);
    # --clear empties only a .venv that does not work: without python.exe or failing both checks
    create = section(installer(), 'venv_create')
    assert any(re.match(VENV_CREATE, line) for line in create)
    assert create[-1] == 'if errorlevel 1 goto venv_failed'


def test_a_half_created_environment_is_removed():
    # it could pass the check at the top on the next run (review)
    assert section(installer(), 'venv_failed')[0] == 'if exist ".venv" rmdir /s /q ".venv"'


def test_an_existing_private_python_is_reused():
    commands = batch_commands(installer())
    reuse = index(commands, rf'^if exist "{re.escape(PRIVATE_PYTHON)}\\python\.exe" goto venv$')
    assert reuse < index(commands, r'^curl\.exe ')


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
