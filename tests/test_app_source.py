"""The app's files fit together (A46): app.py and the modules of framescout_ui.

The app imports streamlit, which CI does not install, so the tests never import it and CI only
compiles it: a name lost when code moved between app.py and a module would only fail when the
page runs. These checks read the source instead.
"""
import ast
import builtins
import symtable

import pytest

import framescout_core
from app_source import APP, ROOT, UI_PACKAGE, app_files

UI = UI_PACKAGE.name
app_file = pytest.mark.parametrize('path', app_files(), ids=lambda path: path.relative_to(ROOT).as_posix())


def top_level_names(path):
    """The names a module defines at its top level (functions, classes, assignments, imports)."""
    table = symtable.symtable(path.read_text(encoding='utf-8'), str(path), 'exec')
    return {symbol.get_name() for symbol in table.get_symbols() if symbol.is_assigned() or symbol.is_imported()}


def undefined_globals(path):
    """The global names path uses anywhere that it neither defines nor imports, and no builtin."""
    top = symtable.symtable(path.read_text(encoding='utf-8'), str(path), 'exec')
    defined = top_level_names(path) | {'__file__', '__name__'}
    found = set()

    def visit(table):
        for symbol in table.get_symbols():
            name = symbol.get_name()
            if (symbol.is_referenced() and (table is top or symbol.is_global())
                    and name not in defined and not hasattr(builtins, name)):
                found.add(name)
        for child in table.get_children():
            visit(child)
    visit(top)
    return found


def imports_from(path):
    """(module, level, name) of every from-import of path."""
    return [(node.module or '', node.level, alias.name) for node in ast.walk(ast.parse(path.read_text(encoding='utf-8')))
            if isinstance(node, ast.ImportFrom) for alias in node.names]


def test_the_app_has_its_modules():
    assert APP in app_files() and len(app_files()) > 2


@app_file
def test_every_global_name_of_the_app_is_defined_or_imported(path):
    assert undefined_globals(path) == set()


@app_file
def test_every_name_the_app_imports_from_framescout_core_exists(path):
    missing = [name for module, level, name in imports_from(path)
               if not level and module == 'framescout_core' and not hasattr(framescout_core, name)]
    assert missing == []


@app_file
def test_every_name_the_app_imports_from_its_modules_is_defined_there(path):
    missing = []
    for module, level, name in imports_from(path):
        if level:  # a relative import inside framescout_ui
            source = UI_PACKAGE / f'{module}.py'
        elif module.startswith(f'{UI}.'):
            source = UI_PACKAGE / f"{module.split('.', 1)[1]}.py"
        else:
            continue
        if not source.is_file() or name not in top_level_names(source):
            missing.append(f'{module}.{name}')
    assert missing == []


def test_only_app_py_imports_the_app_modules():
    # they import streamlit: the engine, the other scripts, framescout_core and the tests run without it
    importing = set()
    for path in [*ROOT.glob('*.py'), *ROOT.glob('framescout_core/*.py'), *ROOT.glob('framescout_scoring/*.py')]:
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            names = ([alias.name for alias in node.names] if isinstance(node, ast.Import)
                     else [node.module or ''] if isinstance(node, ast.ImportFrom) and not node.level else [])
            if any(name.split('.')[0] == UI for name in names):
                importing.add(path.name)
    assert importing == {APP.name}


def test_the_app_modules_never_import_app_py():
    # app.py is the page Streamlit runs as __main__: importing it would run the page again
    for path in UI_PACKAGE.glob('*.py'):
        nodes = list(ast.walk(ast.parse(path.read_text(encoding='utf-8'))))
        modules = ([alias.name for node in nodes if isinstance(node, ast.Import) for alias in node.names]
                   + [node.module or '' for node in nodes if isinstance(node, ast.ImportFrom) and not node.level])
        assert 'app' not in {module.split('.')[0] for module in modules}, path.name
