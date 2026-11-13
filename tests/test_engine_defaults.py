"""The engine's CLI defaults that must match the app's (read from the source: the engine imports torch)."""
import ast
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from framescout_core import RUN_STATUS, cache_paths, default_cache_env, engine_cache_env, read_status

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


def test_the_app_keeps_the_cache_variables_a_user_set(tmp_path):
    # A36: the engine the app starts gets them as a manual run does (engine_cache_env), not
    # all of cache_paths over the user's values
    tree = ast.parse(APP.read_text(encoding='utf-8'))
    [cache_env] = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == 'cache_env']
    stored = {ast.unparse(node.slice) for node in ast.walk(cache_env)
              if isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Store)}
    assert stored == {"'TMP'", "'TEMP'", "'PYTHONIOENCODING'"}
    # run app.cache_env itself on a project folder in tmp_path: the cache variables are those
    # of engine_cache_env, and only the folders default_cache_env set are created (review)
    own = tmp_path / 'own-hf'
    environ = {'PATH': 'x', 'HF_HOME': str(own)}
    namespace = {'os': SimpleNamespace(environ=environ), 'BASE': tmp_path, 'cache_paths': cache_paths,
                 'default_cache_env': default_cache_env}
    exec(compile(ast.Module(body=[cache_env], type_ignores=[]), str(APP), 'exec'), namespace)
    env = namespace['cache_env']()
    temp = str(tmp_path / '.tmp')
    assert env == {**engine_cache_env(environ, tmp_path), 'TMP': temp, 'TEMP': temp, 'PYTHONIOENCODING': 'utf-8'}
    assert environ == {'PATH': 'x', 'HF_HOME': str(own)}
    assert sorted(p.name for p in (tmp_path / '.cache').iterdir()) == ['torch', 'ultralytics']
    assert (tmp_path / '.tmp').is_dir() and not own.exists()


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
    [scores] = [node.lineno for node in ast.walk(search)
                if isinstance(node, ast.Call) and getattr(node.func, 'id', '') == 'write_scores']
    thumbs = min(node.lineno for node in ast.walk(search) if isinstance(node, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == 'thumbs' for t in node.targets))
    assert scores < thumbs


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


def test_the_engine_sets_the_cache_folders_in_main_not_on_import():
    # I10: a manual run keeps the model downloads and config files under the project's .cache;
    # E42: set in main(), so importing the engine changes no variable of the importer.
    # huggingface_hub and Ultralytics, which read them on import, are imported later in main()
    # (import_open_clip, import_detector_class; tests above)
    tree = ast.parse(ENGINE.read_text(encoding='utf-8'))
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and getattr(node.func, 'id', None) == 'default_cache_env']
    assert len(calls) == 1, 'the engine must call default_cache_env once'
    assert ast.unparse(calls[0]) == 'default_cache_env(os.environ, Path(__file__).resolve().parent)'
    [main] = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'main']
    first = main.body[0]
    assert isinstance(first, ast.Expr) and first.value is calls[0], 'main() must call default_cache_env first'


def test_the_engine_loads_the_detector_weights_from_the_cache():
    # E9: YOLO('yolo11n.pt') downloads into the working folder; the cache signature keeps the name
    nodes = list(ast.walk(ast.parse(ENGINE.read_text(encoding='utf-8'))))
    [detector] = [node for node in nodes if isinstance(node, ast.Call) and getattr(node.func, 'id', None) == 'YOLO']
    assert ast.unparse(detector) == ('YOLO(yolo_weights(args.yolo_model, Path(__file__).resolve().parent, Path.cwd(), '
                                     'os.environ, lambda text: print(text, flush=True)))')
    [prepare] = [node for node in nodes if isinstance(node, ast.Call) and getattr(node.func, 'id', None) == 'prepare_cache']
    assert 'args.yolo_model' in [ast.unparse(arg) for arg in prepare.args]


