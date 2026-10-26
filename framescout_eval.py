"""FrameScout search-model evaluation (E32, E20): which offered search model ranks best?

A development tool, not part of the app. It works on named collections (a photo folder
plus a profiles file each, e.g. one of cosplay photos and one of outdoor photos), kept in
a folder of their own (default: .tmp/eval/ in the project folder, which git ignores):

  1. run      runs the engine once per search model and keeps the raw scores
              (needs the installed FrameScout; downloads a model's weights on its first use)
  2. pool     pools the top photos of every model per profile: the photos to label
  3. label    opens a local labelling page: match / no match per photo, saved at once
  4. metrics  AP@40 per profile and model, and a sweep of the reference weight

  python framescout_eval.py run cosplay D:/Photos/Convention --profiles profiles.json
  python framescout_eval.py pool cosplay
  python framescout_eval.py label cosplay
  python framescout_eval.py metrics cosplay outdoor

Steps 2-4 need numpy only (no torch), and the labels stay in the collection's folder.
Everything runs locally; the labelling page is served on 127.0.0.1 only.
"""
import argparse
import http.server
import json
import mimetypes
import os
import secrets
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path
from urllib.parse import unquote, urlsplit

import numpy as np

from framescout_core import (DEFAULT_REFERENCE_WEIGHT, DEVICES, EVAL_K, MODEL_KEYS, MODELS,
                             average_precision, build_pool, collection_name_problem, load_profiles, model_problem,
                             read_document, read_labels, read_profiles, read_scores, save_labels, set_label,
                             thumbnail_name, write_document)
from framescout_scoring import rank_photos

ROOT = Path(__file__).resolve().parent
ENGINE = ROOT / 'framescout_engine.py'
PAGE = ROOT / 'framescout_eval_page.html'
DEFAULT_DIR = ROOT / '.tmp' / 'eval'
COLLECTION_FORMAT = 1
POOL_FORMAT = 1
# photos per model and profile that go into the pool: the union of all models is labelled
DEFAULT_DEPTH = 100
# gallery length of the engine runs: their thumbnails are what the labelling page shows
DEFAULT_TOP = 150
DEFAULT_PORT = 8765
SWEEP = tuple(round(step / 10, 1) for step in range(11))
# the reference weights whose rankings go into the pool: text only, the app's default and a
# stronger one, so the sweep around them meets few unlabelled photos
POOL_WEIGHTS = tuple(sorted({0.0, DEFAULT_REFERENCE_WEIGHT, 0.6}))


class UsageError(Exception):
    """A wrong call: printed as an error, exit code 2."""


def weight_key(weight):
    return str(float(weight))


class Collection:
    """The folder of one named evaluation collection inside base."""

    def __init__(self, base, name):
        problem = collection_name_problem(name)
        if problem:
            raise ValueError(problem)
        self.name = name
        self.root = Path(base).resolve() / name
        self.config_file = self.root / 'collection.json'
        self.pool_file = self.root / 'pool.json'
        self.labels_file = self.root / 'labels.json'

    def engine_output(self, model):
        """The engine's output folder for model (galleries, thumbnails, cache); one per model,
        so that a run's thumbnail cleanup never removes the thumbnails of another model."""
        return self.root / 'engine' / model

    def scores_file(self, model):
        return self.root / 'scores' / f'{model}.json'

    def config(self):
        """Return {"folders": [...], "profiles": path} of the collection, or None before its first run.

        ValueError if the file is not a usable collection file (e.g. a key is missing).
        """
        config = read_document(self.config_file, 'collection file', COLLECTION_FORMAT)
        if config is not None and not (isinstance(config.get('folders'), list)
                                       and all(isinstance(f, str) for f in config['folders'])
                                       and isinstance(config.get('profiles'), str)):
            raise ValueError(f'{self.config_file} is not a usable collection file: "folders" or "profiles" '
                             'is missing; delete it and name the photo folder(s) and --profiles again.')
        return config

    def save_config(self, folders, profiles):
        write_document(self.config_file, {'format': COLLECTION_FORMAT, 'folders': [str(f) for f in folders],
                                          'profiles': str(profiles)}, indent=2)

    def scores(self):
        """Return {model: scores document} of the models that have been run, in registry order."""
        folder = self.root / 'scores'
        found = {path.stem: path for path in folder.glob('*.json')} if folder.is_dir() else {}
        order = [key for key in MODEL_KEYS if key in found] + sorted(set(found) - set(MODEL_KEYS))
        return {key: read_scores(found[key]) for key in order}


