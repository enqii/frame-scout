"""The engine's CLI defaults that must match the app's (read from the source: the engine imports torch)."""
import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parent.parent / 'framescout_engine.py'
APP = ENGINE.with_name('app.py')


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
    # review: "D:\a --device cpu E:\b" must work too, as options before a single folder did
    calls = [node.func.attr for node in ast.walk(ast.parse(ENGINE.read_text(encoding='utf-8')))
             if isinstance(node, ast.Call) and getattr(node.func, 'attr', '').startswith('parse_')
             and getattr(node.func, 'attr', '').endswith('args')]
    assert calls == ['parse_intermixed_args']


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


def test_the_engine_offers_the_registered_search_models():
    # E22: --model takes the registry keys (no free-text names), with the app's default
    keywords = {k.arg: k.value for k in add_argument_call('--model').keywords}
    assert isinstance(keywords.get('default'), ast.Name) and keywords['default'].id == 'DEFAULT_MODEL'
    assert isinstance(keywords.get('choices'), ast.Name) and keywords['choices'].id == 'MODEL_KEYS'


def test_the_engine_loads_and_caches_the_chosen_model():
    # the default model's names alone would load the default whatever --model says
    nodes = list(ast.walk(ast.parse(ENGINE.read_text(encoding='utf-8'))))
    # (CLIP_MODEL/CLIP_PRETRAINED are gone; review): DEFAULT_MODEL only as the --model default
    defaults = [node for node in nodes if isinstance(node, ast.Name) and node.id == 'DEFAULT_MODEL'
                and isinstance(node.ctx, ast.Load)]
    assert len(defaults) == 1, 'the engine may use DEFAULT_MODEL only as the default of --model'
    [prepare] = [node for node in nodes if isinstance(node, ast.Call) and getattr(node.func, 'id', None) == 'prepare_cache']
    assert any(k.arg == 'model' and ast.unparse(k.value) == 'args.model' for k in prepare.keywords)


def test_the_engine_output_never_fails_on_a_character_of_another_code_page():
    # E22 review: the model labels, profile names and paths can hold characters that the
    # ANSI code page of a redirected stdout (e.g. cp932) cannot encode
    [main] = [node for node in ast.walk(ast.parse(ENGINE.read_text(encoding='utf-8')))
              if isinstance(node, ast.FunctionDef) and node.name == 'main']
    calls = [node for node in ast.walk(main) if isinstance(node, ast.Call)
             and getattr(node.func, 'attr', None) == 'reconfigure']
    assert calls, 'main() must reconfigure sys.stdout and sys.stderr'
    assert all(any(k.arg == 'errors' and ast.unparse(k.value) == "'backslashreplace'" for k in call.keywords)
               for call in calls)
    assert 'sys.stdout, sys.stderr' in ast.unparse(main)


def test_the_app_starts_the_engine_with_utf8_output():
    # E22 review: the app writes the engine's output to run.log and reads it as UTF-8
    tree = ast.parse(APP.read_text(encoding='utf-8'))
    [cache_env] = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == 'cache_env']
    assigned = {ast.unparse(node.targets[0]): ast.unparse(node.value) for node in ast.walk(cache_env)
                if isinstance(node, ast.Assign) and len(node.targets) == 1}
    assert assigned.get("env['PYTHONIOENCODING']") == "'utf-8'"


def test_the_engine_uses_the_shared_default_yolo_model():
    # known_signatures computes the cache signatures of the app's settings with it (E11)
    default = option_default_node('--yolo-model')
    assert isinstance(default, ast.Name) and default.id == 'DEFAULT_YOLO_MODEL'


def test_the_engine_can_write_the_raw_scores_for_the_evaluation():
    # E32: --scores-file is off by default and writes the scores file of framescout_core
    default = option_default_node('--scores-file')
    assert default is None or (isinstance(default, ast.Constant) and default.value is None)
    keywords = {k.arg: ast.unparse(k.value) for k in add_argument_call('--scores-file').keywords}
    assert keywords.get('type') == 'Path'
    tree = ast.parse(ENGINE.read_text(encoding='utf-8'))
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and getattr(node.func, 'id', None) in ('write_scores', 'scores_document')]
    assert sorted(node.func.id for node in calls) == ['scores_document', 'write_scores']
    # written from the scores the galleries rank, before the (slower) gallery export
    [search] = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == 'search']
    source = ast.unparse(search)
    assert source.index('write_scores(') < source.index("thumbs = output / 'thumbnails'")