def test_the_engine_sets_the_unset_cache_variables_when_it_runs():
    # E42: importing the engine changes none of them, main() sets the unset ones and keeps a
    # value the user set; torch, imported before, reads them only when it uses them. Needs
    # the engine's own imports (torch, Pillow), so it is skipped in CI
    pytest.importorskip('torch')
    pytest.importorskip('PIL')
    names = ('TORCH_HOME', 'HF_HOME', 'YOLO_CONFIG_DIR', 'XDG_CACHE_HOME')
    env = {k: v for k, v in os.environ.items() if k.upper() not in names}
    env['HF_HOME'] = str(ENGINE.parent / '.tmp' / 'own-hf')  # set by the user: kept
    script = ('import contextlib, io, os, sys, torch, framescout_engine\n'
              f'names = {names!r}\n'
              'print([os.environ.get(n) for n in names])\n'
              "sys.argv = ['framescout_engine.py', '--help']\n"
              'with contextlib.suppress(SystemExit), contextlib.redirect_stdout(io.StringIO()):\n'
              '    framescout_engine.main()\n'
              'print([os.environ.get(n) for n in names])\n'
              'print(torch.hub.get_dir())\n')
    result = subprocess.run([sys.executable, '-c', script], cwd=ENGINE.parent, capture_output=True, text=True,
                            timeout=300, env=env)
    assert result.returncode == 0, result.stderr
    cache = ENGINE.parent / '.cache'
    assert result.stdout.strip().splitlines()[-3:] == [
        repr([None, env['HF_HOME'], None, None]),
        repr([str(cache / 'torch'), env['HF_HOME'], str(cache / 'ultralytics'), str(cache)]),
        str(cache / 'torch' / 'hub')]


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


def test_the_engine_opens_the_cache_before_it_loads_the_model():
    # E56: a damaged cache is reported at once (E50), not after the seconds (or the first
    # download) of the model load
    search = next(node for node in ast.walk(ast.parse(ENGINE.read_text(encoding='utf-8')))
                  if isinstance(node, ast.FunctionDef) and node.name == 'search')
    lines = {}
    for node in ast.walk(search):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            lines.setdefault(node.func.id, node.lineno)
    assert lines['prepare_cache'] < lines['import_open_clip'] < lines['load_with_hub_fallback']


def test_the_engine_closes_the_cache_if_the_model_or_a_reference_fails_to_load():
    # E56 review: the cache opened before the model load is closed again if the cache check,
    # the model load or a reference image fails, so the file is not left open (locked on
    # Windows)
    search = next(node for node in ast.walk(ast.parse(ENGINE.read_text(encoding='utf-8')))
                  if isinstance(node, ast.FunctionDef) and node.name == 'search')
    guarded = []
    for node in ast.walk(search):
        if not isinstance(node, ast.Try):
            continue
        closes = any(isinstance(handler.type, ast.Name) and handler.type.id == 'BaseException'
                     and 'con.close()' in ast.unparse(handler) and isinstance(handler.body[-1], ast.Raise)
                     for handler in node.handlers)
        if closes:
            guarded.append({call.func.id for part in node.body for call in ast.walk(part)
                            if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)})
    assert any({'prepare_cache', 'load_with_hub_fallback', 'open_image'} <= calls for calls in guarded)


def search_node():
    return next(node for node in ast.walk(ast.parse(ENGINE.read_text(encoding='utf-8')))
                if isinstance(node, ast.FunctionDef) and node.name == 'search')


def called(node):
    """The names of the functions and methods node calls (e.g. 'prepare_cache', 'get' of detector.get())."""
    return [getattr(call.func, 'id', getattr(call.func, 'attr', None))
            for call in ast.walk(node) if isinstance(call, ast.Call)]


def quick_test(node, negated=False):
    """Whether node is "if quick:" (negated: "if not quick:")."""
    test = node.test if isinstance(node, ast.If) else None
    if negated:
        return isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not) and quick_test(ast.If(test=test.operand))
    return isinstance(test, ast.Name) and test.id == 'quick'