# --- ranking: the engine's scoring of the saved scores ---

def ranking(document, profile, weight):
    """Return the photo paths of a scores document in the order the engine ranks them for profile.

    The same rank_photos as the engine, over the same per-crop scores (rounded to
    SCORE_DIGITS), sorted by score with ties in scan order like the galleries.
    """
    text = [np.asarray(row, dtype=np.float64) for row in profile['text']]
    visual = None if profile['visual'] is None else [np.asarray(row, dtype=np.float64) for row in profile['visual']]
    _, matches = rank_photos(text, visual, weight)
    order = sorted(range(len(matches)), key=lambda i: matches[i].score, reverse=True)
    return [document['photos'][i]['path'] for i in order]


def profile_entries(scores):
    """Return {profile name: {model: profile entry}} over all scores documents, in first-seen order."""
    entries = {}
    for model, document in scores.items():
        for profile in document['profiles']:
            entries.setdefault(profile['name'], {})[model] = profile
    return entries


def changed_profiles(entries):
    """Names of the profiles whose prompts or reference images differ between the models' runs."""
    return [name for name, models in entries.items()
            if len({json.dumps([p['prompts'], p['references']]) for p in models.values()}) > 1]


def run_warnings(scores):
    """Warnings about model runs that do not compare the same: changed profiles, other photos."""
    warnings = [f'The profile {name} has changed between the model runs; run the models again.'
                for name in changed_profiles(profile_entries(scores))]
    # a photo changed since another model's run has a new mtime_ns (review)
    photo_sets = {model: {(photo['path'], photo['mtime_ns']) for photo in document['photos']}
                  for model, document in scores.items()}
    if len({frozenset(photos) for photos in photo_sets.values()}) > 1:
        counts = ', '.join(f'{model} {len(photos)}' for model, photos in photo_sets.items())
        warnings.append(f'The models scored different photos ({counts}): photos that failed in one run, or the '
                        'photo folders or photos changed; run the models again if the numbers differ much.')
    return warnings


# --- run ---

def engine_env(cache_dir, environ=os.environ):
    """The engine's environment: model downloads and caches where the app keeps them, UTF-8 output."""
    env = dict(environ)
    cache_dir = Path(cache_dir)
    env.update({'TORCH_HOME': str(cache_dir / 'torch'), 'HF_HOME': str(cache_dir / 'huggingface'),
                'YOLO_CONFIG_DIR': str(cache_dir / 'ultralytics'), 'XDG_CACHE_HOME': str(cache_dir),
                'PYTHONIOENCODING': 'utf-8'})
    return env


def engine_command(collection, model, folders, profiles, args):
    command = [sys.executable, str(ENGINE), *[str(f) for f in folders], '--profiles', str(profiles),
               '--output', str(collection.engine_output(model)), '--model', model,
               '--scores-file', str(collection.scores_file(model)), '--device', args.device,
               '--batch-size', str(args.batch_size), '--top', str(args.top)]
    if args.no_person_detection:
        command.append('--no-person-detection')
    return command


