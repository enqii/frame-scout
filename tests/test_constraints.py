"""constraints.txt pins every installed package to a tested version (I12).

Install-FrameScout.bat runs pip install -r requirements.txt -c constraints.txt: requirements.txt
names the direct dependencies with ranges, constraints.txt pins them and all their dependencies
exactly. Standard library only, like the rest of the suite in CI. Whether constraints.txt lists
every transitive dependency needs the packages' metadata and is checked when the lock is
refreshed (pip install --dry-run --report), not here.
"""
import re
from pathlib import Path

import pytest

from framescout_core import TORCH_VERSION, TORCHVISION_VERSION

ROOT = Path(__file__).resolve().parent.parent
PIN = re.compile(r'^([A-Za-z0-9][A-Za-z0-9._-]*)==(\d+(?:\.\d+)*(?:\.post\d+)?)$')
REQUIREMENT = re.compile(r'^([A-Za-z0-9][A-Za-z0-9._-]*)\s*((?:[<>=!]=?\s*[\w.]+\s*,?\s*)*)$')
SPECIFIER = re.compile(r'^(==|!=|>=|<=|<|>)\s*(\d+(?:\.\d+)*)$')


def canonical(name):
    """The package name as pip compares it (PEP 503)."""
    return re.sub(r'[-_.]+', '-', name).lower()


def version_key(text):
    """A comparable key for a plain release version, optionally with .postN ("2.9.0.post0")."""
    release, _, post = text.partition('.post')
    parts = [int(x) for x in release.split('.')]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts), int(post) if post else -1


def satisfies(version, specifiers):
    """True if version meets every specifier, e.g. [('>=', '2.5.4'), ('<', '3')]."""
    have = version_key(version)
    checks = {'==': lambda want: have == want, '!=': lambda want: have != want,
              '>=': lambda want: have >= want, '<=': lambda want: have <= want,
              '<': lambda want: have < want, '>': lambda want: have > want}
    return all(checks[op](version_key(wanted)) for op, wanted in specifiers)


def lines(path):
    """The non-empty lines of path without comments."""
    result = []
    for line in (ROOT / path).read_text(encoding='utf-8').splitlines():
        line = line.split('#', 1)[0].strip()
        if line:
            result.append(line)
    return result


def requirements(path):
    """{canonical name: [(operator, version)]} of a requirements file with plain specifiers."""
    result = {}
    for line in lines(path):
        match = REQUIREMENT.match(line)
        assert match, f'{path}: cannot read the requirement {line!r}'
        specifiers = []
        for part in filter(None, (x.strip() for x in match.group(2).split(','))):
            spec = SPECIFIER.match(part)
            assert spec, f'{path}: cannot read the version specifier {part!r} in {line!r}'
            specifiers.append(spec.groups())
        result[canonical(match.group(1))] = specifiers
    return result


def pins():
    """{canonical name: version} of constraints.txt; every line must be an exact pin."""
    result = {}
    for line in lines('constraints.txt'):
        match = PIN.match(line)
        assert match, f'constraints.txt: {line!r} is not an exact pin "name==version" (no local label, no hash)'
        name = canonical(match.group(1))
        assert name not in result, f'constraints.txt pins {name} twice'
        result[name] = match.group(2)
    return result


def test_version_comparison():
    # the checks below rely on it; numeric, not textual order, and trailing zeros are equal
    assert satisfies('2.10.0', [('>=', '2.5.4'), ('<', '3')])
    assert not satisfies('13.0.0', [('>=', '12.3.0'), ('<', '13')])
    assert satisfies('12.3', [('==', '12.3.0')])
    assert satisfies('2.9.0.post0', [('>=', '2.9.0')])
    assert not satisfies('2.14.0', [('==', '2.14.1')])
    assert not satisfies('1.40', [('>', '1.40')])
    assert satisfies('5.0.0.93', [('>=', '5')])


def test_constraints_are_exact_pins():
    assert len(pins()) > len(requirements('requirements.txt'))


@pytest.mark.parametrize('path', ['requirements.txt', 'requirements-dev.txt'])
def test_every_requirement_has_a_matching_pin(path):
    pinned = pins()
    for name, specifiers in requirements(path).items():
        if path == 'requirements-dev.txt' and name not in pinned:
            continue  # development tools are not installed with constraints.txt
        assert name in pinned, f'{name} from {path} is not pinned in constraints.txt'
        assert satisfies(pinned[name], specifiers), \
            f'constraints.txt pins {name}=={pinned[name]}, which {path} does not allow'


def test_torch_pins_match_the_installer():
    # without a local label "torch==2.14.1" matches the +cpu and the CUDA builds that
    # install_torch.py installs before requirements.txt
    assert pins()['torch'] == TORCH_VERSION
    assert pins()['torchvision'] == TORCHVISION_VERSION


def installer_commands():
    """The lines of Install-FrameScout.bat that run something: no rem, echo or label lines."""
    result = []
    for line in (ROOT / 'Install-FrameScout.bat').read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line and not re.match(r'(?i)(rem\b|::|echo\b|:)', line):
            result.append(line)
    return result


def test_installer_uses_the_constraints():
    text = (ROOT / 'Install-FrameScout.bat').read_text(encoding='utf-8')
    assert '-r requirements.txt -c constraints.txt' in text


def test_installer_constrains_the_torch_install_too():
    # PIP_CONSTRAINT reaches the pip call of install_torch.py, so torch's dependencies are
    # installed in their pinned versions right away (I18); relative, because pip splits the
    # value at spaces and the installer folder may contain one
    commands = installer_commands()
    setting = commands.index('set "PIP_CONSTRAINT=constraints.txt"')
    torch_install = next(i for i, line in enumerate(commands) if 'install_torch.py' in line)
    venv = next(i for i, line in enumerate(commands) if '-m venv' in line)
    assert venv < setting < torch_install