def test_the_engine_offers_a_quick_search_without_profiles():
    # F10: the option is additive and off by default; the text is taken as one argument
    default = option_default_node('--quick-query')
    assert default is None or (isinstance(default, ast.Constant) and default.value is None)
    keywords = {k.arg: ast.unparse(k.value) for k in add_argument_call('--quick-query').keywords}
    assert 'nargs' not in keywords and 'action' not in keywords
    search = search_node()
    # the profile of the text, never together with --profiles or --character
    [branch] = [node for node in ast.walk(search) if quick_test(node) and 'quick_profile' in called(node)]
    [call] = [node for node in ast.walk(branch)
              if isinstance(node, ast.Call) and getattr(node.func, 'id', '') == 'quick_profile']
    assert ast.unparse(call.args[0]) == 'args.quick_query'
    [refused] = [node for node in branch.body if isinstance(node, ast.If)
                 and {'args.profiles', 'args.character'} <= {ast.unparse(n) for n in ast.walk(node.test)}]
    assert 'error' in called(refused)


def test_a_quick_search_checks_the_cache_before_it_loads_the_model():
    # F10 review: a folder with nothing analyzed fails at once, not after the seconds (or the
    # first download) of loading the model; the cache check reuses the engine's analyzed()
    search = search_node()
    [branch] = [node for node in ast.walk(search) if quick_test(node) and 'quick_photos' in called(node)]
    [call] = [node for node in ast.walk(branch) if isinstance(node, ast.Call) and getattr(node.func, 'id', '') == 'quick_photos']
    assert isinstance(call.args[2], ast.Name) and call.args[2].id == 'analyzed'
    lines = {}
    for node in ast.walk(search):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            lines.setdefault(node.func.id, node.lineno)
    assert lines['prepare_cache'] < call.lineno < lines['import_open_clip'] < lines['load_with_hub_fallback']


def test_a_quick_search_analyzes_nothing():
    # F10: no detector, no analysis: every analysis call is under "if not quick:"
    search = search_node()
    guarded = {id(node) for branch in ast.walk(search) if quick_test(branch, negated=True)
               for node in ast.walk(branch)}
    for node in ast.walk(search):
        if isinstance(node, ast.Call) and getattr(node.func, 'id', getattr(node.func, 'attr', None)) in (
                'to_analyze', 'store_group', 'choose', 'retry'):
            assert id(node) in guarded, ast.unparse(node)


def test_a_quick_search_writes_into_its_own_folder():
    # F10: the galleries, results.json and marks.json of the profiles stay untouched, and the
    # cleanup after it looks only at the quick folder: both write into target, which is the
    # QUICK_DIR folder in the output folder for a quick search
    search = search_node()
    [target] = [node.value for node in ast.walk(search) if isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == 'target' for t in node.targets)]
    assert isinstance(target, ast.IfExp) and isinstance(target.test, ast.Name) and target.test.id == 'quick'
    assert {'output', 'QUICK_DIR'} <= {n.id for n in ast.walk(target.body) if isinstance(n, ast.Name)}
    assert isinstance(target.orelse, ast.Name) and target.orelse.id == 'output'
    writers = [node for node in ast.walk(search) if isinstance(node, ast.Call)
               and getattr(node.func, 'id', '') in ('publish_export', 'auto_cleanup')]
    assert {node.func.id for node in writers} == {'publish_export', 'auto_cleanup'}
    assert all(isinstance(node.args[0], ast.Name) and node.args[0].id == 'target' for node in writers)


def like_test(node, negated=False):
    """Whether node is "if like:" (negated: "if not like:")."""
    test = node.test if isinstance(node, ast.If) else None
    if negated:
        return isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not) and like_test(ast.If(test=test.operand))
    return isinstance(test, ast.Name) and test.id == 'like'