def command_run(args):
    collection = Collection(args.dir, args.collection)
    config = collection.config() or {}
    folders = [Path(f).resolve() for f in args.folders] or [Path(f) for f in config.get('folders', [])]
    profiles = Path(args.profiles).resolve() if args.profiles else (Path(config['profiles']) if config else None)
    if not folders or profiles is None:
        raise UsageError(f'The collection {collection.name} is new: name its photo folder(s) and --profiles.')
    missing = [str(f) for f in folders if not f.is_dir()]
    if missing:
        raise UsageError(f'Photo folder not found: {", ".join(missing)}')
    try:
        load_profiles(profiles, [])
    except (OSError, ValueError) as exc:
        raise UsageError(f'The profiles file {profiles} cannot be used: {exc}')
    models = args.models.split(',') if args.models else list(MODEL_KEYS)
    unknown = [m for m in models if m not in MODELS]
    if unknown:
        raise UsageError(f'Unknown search model(s) {", ".join(unknown)}; known: {", ".join(MODEL_KEYS)}')
    if config and (config['folders'] != [str(f) for f in folders] or config['profiles'] != str(profiles)):
        print('Note: the photo folders or the profiles file differ from the previous run of this collection; '
              'run every model again so that their scores compare the same photos.', flush=True)
    collection.save_config(folders, profiles)
    env = engine_env(args.cache_dir)
    failed = []
    for model in models:
        # a model's scores are those of its latest run: a skipped or failed run leaves none,
        # so pool and metrics never compare an older run with the fresh ones (review)
        collection.scores_file(model).unlink(missing_ok=True)
        problem = model_problem(model)
        if problem:
            print(f'Skipped {model}: {problem}', flush=True)
            failed.append(model)
            continue
        print(f'\n=== {collection.name}: {MODELS[model].label} ({model}) ===', flush=True)
        # the engine's own output goes to this console; a model is downloaded on its first use
        done = subprocess.run(engine_command(collection, model, folders, profiles, args), env=env, check=False)
        if done.returncode != 0:
            print(f'The search with {model} failed (exit code {done.returncode}).', flush=True)
            collection.scores_file(model).unlink(missing_ok=True)
            failed.append(model)
    if failed:
        print(f'\nNot scored: {", ".join(failed)}.', flush=True)
        return 1
    print(f'\nScores of {len(models)} model(s) saved in {collection.root / "scores"}. '
          f'Next: python framescout_eval.py pool {collection.name}', flush=True)
    return 0


# --- pool ---

def profile_details(collection):
    """{profile name: (context, features)} from the collection's profiles file, {} if it cannot be read."""
    config = collection.config()
    if not config:
        return {}
    try:
        return {p['name'].strip(): (p.get('franchise', ''), p.get('features', ''))
                for p in read_profiles(Path(config['profiles']))}
    except (OSError, ValueError):
        return {}


def pool_document(collection, scores, depth, weights):
    """The pool file: per profile the union of every model's first depth photos at each weight."""
    entries = profile_entries(scores)
    details = profile_details(collection)
    mtimes = {}
    for document in scores.values():
        mtimes.update({photo['path']: photo['mtime_ns'] for photo in document['photos']})
    profiles = []
    for name, models in entries.items():
        rankings = []
        for model, profile in models.items():
            # the weight only matters with reference images
            for weight in (weights if profile['visual'] is not None else weights[:1]):
                rankings.append(ranking(scores[model], profile, weight))
        context, features = details.get(name, ('', ''))
        references = next(reversed(models.values()))['references']
        profiles.append({'name': name, 'context': context, 'features': features, 'references': references,
                         'photos': [{'path': path, 'mtime_ns': mtimes[path]}
                                    for path in build_pool(rankings, depth, seed=name)]})
    return {'format': POOL_FORMAT, 'depth': depth, 'weights': list(weights), 'models': list(scores),
            'profiles': profiles}


def parse_weights(text):
    try:
        weights = [float(part) for part in text.split(',') if part.strip()]
    except ValueError:
        raise UsageError(f'Invalid weights {text!r}: use numbers from 0 to 1, separated by commas.') from None
    if not weights or not all(0 <= w <= 1 for w in weights):
        raise UsageError(f'Invalid weights {text!r}: use numbers from 0 to 1, separated by commas.')
    return weights


