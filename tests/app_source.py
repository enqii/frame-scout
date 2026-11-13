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
    so a check of the order of statements uses page_tree().
    """
    body = []
    for path in app_files():
        body.extend(ast.parse(path.read_text(encoding='utf-8'), str(path)).body)
    return ast.Module(body=body, type_ignores=[])


def page_tree():
    """The syntax tree of app.py alone, the page run: for checks that compare line numbers.

    Line numbers of app_tree() come from different files and must not be compared (review).
    """
    return ast.parse(APP.read_text(encoding='utf-8'), str(APP))