def test_the_engine_offers_find_similar_as_a_quick_search():
    # F11: additive options, off by default, one argument each; "Find similar" is a quick
    # search (quick is true), so it analyzes nothing and writes into the quick folder
    for option in ('--like', '--like-part'):
        default = option_default_node(option)
        assert default is None or (isinstance(default, ast.Constant) and default.value is None)
        keywords = {k.arg: ast.unparse(k.value) for k in add_argument_call(option).keywords}
        assert 'nargs' not in keywords and 'action' not in keywords
    search = search_node()
    assigned = {node.targets[0].id: ast.unparse(node.value) for node in ast.walk(search)
                if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id in ('like', 'quick')}
    assert assigned == {'like': 'args.like is not None', 'quick': 'args.quick_query is not None or like'}
    [branch] = [node for node in ast.walk(search) if quick_test(node) and 'quick_profile' in called(node)]
    assert 'like_profile' in called(branch)


def test_find_similar_reads_its_photo_before_and_instead_of_the_model_load():
    # F11: its query is the photo's cached vector, so no model is loaded; a photo without a
    # current cache row fails at once (never analyzed silently)
    search = search_node()
    [branch] = [node for node in ast.walk(search) if quick_test(node) and 'quick_photos' in called(node)]
    assert 'like_crop' in called(branch)
    [call] = [node for node in ast.walk(branch) if isinstance(node, ast.Call)
              and getattr(node.func, 'id', '') == 'quick_photos']
    assert [k.arg for k in call.keywords] == ['exclude']
    unloaded = {id(node) for test in ast.walk(search) if like_test(test) for part in test.orelse
                for node in ast.walk(part)}
    loads = [node for node in ast.walk(search) if isinstance(node, ast.Call)
             and getattr(node.func, 'id', '') in ('import_open_clip', 'load_with_hub_fallback')]
    assert loads and all(id(node) in unloaded for node in loads)


def test_find_similar_uses_no_name_of_the_model_load():
    # review: the names the model load defines (the model and the input size of a photo
    # analysis) are only used where a model was loaded, never on the "Find similar" path
    search = search_node()
    branches = [part for test in ast.walk(search) for part in
                (test.orelse if like_test(test) else test.body if like_test(test, negated=True) else [])]
    guarded = {id(node) for part in branches for node in ast.walk(part)}
    uses = [node for node in ast.walk(search) if isinstance(node, ast.Name) and node.id in ('model', 'image_size')]
    assert uses and all(id(node) in guarded for node in uses)


def test_the_engine_names_the_closest_search_text_of_each_card():
    # F17: rank_photos gets each crop's best query (no ranking change, tests/test_scoring.py),
    # and the cards of results.json and the HTML gallery name the closest text
    calls = {}
    for node in ast.walk(search_node()):
        if isinstance(node, ast.Call):
            calls.setdefault(getattr(node.func, 'id', getattr(node.func, 'attr', None)), []).append(node)
    # review: the values of the profile at hand flow through, not only the keyword names
    [rank] = calls['rank_photos']
    assert [(k.arg, ast.unparse(k.value)) for k in rank.keywords] == [('best', 'best_queries.get(name)')]
    [card] = calls['result_card']
    assert [(k.arg, ast.unparse(k.value)) for k in card.keywords] == [('best_query', 'best_query')]
    [closest] = calls['closest_query']
    assert [ast.unparse(a) for a in closest.args] == ['match.query', 'query_names[name]']
    [labels] = calls['query_labels']
    assert [ast.unparse(a) for a in labels.args] == ['p']
    assert 'query_caption' in calls


def test_the_engine_keeps_the_closest_texts_only_where_a_card_names_them():
    # review: a profile with a single text ("Find similar" has none) names no closest text,
    # so its per-crop indexes are not kept for the whole run
    assigned = {target.id: node for node in ast.walk(search_node()) if isinstance(node, ast.Assign)
                for target in node.targets if isinstance(target, ast.Name)}
    best, names = assigned['best_queries'], assigned['query_names']
    assert names.lineno < best.lineno
    assert ast.unparse(best.value) == "{name: [] for name, texts in query_names.items() if len(texts) > 1}"
    [append] = [node for node in ast.walk(search_node()) if isinstance(node, ast.If)
                and any('best_queries[name].append' in ast.unparse(part) for part in node.body)]
    assert ast.unparse(append.test) == 'name in best_queries'