def command_pool(args):
    collection = Collection(args.dir, args.collection)
    scores = collection.scores()
    if not scores:
        raise UsageError(f'No scores in {collection.root}: run "python framescout_eval.py run {collection.name} ..." first.')
    if args.depth < 1:
        raise UsageError('--depth must be at least 1.')
    if args.depth < EVAL_K:
        print(f'Note: with --depth below {EVAL_K}, the top {EVAL_K} of AP@{EVAL_K} holds unlabelled photos.', flush=True)
    weights = parse_weights(args.weights)
    for warning in run_warnings(scores):
        print(f'Warning: {warning}', flush=True)
    document = pool_document(collection, scores, args.depth, weights)
    write_document(collection.pool_file, document, indent=1)
    labels = read_labels(collection.labels_file)
    total = todo = 0
    for profile in document['profiles']:
        done = sum(photo['path'] in labels.get(profile['name'], {}) for photo in profile['photos'])
        total += len(profile['photos']); todo += len(profile['photos']) - done
        print(f'{profile["name"]}: {len(profile["photos"])} photos to label ({done} labelled)', flush=True)
    print(f'Pool of {len(document["models"])} model(s): {total} photos, {todo} still to label '
          f'(about {todo * 1.5 / 60:.0f} min at 1.5 s each). Next: python framescout_eval.py label {collection.name}',
          flush=True)
    return 0


# --- metrics ---

def evaluate(scores, labels, k, weight, sweep):
    """AP@k of every model per profile at weight, their means, and per model the mean AP@k of
    the profiles with reference images at each weight of sweep.

    A photo in a model's top k without a label counts as no match and is counted in
    "unlabelled" (re-run pool with a larger depth or more weights and label it).
    """
    entries = profile_entries(scores)
    result = {'profiles': {}, 'mean': {}, 'sweep': {}, 'sweep_profiles': []}
    for name, models in entries.items():
        marks = labels.get(name, {})
        relevant = {path for path, match in marks.items() if match}
        cells = {}
        for model, profile in models.items():
            ranked = ranking(scores[model], profile, weight)
            cells[model] = {'ap': average_precision(ranked, relevant, k),
                            'unlabelled': sum(path not in marks for path in ranked[:k])}
        result['profiles'][name] = {'hits': len(relevant), 'labelled': len(marks),
                                    'references': bool(next(iter(models.values()))['references']), 'models': cells}
    for model in scores:
        values = [p['models'][model]['ap'] for p in result['profiles'].values()
                  if model in p['models'] and p['models'][model]['ap'] is not None]
        result['mean'][model] = sum(values) / len(values) if values else None
    with_refs = [name for name, models in entries.items() if all(p['visual'] is not None for p in models.values())
                 and any(labels.get(name, {}).values())]
    if sweep and with_refs:
        result['sweep_profiles'] = with_refs
        for model in scores:
            row = {}
            for w in sweep:
                values, unlabelled = [], 0
                for name in with_refs:
                    if model not in entries[name]:
                        continue
                    ranked = ranking(scores[model], entries[name][model], w)
                    marks = labels[name]
                    values.append(average_precision(ranked, {p for p, match in marks.items() if match}, k))
                    unlabelled += sum(path not in marks for path in ranked[:k])
                values = [v for v in values if v is not None]
                row[weight_key(w)] = {'ap': sum(values) / len(values) if values else None, 'unlabelled': unlabelled}
            result['sweep'][model] = row
    return result


def cell(value, unlabelled=0, mark=''):
    return ('–' if value is None else f'{value:.3f}') + mark + (f' ({unlabelled} unlabelled)' if unlabelled else '')


def table(header, rows):
    lines = ['| ' + ' | '.join(header) + ' |', '|' + '---|' * len(header)]
    lines += ['| ' + ' | '.join(row) + ' |' for row in rows]
    return '\n'.join(lines)


