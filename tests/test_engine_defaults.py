"""The engine's CLI defaults that must match the app's (read from the source: the engine imports torch)."""
import ast
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent / 'framescout_engine.py'


def option_default_node(option):
    """The AST node of the default= keyword of parser.add_argument(option, ...), or None."""
    for node in ast.walk(ast.parse(ENGINE.read_text(encoding='utf-8'))):
        if (isinstance(node, ast.Call) and getattr(node.func, 'attr', None) == 'add_argument'
                and node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value == option):
            return next((k.value for k in node.keywords if k.arg == 'default'), None)
    raise AssertionError(f'{option} not found in {ENGINE.name}')


def add_argument_call(option):
    for node in ast.walk(ast.parse(ENGINE.read_text(encoding='utf-8'))):
        if (isinstance(node, ast.Call) and getattr(node.func, 'attr', None) == 'add_argument'
                and node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value == option):
            return node
    raise AssertionError(f'{option} not found in {ENGINE.name}')


def test_the_engine_takes_one_or_more_photo_folders():
    # A25: "framescout_engine.py D:\a E:\b --profiles ..."; a call with one folder works as before
    keywords = {k.arg: k.value for k in add_argument_call('folder').keywords}
    assert isinstance(keywords.get('nargs'), ast.Constant) and keywords['nargs'].value == '+'


def test_the_engine_uses_the_shared_default_reference_weight():
    default = option_default_node('--reference-weight')
    assert isinstance(default, ast.Name) and default.id == 'DEFAULT_REFERENCE_WEIGHT', \
        f'--reference-weight must default to DEFAULT_REFERENCE_WEIGHT, found {ast.dump(default) if default else None}'


def test_the_engine_imports_ultralytics_only_through_import_detector_class():
    # E27, E28: a direct import would skip the environment that turns off its analytics and installs
    nodes = list(ast.walk(ast.parse(ENGINE.read_text(encoding='utf-8'))))
    direct = [node.lineno for node in nodes
              if (isinstance(node, ast.ImportFrom) and (node.module or '').split('.')[0] == 'ultralytics')
              or (isinstance(node, ast.Import) and any(a.name.split('.')[0] == 'ultralytics' for a in node.names))]
    assert direct == [], f'framescout_engine.py imports ultralytics directly on line(s) {direct}'
    calls = [node for node in nodes if isinstance(node, ast.Call) and getattr(node.func, 'id', None) == 'import_detector_class']
    assert len(calls) == 1, 'the engine must load the detector class with import_detector_class'
    # it must change the real process environment, which Ultralytics reads on import (review)
    assert ast.unparse(calls[0].args[0]) == 'os.environ'


def test_the_engine_uses_the_shared_default_yolo_model():
    # known_signatures computes the cache signatures of the app's settings with it (E11)
    default = option_default_node('--yolo-model')
    assert isinstance(default, ast.Name) and default.id == 'DEFAULT_YOLO_MODEL'
