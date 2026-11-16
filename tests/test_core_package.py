"""Imports from framescout_core go to the module that defines a name (I45): no re-export list."""
import ast
import importlib
import pkgutil
from pathlib import Path

import framescout_core

ROOT = Path(__file__).resolve().parent.parent
# the repository's own Python files: the scripts, the packages and the tests
SOURCES = [*ROOT.glob('*.py'), *ROOT.glob('framescout_*/*.py'), *ROOT.glob('tests/*.py')]


def area_modules():
    return {info.name for info in pkgutil.iter_modules(framescout_core.__path__)}


def test_there_are_area_modules():
    assert len(area_modules()) >= 10


def test_the_package_file_holds_no_code():
    # a name imported here again would start a second, hand-kept re-export list
    body = ast.parse((ROOT / 'framescout_core' / '__init__.py').read_text(encoding='utf-8')).body
    assert len(body) == 1 and isinstance(body[0], ast.Expr)  # the docstring


def test_every_name_imported_from_framescout_core_exists():
    # app.py and the engine need streamlit or torch, which CI does not install: CI only
    # compiles them, so a wrong module or name would only fail when they run
    missing = []
    for path in SOURCES:
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if not isinstance(node, ast.ImportFrom) or node.level or not (node.module or '').startswith('framescout_core'):
                continue
            module = importlib.import_module(node.module)
            for alias in node.names:
                # from the package itself only its modules ("from framescout_core import cleanup")
                found = (alias.name in area_modules() if node.module == 'framescout_core'
                         else hasattr(module, alias.name))
                if not found:
                    missing.append(f'{path.relative_to(ROOT).as_posix()}: {node.module}.{alias.name}')
    assert missing == []
