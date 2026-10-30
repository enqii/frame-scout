"""constraints.txt pins every installed package to the version of the verified runs (I12).

Install-FrameScout.bat runs pip install -r requirements.txt -c constraints.txt: requirements.txt
names the direct dependencies with ranges, constraints.txt pins them and all their dependencies
exactly. Standard library only, like the rest of the suite in CI. Whether constraints.txt lists
every transitive dependency needs the packages' metadata and is checked when the lock is
refreshed (pip install --dry-run --report), not here.
"""
import ast
import re
from pathlib import Path

import pytest

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


def test_every_line_is_an_exact_pin_in_sorted_order():
    # every line pins one package exactly ("name==version"; no local label, hash or
    # duplicate), in order of the name, so a refresh shows up as a readable diff; whether
    # every transitive dependency is pinned is checked when the pins are refreshed
    names = []
    for line in lines('constraints.txt'):
        match = PIN.match(line)
        assert match, f'constraints.txt: {line!r} is not an exact pin "name==version" (no local label, no hash)'
        names.append(canonical(match.group(1)))
    assert len(set(names)) == len(names), 'constraints.txt pins a package twice'
    assert names == sorted(names), 'constraints.txt is not sorted by package name'
    assert set(requirements('requirements.txt')) < set(names)  # the dependencies' dependencies too


@pytest.mark.parametrize('path', ['requirements.txt', 'requirements-dev.txt'])
def test_every_requirement_has_a_matching_pin(path):
    pinned = pins()
    for name, specifiers in requirements(path).items():
        if path == 'requirements-dev.txt' and name not in pinned:
            continue  # development tools are not installed with constraints.txt
        assert name in pinned, f'{name} from {path} is not pinned in constraints.txt'
        assert satisfies(pinned[name], specifiers), \
            f'constraints.txt pins {name}=={pinned[name]}, which {path} does not allow'


def batch_commands(text):
    """The lines of a batch file that run something: no empty, rem, echo or label lines."""
    lines = (line.strip() for line in text.splitlines())
    return [line for line in lines if line and not re.match(r'(?i)(rem\b|::|echo\b|:)', line)]


def installer_commands():
    return batch_commands((ROOT / 'Install-FrameScout.bat').read_text(encoding='utf-8'))


def test_batch_commands_skip_comments_and_messages():
    text = ('rem ".venv\\Scripts\\python.exe" -m pip install -r requirements.txt -c constraints.txt\n'
            ' REM x\n:: x\n echo -m pip install -r requirements.txt -c constraints.txt\n:label\n\n'
            ' set "A=b"\nif errorlevel 1 (echo failed & exit /b 1)\n')
    assert batch_commands(text) == ['set "A=b"', 'if errorlevel 1 (echo failed & exit /b 1)']


def test_installer_uses_the_constraints():
    # the pip command itself, not a comment or a message that mentions it (review)
    assert any('-m pip install' in line and '-r requirements.txt -c constraints.txt' in line
               for line in installer_commands())


def test_installer_constrains_the_torch_install_too():
    # PIP_CONSTRAINT reaches the pip call of install_torch.py, so torch's dependencies are
    # installed in their pinned versions right away (I18); relative, because pip splits the
    # value at spaces and the installer folder may contain one
    commands = installer_commands()
    setting = commands.index('set "PIP_CONSTRAINT=constraints.txt"')
    torch_install = next(i for i, line in enumerate(commands) if 'install_torch.py' in line)
    venv = next(i for i, line in enumerate(commands) if '-m venv' in line)
    assert venv < setting < torch_install


def test_streamlit_floor_allows_the_width_parameter():
    # app.py sizes its buttons with width="stretch", which st.button and st.download_button
    # accept since Streamlit 1.48.0 (A10)
    specifiers = requirements('requirements.txt')['streamlit']
    floors = [wanted for op, wanted in specifiers if op == '>=']
    assert floors and all(version_key(wanted) >= version_key('1.48') for wanted in floors)
    # only call keywords count, so a comment or string that names the old parameter does not
    # fail the test (A10, review)
    tree = ast.parse((ROOT / 'app.py').read_text(encoding='utf-8'))
    keywords = {node.arg for node in ast.walk(tree) if isinstance(node, ast.keyword)}
    assert 'use_container_width' not in keywords, 'use width="stretch" instead (A10)'
