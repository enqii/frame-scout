"""The package framescout_core re-exports the public names of its area modules (I15)."""
import ast
import importlib
import inspect
import pkgutil

import framescout_core


def area_modules():
    return [importlib.import_module(f'framescout_core.{info.name}')
            for info in pkgutil.iter_modules(framescout_core.__path__) if not info.name.startswith('_')]


def defined_names(module):
    """Public names a module defines itself (functions, classes, assignments), not imports."""
    names = set()
    for node in ast.parse(inspect.getsource(module)).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            for target in node.targets if isinstance(node, ast.Assign) else [node.target]:
                names.update(n.id for n in ast.walk(target) if isinstance(n, ast.Name))
    return {name for name in names if not name.startswith('_')}


def test_there_are_area_modules():
    assert len(area_modules()) >= 10


def test_every_public_name_of_an_area_module_is_re_exported():
    # app.py and the engine import from the package, but the tests never import them and CI
    # only compiles them, so a name missing in __init__.py would only fail at the app start
    missing = sorted(f'{module.__name__}.{name}' for module in area_modules() for name in defined_names(module)
                     if getattr(framescout_core, name, None) is not getattr(module, name))
    assert missing == []


def test_private_helpers_are_not_re_exported():
    # a monkeypatch of a private helper on the package would not reach the calling module
    # (the submodule _common itself is bound on the package by the import system)
    leaked = sorted(name for name, value in vars(framescout_core).items()
                    if name.startswith('_') and not name.startswith('__') and not inspect.ismodule(value))
    assert leaked == []