def report(name, result, k, weight, models):
    """The Markdown tables of one collection's result."""
    lines = [f'## {name}: AP@{k} at reference weight {weight:g}', '']
    rows = []
    for profile, data in result['profiles'].items():
        row = [profile + (' (refs)' if data['references'] else ''), f'{data["hits"]}/{data["labelled"]}']
        for model in models:
            entry = data['models'].get(model)
            row.append('n/a' if entry is None else cell(entry['ap'], entry['unlabelled']))
        rows.append(row)
    rows.append(['**Mean**', ''] + [cell(result['mean'].get(model)) for model in models])
    lines.append(table(['Profile', 'Hits/labelled'] + models, rows))
    unlabelled = any(entry['unlabelled'] for data in result['profiles'].values() for entry in data['models'].values())
    if result['sweep']:
        lines += ['', f'Reference weight: mean AP@{k} of {len(result["sweep_profiles"])} profile(s) with reference '
                  f'images ({", ".join(result["sweep_profiles"])}); * = best per model', '']
        sweep = {model: result['sweep'].get(model, {}) for model in models}
        weights = list(next(iter(result['sweep'].values())))
        best = {model: max((v['ap'] for v in row.values() if v['ap'] is not None), default=None)
                for model, row in sweep.items()}
        rows = []
        for w in weights:
            row = [w]
            for model in models:
                entry = sweep[model].get(w)
                row.append('n/a' if entry is None else cell(
                    entry['ap'], entry['unlabelled'], '*' if entry['ap'] is not None and entry['ap'] == best[model] else ''))
            rows.append(row)
        lines.append(table(['Weight'] + models, rows))
        unlabelled = unlabelled or any(v['unlabelled'] for row in sweep.values() for v in row.values())
    if unlabelled:
        lines += ['', 'Unlabelled photos in a top list count as no match: run "pool" again with a larger --depth '
                  'or the --weights used here, and label the new photos.']
    return '\n'.join(lines)


def command_metrics(args):
    weights = parse_weights(args.sweep) if args.sweep else []
    if not 0 <= args.weight <= 1 or args.k < 1:
        raise UsageError('--weight must be from 0 to 1 and --k at least 1.')
    results, models = {}, []
    for name in args.collections:
        collection = Collection(args.dir, name)
        scores = collection.scores()
        if not scores:
            raise UsageError(f'No scores in {collection.root}.')
        for warning in run_warnings(scores):
            print(f'Warning: {name}: {warning}', flush=True)
        results[name] = evaluate(scores, read_labels(collection.labels_file), args.k, args.weight, weights)
        models += [model for model in scores if model not in models]
    for name, result in results.items():
        print(report(name, result, args.k, args.weight, models) + '\n', flush=True)
    if len(results) > 1:
        overall = {}
        for model in models:
            values = [p['models'][model]['ap'] for r in results.values() for p in r['profiles'].values()
                      if model in p['models'] and p['models'][model]['ap'] is not None]
            overall[model] = sum(values) / len(values) if values else None
        print(f'## All collections: mean AP@{args.k} over every profile with hits\n', flush=True)
        print(table(['Collections'] + models, [[', '.join(results)] + [cell(overall[m]) for m in models]]), flush=True)
    if args.json:
        write_document(Path(args.json), {'k': args.k, 'weight': args.weight, 'collections': results}, indent=1)
        print(f'\nMetrics saved: {Path(args.json).resolve()}', flush=True)
    return 0


# --- labelling page ---