def test_the_engine_imports_open_clip_only_through_import_open_clip():
    # E16, E33: huggingface_hub reads its offline and warning variables when it is imported,
    # so neither open_clip nor a library that imports huggingface_hub may be imported before
    nodes = list(ast.walk(ast.parse(ENGINE.read_text(encoding='utf-8'))))
    hub_users = {'open_clip', 'huggingface_hub', 'transformers', 'timm'}
    direct = [node.lineno for node in nodes
              if (isinstance(node, ast.ImportFrom) and (node.module or '').split('.')[0] in hub_users)
              or (isinstance(node, ast.Import) and any(a.name.split('.')[0] in hub_users for a in node.names))]
    assert direct == [], f'framescout_engine.py imports a Hugging Face library directly on line(s) {direct}'
    calls = [node for node in nodes if isinstance(node, ast.Call) and getattr(node.func, 'id', None) == 'import_open_clip']
    assert len(calls) == 1, 'the engine must import open_clip with import_open_clip'
    assert ast.unparse(calls[0].args[0]) == 'os.environ'
    assert ast.unparse(calls[0].args[1]) == 'importlib.import_module'
    # an earlier indirect import of huggingface_hub gets the values through sys.modules (review)
    assert {kw.arg: ast.unparse(kw.value) for kw in calls[0].keywords}.get('modules') == 'sys.modules'
    [fallback] = [node for node in nodes if isinstance(node, ast.Call)
                  and getattr(node.func, 'id', None) == 'load_with_hub_fallback']
    assert 'hub_go_online(os.environ, sys.modules)' in ast.unparse(fallback)


def test_the_engine_sets_the_cache_folders_before_the_model_libraries_are_imported():
    # I10: a manual run keeps the model downloads and config files under the project's .cache
    tree = ast.parse(ENGINE.read_text(encoding='utf-8'))
    calls = [node for node in tree.body if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
             and getattr(node.value.func, 'id', None) == 'default_cache_env']
    assert len(calls) == 1, 'the engine must call default_cache_env once at module level'
    assert ast.unparse(calls[0].value) == 'default_cache_env(os.environ, Path(__file__).resolve().parent)'
    third_party = [node.lineno for node in tree.body
                   if (isinstance(node, ast.Import) and any(a.name.split('.')[0] not in sys.stdlib_module_names
                                                            for a in node.names))
                   or (isinstance(node, ast.ImportFrom) and (node.module or '').split('.')[0]
                       not in sys.stdlib_module_names | {'framescout_core'})]
    assert third_party and calls[0].lineno < min(third_party)


def test_the_engine_loads_the_detector_weights_from_the_cache():
    # E9: YOLO('yolo11n.pt') downloads into the working folder; the cache signature keeps the name
    nodes = list(ast.walk(ast.parse(ENGINE.read_text(encoding='utf-8'))))
    [detector] = [node for node in nodes if isinstance(node, ast.Call) and getattr(node.func, 'id', None) == 'YOLO']
    assert ast.unparse(detector) == 'YOLO(yolo_weights(args.yolo_model, Path(__file__).resolve().parent, Path.cwd()))'
    [prepare] = [node for node in nodes if isinstance(node, ast.Call) and getattr(node.func, 'id', None) == 'prepare_cache']
    assert 'args.yolo_model' in [ast.unparse(arg) for arg in prepare.args]


def test_importing_the_engine_sets_the_unset_cache_variables():
    # needs the engine's own imports (torch, Pillow), so it is skipped in CI
    pytest.importorskip('torch')
    pytest.importorskip('PIL')
    names = ('TORCH_HOME', 'HF_HOME', 'YOLO_CONFIG_DIR', 'XDG_CACHE_HOME')
    env = {k: v for k, v in os.environ.items() if k not in names}
    env['HF_HOME'] = str(ENGINE.parent / '.tmp' / 'own-hf')  # set by the user: kept
    script = f'import os, framescout_engine\nprint([os.environ[n] for n in {names!r}])'
    result = subprocess.run([sys.executable, '-c', script], cwd=ENGINE.parent, capture_output=True, text=True,
                            timeout=300, env=env)
    assert result.returncode == 0, result.stderr
    cache = ENGINE.parent / '.cache'
    assert result.stdout.strip().splitlines()[-1] == repr(
        [str(cache / 'torch'), env['HF_HOME'], str(cache / 'ultralytics'), str(cache)])


def test_importing_the_engine_does_not_import_a_hugging_face_library():
    # review: the AST test above sees only direct imports; this one sees indirect ones too.
    # It needs the engine's own imports (torch, Pillow), so it is skipped in CI.
    pytest.importorskip('torch')
    pytest.importorskip('PIL')
    script = ('import sys, framescout_engine\n'
              "print(sorted(name for name in ('huggingface_hub', 'transformers', 'open_clip', 'timm')"
              ' if name in sys.modules))')
    result = subprocess.run([sys.executable, '-c', script], cwd=ENGINE.parent, capture_output=True, text=True,
                            timeout=300)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == '[]'
