"""The engine's CLI defaults that must match the app's (read from the source: the engine imports torch)."""
import ast
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent / 'framescout_engine.py'


def option_default(option):
    for node in ast.walk(ast.parse(ENGINE.read_text(encoding='utf-8'))):
        if (isinstance(node, ast.Call) and getattr(node.func, 'attr', None) == 'add_argument'
                and node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value == option):
            return next(k.value for k in node.keywords if k.arg == 'default')
    raise AssertionError(f'{option} not found')


def test_the_engine_uses_the_shared_default_reference_weight():
    default = option_default('--reference-weight')
    assert isinstance(default, ast.Name) and default.id == 'DEFAULT_REFERENCE_WEIGHT'
