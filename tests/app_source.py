"""The source of the Streamlit app for tests that read it (the app imports streamlit, CI has none).

Since A46 the app is app.py (the page layout) plus the modules of the package framescout_ui.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'app.py'
UI_PACKAGE = ROOT / 'framescout_ui'


def app_files():
    """app.py and the modules of framescout_ui."""
    return [APP, *sorted(UI_PACKAGE.glob('*.py'))]


def app_tree():
    """One syntax tree of all app files: their top-level statements in one module body.

    For checks of what the app does anywhere; line numbers are those of each node's own file,
    so a check of the order of statements parses app.py alone (ast.parse(APP.read_text(...))).
    """
    body = []
    for path in app_files():
        body.extend(ast.parse(path.read_text(encoding='utf-8'), str(path)).body)
    return ast.Module(body=body, type_ignores=[])