class LabelSession:
    """The labelling page of one collection: its pool, its labels and the routes of the local server.

    Every route starts with a random token, so other web pages cannot read or change the
    labels through the browser. A label is saved to labels.json as soon as it is set.
    """

    def __init__(self, collection):
        self.collection = collection
        self.pool = read_document(collection.pool_file, 'pool file', POOL_FORMAT)
        if self.pool is None:
            raise UsageError(f'No pool in {collection.root}: run "python framescout_eval.py pool {collection.name}" first.')
        self.labels = read_labels(collection.labels_file)  # ValueError: never saved over
        self.token = secrets.token_urlsafe(16)
        self.lock = threading.Lock()
        self.thumb_folders = [collection.engine_output(model) / 'thumbnails' for model in self.pool['models']]

    def state(self):
        profiles = []
        for profile in self.pool['profiles']:
            marks = self.labels.get(profile['name'], {})
            profiles.append({'name': profile['name'], 'context': profile['context'], 'features': profile['features'],
                             'references': len(profile['references']),
                             'photos': [{'name': Path(p['path']).name, 'folder': str(Path(p['path']).parent)}
                                        for p in profile['photos']],
                             'labels': [marks.get(p['path']) for p in profile['photos']]})
        return {'collection': self.collection.name, 'profiles': profiles}

    def entry(self, profile, index, key):
        """The pool profile number profile and its item number index of the list key, or None."""
        try:
            profile, index = int(profile), int(index)
            if profile < 0 or index < 0:
                return None
            return self.pool['profiles'][profile], self.pool['profiles'][profile][key][index]
        except (ValueError, IndexError):
            return None

    def image(self, path, thumbnail=None):
        path = Path(path)
        if thumbnail:
            for folder in self.thumb_folders:
                candidate = folder / thumbnail
                if candidate.is_file():
                    return 200, 'image/jpeg', candidate.read_bytes()
        try:
            data = path.read_bytes()
        except OSError:
            return 404, 'text/plain', b'not found'
        return 200, mimetypes.guess_type(path.name)[0] or 'application/octet-stream', data

    def label(self, body):
        try:
            request = json.loads(body)
            found = self.entry(request['profile'], request['photo'], 'photos')
            value = request['value']
            if found is None or (value is not None and not isinstance(value, bool)):
                raise ValueError
        except (ValueError, TypeError, KeyError):
            return 400, 'application/json', b'{"ok": false}'
        profile, photo = found
        with self.lock:
            labels = set_label(self.labels, profile['name'], photo['path'], value)
            save_labels(self.collection.labels_file, labels)
            self.labels = labels
        return 200, 'application/json', b'{"ok": true}'

    def handle(self, method, target, body):
        """Answer one request: (status, content type, body)."""
        parts = unquote(urlsplit(target).path).split('/')
        if len(parts) < 2 or parts[1] != self.token:
            return 404, 'text/plain', b'not found'
        route = parts[2:]
        if method == 'POST':
            return self.label(body) if route == ['label'] else (404, 'text/plain', b'not found')
        if route == []:  # without the trailing slash the page's relative links would miss the token
            return 200, 'text/html; charset=utf-8', f'<meta http-equiv="refresh" content="0; url={self.token}/">'.encode()
        if route == ['']:
            return 200, 'text/html; charset=utf-8', PAGE.read_bytes()
        if route == ['state']:
            return 200, 'application/json', json.dumps(self.state(), ensure_ascii=False).encode('utf-8')
        if len(route) == 3 and route[0] in ('photo', 'original'):
            found = self.entry(route[1], route[2], 'photos')
            if found:
                photo = found[1]
                thumb = thumbnail_name(Path(photo['path']), photo['mtime_ns']) if route[0] == 'photo' else None
                return self.image(photo['path'], thumb)
        if len(route) == 3 and route[0] == 'reference':
            found = self.entry(route[1], route[2], 'references')
            if found:
                return self.image(found[1])
        return 404, 'text/plain', b'not found'


