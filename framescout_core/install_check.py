"""The "Check installation" self-test (F15): is the installation in this folder complete and usable?

After a Windows update, a moved folder or an interrupted installation, a search fails with a
traceback in run.log, and nothing says whether to reinstall. Check-FrameScout.bat
(framescout_check.py) and the app's AI settings tab run these checks and name one fix per
problem: the program files are of one FrameScout version (I34), the Python environment
belongs to this folder, the installed package versions are those of requirements/constraints.txt, PyTorch imports (and finds the GPU for a CUDA build), .cache and
results can be written, which model files are downloaded, and the free disk space.

Read-only: nothing is written, downloaded or repaired. The only file operation is a temporary
file that is created and deleted again to see whether a folder can be written (Windows
reports a folder's permissions unreliably otherwise). PyTorch is imported in a subprocess of
the environment's Python, since its import takes seconds and can crash on a broken install.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
from importlib import metadata
from pathlib import Path
from typing import NamedTuple

from .cache_dirs import CACHE_DIR, engine_cache_env, find_yolo_weights
from .cleanup import _reachable_roots, size_text
from .devices import cuda_hint
from .disk_space import SPACE_CHECK_TIMEOUT, SPACE_RESERVE, _existing_folder, _reachable, downloaded_models
from .hub import hub_cache_dir
from .layout import REPLACED_PACKAGES, leftover_fix, leftover_text
from .models import MODELS
from .paths import CONSTRAINTS_FILE, REQUIREMENTS_FILE, windows_path
from .portable_python import PRIVATE_PYTHON
from .signature import DEFAULT_YOLO_MODEL

VENV_DIR = '.venv'
# seconds the PyTorch import may take: the first import after an installation can be slow
# while a virus scanner checks the files
TORCH_CHECK_TIMEOUT = 180
# run by the environment's Python with -B (no compiled files written): one JSON line
TORCH_PROBE = ('import json, torch; available = torch.cuda.is_available(); '
               'print(json.dumps({"torch": torch.__version__, "cuda": torch.version.cuda, "available": available, '
               '"gpu": torch.cuda.get_device_name(0) if available else None}))')
REINSTALL = 'Close FrameScout and run Install-FrameScout.bat again.'
_PIN = re.compile(r'\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*==\s*([^\s;#]+)')
_REQUIREMENT_NAME = re.compile(r'\s*([A-Za-z0-9][A-Za-z0-9._-]*)')


class CheckResult(NamedTuple):
    """One check: its name, ok (True fine, False a problem, None information), what was found, the fix."""
    name: str
    ok: object
    text: str
    fix: str


def venv_python(base):
    """The Python of the environment in base (.venv/Scripts/python.exe on Windows)."""
    venv = Path(base) / VENV_DIR
    return venv / 'Scripts' / 'python.exe' if os.name == 'nt' else venv / 'bin' / 'python'


def venv_site_packages(base):
    """The folder the environment in base installs its packages into."""
    venv = Path(base) / VENV_DIR
    if os.name == 'nt':
        return venv / 'Lib' / 'site-packages'
    found = sorted(venv.glob('lib/python3*/site-packages'))
    return found[-1] if found else venv / 'lib' / 'site-packages'


def _canonical(name):
    """The package name as pip compares it (PEP 503)."""
    return re.sub(r'[-_.]+', '-', name).lower()


def requirement_names(text):
    """Return the package names of the requirements file text (comments and blank lines skipped)."""
    names = []
    for line in text.splitlines():
        match = _REQUIREMENT_NAME.match(line.split('#', 1)[0])
        if match:
            names.append(match[1])
    return names


def installed_versions(site_packages):
    """Return {canonical name: version} of the packages installed in the folder site_packages (read-only)."""
    if not Path(site_packages).is_dir():
        return {}
    versions = {}
    for dist in metadata.distributions(path=[str(site_packages)]):
        name = dist.metadata['Name'] if dist.metadata else None
        if name:
            versions.setdefault(_canonical(name), dist.version)
    return versions


def _read_cfg(path):
    """The key = value lines of a pyvenv.cfg."""
    values = {}
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        key, sep, value = line.partition('=')
        if sep:
            values[key.strip().lower()] = value.strip()
    return values


def _same_folder(first, second):
    """Whether both paths name the same existing folder, also through a link, junction or 8.3 short name."""
    try:
        return os.path.samefile(first, second)
    except OSError:
        return False


def check_program_files(base):
    """Are the program files in base of one FrameScout version (I34)? A single file next to its package is a leftover."""
    name = 'Program files'
    found = [package for package in REPLACED_PACKAGES
             if (Path(base) / f'{package}.py').is_file() and (Path(base) / package / '__init__.py').is_file()]
    if not found:
        return [CheckResult(name, True, 'No leftovers of another FrameScout version.', '')]
    return [CheckResult(name, False, f'The FrameScout folder holds {leftover_text(package)}', leftover_fix(package))
            for package in found]


def check_environment(base):
    """Check that .venv exists and its Python is there and belongs to this folder (or is an installed Python)."""
    name = 'Python environment'
    base = Path(base)
    if not venv_python(base).is_file():
        return [CheckResult(name, False, 'There is no Python environment in .venv.',
                            'Run Install-FrameScout.bat.')]
    try:
        home = Path(_read_cfg(base / VENV_DIR / 'pyvenv.cfg')['home'])
    except (OSError, UnicodeDecodeError, KeyError) as exc:
        return [CheckResult(name, False, f'The file .venv/pyvenv.cfg cannot be read ({exc}).',
                            f'Delete the folder {VENV_DIR} in this folder, then run Install-FrameScout.bat.')]
    private = base / PRIVATE_PYTHON
    pythons = [home / 'python.exe', home / 'python', home / 'python3']
    if not any(path.is_file() for path in pythons):
        return [CheckResult(name, False, f'The Python that .venv was created with is missing ({home}): the '
                            'FrameScout folder was moved, or that Python was deleted or uninstalled.',
                            'Run Install-FrameScout.bat; it repairs the environment. Or move the folder back.')]
    if home.name.lower() == PRIVATE_PYTHON and not _same_folder(home, private):
        return [CheckResult(name, False, f'.venv uses the private Python of another folder ({home}): the FrameScout '
                            'folder was copied or moved, and it stops working when that folder is deleted.',
                            f'Delete the folder {VENV_DIR} in this folder, then run Install-FrameScout.bat.')]
    if home.name.lower() == PRIVATE_PYTHON:
        return [CheckResult(name, True, 'The environment in .venv uses the private Python of this folder.', '')]
    return [CheckResult(name, True, f'The environment in .venv uses the installed Python in {home} (made by an older '
                        'installer).', '')]


def check_packages(site_packages, constraints_text, requirements_text):
    """Check that the packages of requirements/requirements.txt are installed and every installed pinned package has its pin.

    A pin of a package that is not installed is no problem unless requirements.txt names it
    (requirements/constraints.txt may pin packages another Python version needs), and a requirement with an
    environment marker is not required either. torch and torchvision count with any build
    label (+cpu, +cu130).
    """
    name = 'Packages'
    installed = installed_versions(site_packages)
    pins = {}
    for line in constraints_text.splitlines():
        match = _PIN.match(line.split('#', 1)[0])
        if match:
            pins[_canonical(match[1])] = match[2]
    # a requirement with an environment marker (";") may not apply to this platform or Python,
    # and the standard library cannot evaluate markers: it is not reported missing (review)
    unconditional = '\n'.join(line for line in requirements_text.splitlines() if ';' not in line.split('#', 1)[0])
    missing = [package for package in requirement_names(unconditional) if _canonical(package) not in installed]
    other = [f'{package} {installed[package]} instead of {version}' for package, version in sorted(pins.items())
             if package in installed and installed[package].partition('+')[0] != version]
    if not missing and not other:
        return [CheckResult(name, True, f'{len(installed)} packages installed, in the versions of '
                            f'{windows_path(CONSTRAINTS_FILE)}.', '')]
    parts = ([f'missing: {", ".join(missing)}'] if missing else []) + (
        [f'other versions: {", ".join(other)}'] if other else [])
    return [CheckResult(name, False, 'Not as the installer installs them: ' + '; '.join(parts) + '.',
                        f'{REINSTALL} It installs the versions of {windows_path(CONSTRAINTS_FILE)}.')]


def check_torch(python, environ, torch_version, run=subprocess.run, timeout=TORCH_CHECK_TIMEOUT, cwd=None):
    """Import PyTorch with the environment's python in a subprocess; for a CUDA build, check that it finds a GPU.

    torch_version is the installed version from the package metadata (None: not installed,
    nothing is run); environ the environment of the subprocess; run is subprocess.run; cwd
    its working folder. The import sees the sys.path the engine gets: with cwd the FrameScout
    folder, the first entry is that folder, as for the engine script, and environ is the
    engine's environment; no -I, since a PYTHONPATH that breaks PyTorch breaks the engine too.
    """
    name = 'PyTorch'
    if torch_version is None:
        return [CheckResult(name, False, 'PyTorch is not installed.', REINSTALL)]
    try:
        result = run([str(python), '-B', '-c', TORCH_PROBE], capture_output=True, text=True, env=environ,
                     timeout=timeout, cwd=None if cwd is None else str(cwd))
    except subprocess.TimeoutExpired:
        return [CheckResult(name, False, f'Importing PyTorch did not finish within {timeout} seconds.', REINSTALL)]
    except OSError as exc:
        return [CheckResult(name, False, f'The Python of .venv cannot be started ({exc}).', REINSTALL)]
    lines = (result.stdout or '').strip().splitlines()
    try:
        if result.returncode:
            raise ValueError
        found = json.loads(lines[-1])
    except (ValueError, IndexError):
        error = ((result.stderr or '').strip().splitlines() or [f'exit code {result.returncode}'])[-1]
        return [CheckResult(name, False, f'PyTorch {torch_version} cannot be imported: {error}',
                            f'{REINSTALL} If it still fails, delete the folder {VENV_DIR} and run it once more.')]
    cuda_build = torch_version.partition('+')[2].startswith('cu')
    if found.get('available'):
        return [CheckResult(name, True, f'PyTorch {found.get("torch")} works and uses the GPU {found.get("gpu")} '
                            '(CUDA).', '')]
    if cuda_build:
        return [CheckResult(name, False, f'PyTorch {found.get("torch")} with CUDA support works but finds no usable '
                            'NVIDIA GPU, so searches run on the CPU.', cuda_hint(found.get('cuda') or 'cuda'))]
    return [CheckResult(name, True, f'PyTorch {found.get("torch")} (CPU build) works; searches run on the CPU.', '')]


def check_writable(folder, label):
    """Check that the folder (or, if it does not exist yet, its nearest existing parent) can be written.

    A temporary file is created and deleted again; nothing else is written or created.
    """
    name = f'{"Cache" if label == CACHE_DIR else "Results"} folder ({label})'
    existing = _existing_folder(folder)
    try:
        if existing is None:
            raise FileNotFoundError(f'no existing folder on the way to {folder}')
        with tempfile.TemporaryFile(dir=existing):
            pass
    except OSError as exc:
        return [CheckResult(name, False, f'{folder} cannot be written: {exc}.',
                            'Move FrameScout to a folder you can write to (e.g. in your user folder, not in '
                            'C:\\Program Files) and check that a virus scanner does not block it.')]
    state = '' if Path(folder).is_dir() else ' (created on first use)'
    return [CheckResult(name, True, f'{folder} can be written{state}.', '')]


def check_models(base, environ, timeout=SPACE_CHECK_TIMEOUT, reachable=_reachable_roots):
    """Information only: which search models and whether the person detection model are downloaded.

    A model that is not downloaded is no problem: a search downloads it on first use. If the
    drive of the model cache does not answer within timeout seconds (reachable: cleanup's root
    probe), the result says that it is not known instead of "not downloaded yet" (review).
    """
    env = engine_cache_env(environ, base)  # the engine's cache variables, as the app gives them
    hub_cache = hub_cache_dir(env)
    if not _reachable([hub_cache], timeout, reachable)[hub_cache]:
        return [CheckResult('Model files', None, f'The model folder {hub_cache} did not answer within {timeout:g} '
                            'seconds, so which model files are downloaded is not known.', '')]
    downloaded = downloaded_models(base, env)
    found, _ = find_yolo_weights(DEFAULT_YOLO_MODEL, base, base, env)
    have = [MODELS[key].label for key in MODELS if key in downloaded] + (['person detection'] if found else [])
    missing = [f'{MODELS[key].label} ({MODELS[key].download})' for key in MODELS if key not in downloaded] + (
        [] if found else ['person detection'])
    parts = [f'Downloaded: {", ".join(have)}.' if have else 'No model file is downloaded yet.']
    if missing:
        parts.append(f'Not downloaded yet: {", ".join(missing)}; each one is downloaded the first time a search '
                     'uses it (needs internet access).')
    return [CheckResult('Model files', None, ' '.join(parts), '')]


def check_disk_space(base, disk_usage=shutil.disk_usage, reserve=SPACE_RESERVE):
    """Check that the drive of base has at least reserve bytes free."""
    name = 'Free disk space'
    try:
        free = disk_usage(base).free
    except OSError as exc:
        return [CheckResult(name, None, f'The free disk space cannot be determined ({exc}).', '')]
    if free < reserve:
        return [CheckResult(name, False, f'Only {size_text(free)} free on the drive of the FrameScout folder.',
                            f'Free at least {size_text(reserve)} on that drive; a full disk breaks downloads and the '
                            'cache.')]
    return [CheckResult(name, True, f'{size_text(free)} free on the drive of the FrameScout folder.', '')]


def _read_text(path):
    try:
        return Path(path).read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        return ''


def check_installation(base, environ, run=subprocess.run):
    """Run every check for the FrameScout folder base; environ is os.environ (not changed). Returns CheckResults.

    The packages are checked only if .venv has a Python, PyTorch is imported (with the
    environment's Python and the cache variables the engine gets, engine_cache_env) only if the
    environment check found no problem; otherwise they are information "Not checked", so a
    broken environment counts as one problem.
    """
    base = Path(base)
    env = engine_cache_env(environ, base)  # the engine's cache variables, as the app gives them
    environment = check_environment(base)
    results = check_program_files(base) + environment
    site = venv_site_packages(base)
    if venv_python(base).is_file():
        results += check_packages(site, _read_text(base / CONSTRAINTS_FILE), _read_text(base / REQUIREMENTS_FILE))
    else:
        results.append(CheckResult('Packages', None, 'Not checked, since there is no Python environment.', ''))
    if environment[0].ok:
        torch = installed_versions(site).get('torch')
        results += check_torch(venv_python(base), env, torch, run=run, cwd=base)
    else:
        results.append(CheckResult('PyTorch', None, 'Not checked, since the Python environment does not work.', ''))
    results += check_writable(base / CACHE_DIR, CACHE_DIR)
    results += check_writable(base / 'results', 'results')
    results += check_models(base, env)  # engine_cache_env again keeps env as it is
    results += check_disk_space(base)
    return results


def check_lines(results):
    """Return the text lines of results: "[OK]      name: text", a problem with a "Fix:" line below it."""
    tags = {True: '[OK]     ', False: '[PROBLEM]', None: '[INFO]   '}
    lines = []
    for result in results:
        lines.append(f'{tags[result.ok]} {result.name}: {result.text}')
        if result.fix:
            lines.append(f'          Fix: {result.fix}')
    return lines