def analyze_test(node):
    """Whether node is "if analyze_only:"."""
    return isinstance(node, ast.If) and isinstance(node.test, ast.Name) and node.test.id == 'analyze_only'


def test_the_engine_offers_an_analysis_without_a_search():
    # F18: an additive switch, off by default, never together with a search
    keywords = {k.arg: ast.unparse(k.value) for k in add_argument_call('--analyze-only').keywords}
    assert keywords.get('action') == "'store_true'"
    search = search_node()
    assigned = [ast.unparse(node.value) for node in ast.walk(search) if isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == 'analyze_only' for t in node.targets)]
    assert assigned == ['args.analyze_only']
    [branch] = [node for node in ast.walk(search) if analyze_test(node) and 'error' in called(node)]
    [refused] = [node for node in branch.body if isinstance(node, ast.If) and 'error' in called(node)]
    assert {'args.profiles', 'args.character', 'args.quick_query', 'like', 'args.scores_file'} <= {
        ast.unparse(n) for n in ast.walk(refused.test)}
    # no profile: no search text is encoded and no reference image read
    assert any(ast.unparse(node) == 'profiles = []' for node in branch.body)
    # the analysis itself is the one of a search: quick is false
    assert not any(analyze_test(node) for node in ast.walk(search) if quick_test(node, negated=True))


def test_an_analysis_stops_before_scoring_and_export():
    # F18: results.json, the galleries, the marks and the scores file stay as they are
    search = search_node()
    stops = [node for node in ast.walk(search) if analyze_test(node)
             and any(isinstance(part, ast.Return) for part in node.body)]
    assert len(stops) == 1
    [stop] = stops
    assert 'close' in called(stop)  # the cache file is not left open
    # cached_features of "Find similar" is read before the analysis, in the quick branch
    quick = {id(node) for branch in ast.walk(search) if quick_test(branch) for part in branch.body
             for node in ast.walk(part)}
    later = [node.lineno for node in ast.walk(search) if isinstance(node, ast.Call) and id(node) not in quick
             and (getattr(node.func, 'id', '') in ('cached_features', 'write_scores', 'publish_export', 'auto_cleanup')
                  or ast.unparse(node).startswith("status.update('scoring'"))]
    assert len(later) >= 5 and stop.lineno < min(later)


def test_the_status_of_an_analysis_says_so_from_its_first_phase():
    # F18: the app names it an analysis, not a search (framescout_core.analysis_only)
    main = next(node for node in ast.walk(ast.parse(ENGINE.read_text(encoding='utf-8')))
                if isinstance(node, ast.FunctionDef) and node.name == 'main')
    [scanning] = [node for node in ast.walk(main) if isinstance(node, ast.Call)
                  and ast.unparse(node).startswith("status.update('scanning'")]
    assert "'analyze_only': True" in ast.unparse(scanning) and 'args.analyze_only' in ast.unparse(scanning)


@pytest.mark.parametrize('extra', [['--profiles', 'p.json'], ['--character', 'Red car'], ['--quick-query=dog'],
                                   ['--scores-file', 'scores.json']])
def test_an_analysis_refuses_a_search_and_says_so_in_its_status(tmp_path, extra):
    # F18: runs the engine up to its argument check (no model load); needs the engine's own
    # imports (torch, Pillow), so it is skipped in CI
    pytest.importorskip('torch')
    pytest.importorskip('PIL')
    photos, output = tmp_path / 'photos', tmp_path / 'results'
    photos.mkdir()
    env = engine_cache_env(dict(os.environ), ENGINE.parent)
    result = subprocess.run([sys.executable, str(ENGINE), str(photos), '--analyze-only', *extra, '--output', str(output)],
                            cwd=tmp_path, capture_output=True, text=True, timeout=300, env=env)
    assert result.returncode == 2, result.stderr
    assert '--analyze-only analyzes the photos without a search' in result.stderr
    status = read_status(output / RUN_STATUS)
    assert status['phase'] == 'failed' and status['analyze_only'] is True
    assert status['message'].startswith('--analyze-only')
    assert not (output / 'results.json').exists()