def serve(session, port, open_browser):
    class Handler(http.server.BaseHTTPRequestHandler):
        def answer(self, method, body=b''):
            status, kind, data = session.handle(method, self.path, body)
            self.send_response(status)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store' if kind.startswith(('application/json', 'text/'))
                             else 'max-age=3600')
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self.answer('GET')

        def do_POST(self):
            length = int(self.headers.get('Content-Length') or 0)
            self.answer('POST', self.rfile.read(min(length, 10_000)))

        def log_message(self, *args):  # no line per photo in the console
            pass

    server = http.server.ThreadingHTTPServer(('127.0.0.1', port), Handler)
    url = f'http://127.0.0.1:{server.server_address[1]}/{session.token}/'
    print(f'Labelling page of {session.collection.name}: {url}\nLabels are saved in {session.collection.labels_file}. '
          'Stop with Ctrl+C.', flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('Stopped.', flush=True)
    finally:
        server.server_close()


def command_label(args):
    session = LabelSession(Collection(args.dir, args.collection))
    serve(session, args.port, not args.no_browser)
    return 0


# --- command line ---

def parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--dir', type=Path, default=DEFAULT_DIR,
                        help=f'folder of the collections (default: {DEFAULT_DIR})')
    main = argparse.ArgumentParser(description='Evaluate the search models of FrameScout on your own labelled photos.')
    commands = main.add_subparsers(dest='command', required=True)
    run = commands.add_parser('run', parents=[common], help='run the engine once per search model')
    run.add_argument('collection', help='name of the collection, e.g. cosplay or outdoor')
    run.add_argument('folders', nargs='*', help='photo folder(s); default: those of the previous run')
    run.add_argument('--profiles', help='profiles JSON file; default: that of the previous run')
    run.add_argument('--models', help=f'comma-separated search models (default: all: {",".join(MODEL_KEYS)})')
    run.add_argument('--device', choices=DEVICES, default='auto')
    run.add_argument('--batch-size', type=int, default=8)
    run.add_argument('--top', type=int, default=DEFAULT_TOP,
                     help='gallery length per model; their thumbnails are shown on the labelling page')
    run.add_argument('--no-person-detection', action='store_true')
    run.add_argument('--cache-dir', type=Path, default=ROOT / '.cache',
                     help='model downloads and caches (default: the app\'s .cache folder)')
    run.set_defaults(handler=command_run)
    pool = commands.add_parser('pool', parents=[common], help='pool the top photos of every model for labelling')
    pool.add_argument('collection')
    pool.add_argument('--depth', type=int, default=DEFAULT_DEPTH, help='photos per model and profile')
    pool.add_argument('--weights', default=','.join(map(str, POOL_WEIGHTS)),
                      help='reference weights whose rankings go into the pool for profiles with reference images '
                           f'(default: {",".join(map(str, POOL_WEIGHTS))})')
    pool.set_defaults(handler=command_pool)
    label = commands.add_parser('label', parents=[common], help='open the labelling page')
    label.add_argument('collection')
    label.add_argument('--port', type=int, default=DEFAULT_PORT)
    label.add_argument('--no-browser', action='store_true')
    label.set_defaults(handler=command_label)
    metrics = commands.add_parser('metrics', parents=[common], help='AP per profile and model')
    metrics.add_argument('collections', nargs='+')
    metrics.add_argument('--k', type=int, default=EVAL_K, help='cut-off of the average precision')
    metrics.add_argument('--weight', type=float, default=DEFAULT_REFERENCE_WEIGHT, help='reference weight')
    metrics.add_argument('--sweep', default=','.join(map(str, SWEEP)),
                         help='reference weights to compare (empty: no sweep)')
    metrics.add_argument('--json', help='also save the numbers to this JSON file')
    metrics.set_defaults(handler=command_metrics)
    return main


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        return args.handler(args)
    except (UsageError, ValueError) as exc:
        print(f'framescout_eval.py: error: {exc}', file=sys.stderr, flush=True)
        return 2
    except KeyboardInterrupt:  # e.g. Ctrl+C during a model run: the cache keeps what was analyzed
        print('\nInterrupted. Run the same command again to continue.', file=sys.stderr, flush=True)
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
