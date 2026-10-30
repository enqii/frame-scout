"""FrameScout: local image search with CLIP and optional person detection.

Search profiles are kept in profiles.json. Reference images are optional.
The first model start needs internet access; your own images are never uploaded.
"""
import argparse
import html
import importlib
import io
import json
import os
import sqlite3
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from framescout_core import (CACHE_FILE, DEFAULT_MODEL, DEFAULT_REFERENCE_WEIGHT, DEFAULT_YOLO_MODEL,
                             DEVICES, DRAFT_REDUCING_GAP, FULL_IMAGE_LABEL, MODEL_KEYS, MODELS, RAW_EXT, RUN_LOCK,
                             RUN_STATUS, RunLock, StatusReporter, auto_cleanup, available_decoders, crop_label,
                             cuda_hint, default_cache_env, detection_options, distinct_folders, draft_size,
                             final_status, yolo_weights,
                             SkippedPhotos, folder_labels, gallery_cards, group_batches, hub_go_online, import_detector_class,
                             import_open_clip, load_with_hub_fallback,
                             load_profiles, missing_decoder, missing_folders_message, model_problem,
                             output_folder_problem, photo_name,
                             prefetch,
                             prepare_cache, profile_slugs, progress_due, publish_export,
                             progress_line, raw_preview_transpose, raw_preview_usable, result_card, results_document,
                             scan_folders, scores_document, search_fingerprint, size_text, skipped_lines,
                             store_group, supported_extensions, write_scores)

# model downloads and library config files go to the project's .cache folder, as with the
# .bat files and the app, also for a manual run; a variable the user set is kept (I10).
# Before torch, huggingface_hub and Ultralytics are imported: they read them on import.
default_cache_env(os.environ, Path(__file__).resolve().parent)

import numpy as np
import torch
from PIL import Image, ImageOps, ImageFile

from framescout_scoring import photo_scores, rank_photos, score_caption, text_queries

# AVIF, HEIC/HEIF and camera RAW photos (E25). pillow-heif and rawpy are in
# requirements.txt; an older installation without them still runs and skips those photos
# with a note. The app checks the same way (available_decoders), so both agree (review).
DECODERS = available_decoders()
if DECODERS.heif:
    from pillow_heif import register_heif_opener
    register_heif_opener()
if DECODERS.raw:
    import rawpy

Image.MAX_IMAGE_PIXELS = 160_000_000
ImageFile.LOAD_TRUNCATED_IMAGES = True
# EXIF tag of the image orientation
ORIENTATION = 0x0112
# Photos are decoded in threads ahead of CLIP (E2). Pillow releases the GIL while it
# decodes; more threads would mostly compete with PyTorch for the same CPU cores.
DECODE_THREADS = min(4, os.cpu_count() or 1)
# With person detection a thread holds a full-resolution photo until the detector, which
# runs one photo at a time (E14), is done with it. Two threads let one photo be decoded
# while the other is in the detector, so at most two full-resolution photos are in
# memory; more threads were not faster, they only wait there with a photo each (review).
DETECTION_DECODE_THREADS = 2
THUMBNAIL_SIZE = 380
# How long the engine waits for the run lock of the output folder. The app holds it for a
# moment while it starts the engine or checks whether a search runs; a search that really
# runs holds it for its whole duration.
LOCK_TIMEOUT = 5
# exit code when another search already uses the output folder (A4)
EXIT_BUSY = 3
# explanation of the numbers on the gallery cards (E5)
SCORE_NOTE = ('"Score" says how far the best part of a photo lies above the average image part (whole photo or '
              'person) of this search, in its standard deviations; with reference images it is a weighted mix of '
              'the scaled text and image scores; '
              'the small numbers are its raw similarity with the text and the reference images.')
RAW_NOTE = ('The scores could not be scaled (too few photos or no spread), so "Similarity" is the raw weighted similarity; '
            'the small numbers are its raw similarity with the text and the reference images.')


class Parser(argparse.ArgumentParser):
    """ArgumentParser that remembers its error message for the status file."""
    error_message = None

    def error(self, message):
        self.error_message = message
        super().error(message)


def open_image(path, min_size=None):
    """Open path as an upright RGB image.

    With min_size, a JPEG is decoded at 1/2, 1/4 or 1/8 scale (Image.draft) as long as
    both edges stay at least min_size pixels long; other formats ignore it (E2). A camera
    RAW file is read with open_raw (E25).
    """
    suffix = Path(path).suffix.lower()
    # e.g. a HEIC reference image without pillow-heif: say why instead of a decoder error;
    # other extensions are left to Pillow, as before (a reference image can be any format)
    reason = missing_decoder(suffix, DECODERS)
    if reason:
        raise OSError(reason)
    if suffix in RAW_EXT:
        return open_raw(path, min_size)
    with Image.open(path) as image:
        if min_size:
            image.draft(None, (min_size, min_size))
        return ImageOps.exif_transpose(image).convert('RGB')


def open_raw(path, min_size=None):
    """Open the camera RAW file path as an upright RGB image (E25).

    The preview the camera embedded is used if it is large enough and can be read
    (raw_preview); otherwise the sensor data is decoded at half size with the camera's
    white balance, and LibRaw turns that image upright itself.
    """
    with rawpy.imread(str(path)) as raw:
        preview = raw_preview(raw, min_size)
        if preview is None:
            preview = Image.fromarray(raw.postprocess(half_size=True, use_camera_wb=True, output_bps=8))
    return preview.convert('RGB')


def raw_preview(raw, min_size=None):
    """Return the upright preview embedded in the rawpy file raw, or None if there is no usable one.

    A JPEG or bitmap preview is usable if its longer edge is long enough
    (raw_preview_usable); a JPEG preview is drafted with min_size like any JPEG. A preview
    that cannot be read (corrupt, truncated, unknown format) is not usable either, so the
    caller falls back to the sensor data instead of failing the photo (review).
    """
    try:
        thumb = raw.extract_thumb()
        if thumb.format == rawpy.ThumbFormat.JPEG:
            with Image.open(io.BytesIO(thumb.data)) as image:
                if not raw_preview_usable(*image.size):
                    return None
                if min_size:
                    image.draft(None, (min_size, min_size))
                turn = raw_preview_transpose(image.getexif().get(ORIENTATION), raw.sizes.flip)
                # both load the pixels before the file closes
                image = ImageOps.exif_transpose(image) if turn == 'exif' else image.convert('RGB')
        elif thumb.format == rawpy.ThumbFormat.BITMAP:
            image = Image.fromarray(thumb.data)
            if not raw_preview_usable(*image.size):
                return None
            turn = raw_preview_transpose(None, raw.sizes.flip)
        else:
            return None
        if turn not in (None, 'exif'):
            image = image.transpose(getattr(Image.Transpose, turn))
        return image
    except (rawpy.LibRawError, OSError, ValueError, SyntaxError):
        # LibRawError covers a missing or unsupported thumbnail; Pillow raises OSError
        # (UnidentifiedImageError), ValueError or SyntaxError for broken image data
        return None


def crops_for(image, detector, options, lock):
    """Return [(label, image)]: the whole photo, then each person found with detector.predict(**options)."""
    crops = [(FULL_IMAGE_LABEL, image)]
    if detector is None:
        return crops
    limit = options['max_det']
    with lock:  # one detector instance is shared by the decoding threads
        result = detector.predict(source=image, **options)[0]
    boxes = result.boxes.xyxy.cpu().tolist() if result.boxes is not None else []
    w, h = image.size
    for i, (x1, y1, x2, y2) in enumerate(boxes[:limit], 1):
        px, py = (x2 - x1) * .12, (y2 - y1) * .12
        x1, y1, x2, y2 = max(0, int(x1-px)), max(0, int(y1-py)), min(w, int(x2+px)), min(h, int(y2+py))
        if x2-x1 < 35 or y2-y1 < 70 or (x2-x1)*(y2-y1) > .92*w*h:
            continue
        crops.append((f'Person {i}', image.crop((x1, y1, x2, y2))))
    return crops


def pack(features):
    buf = io.BytesIO()
    np.save(buf, np.asarray(features, dtype=np.float16), allow_pickle=False)
    return buf.getvalue()


def unpack(blob):
    return np.load(io.BytesIO(blob), allow_pickle=False).astype(np.float32)


def main():
    # a character the encoding of a redirected stdout cannot hold (the ANSI code page on
    # Windows, e.g. cp932 for "·" in a model label, or a profile name) is escaped instead of
    # ending the search; the app starts the engine with UTF-8 output (E22 review)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(errors='backslashreplace')
    parser = Parser(description='FrameScout: local image search by name, reference images and optional features.')
    parser.add_argument('folder', type=Path, nargs='+',
                        help='one or more photo folders (subfolders are searched recursively)')
    parser.add_argument('--profiles', type=Path, help='JSON file with search profiles, texts in English (see profiles.example.json)')
    parser.add_argument('--character', action='append', default=[], metavar='NAME|CONTEXT|FEATURES',
                        help='inline search profile in English, can be repeated; e.g. "Red car|Vehicles|red paint, black roof"')
    parser.add_argument('--output', type=Path, default=Path('results'))
    parser.add_argument('--device', choices=DEVICES, default='auto')  # the app offers the same (A8 review)
    parser.add_argument('--batch-size', type=int, default=8)
    parser.add_argument('--top', type=int, default=150)
    parser.add_argument('--no-person-detection', action='store_true')
    parser.add_argument('--max-persons', type=int, default=12)
    parser.add_argument('--person-confidence', type=float, default=.3)
    parser.add_argument('--yolo-model', default=DEFAULT_YOLO_MODEL)
    # E22: the default is the evaluated one; another model analyzes every photo once more and
    # keeps its own cache entries
    parser.add_argument('--model', choices=MODEL_KEYS, default=DEFAULT_MODEL,
                        help='search model (CLIP); models other than the default are slower on a CPU, download '
                             'their weights on first use and are not evaluated yet')
    parser.add_argument('--reference-weight', type=float, default=DEFAULT_REFERENCE_WEIGHT,
                        help='weight of the reference image score (0..1); profiles without reference images use text only')
    # E32: the input of the search-model evaluation (framescout_eval.py); not used by the app
    parser.add_argument('--scores-file', type=Path, default=None, metavar='JSON',
                        help='also write the raw text and reference similarity of every part of every photo '
                             'to this JSON file (for the evaluation tool framescout_eval.py)')
    # the folders may come before, between or after the options, as one folder could (review)
    args = parser.parse_intermixed_args()
    if args.batch_size < 1 or args.top < 1 or args.max_persons < 1 or not (0 < args.person_confidence <= 1) or not (0 <= args.reference_weight <= 1):
        parser.error('Invalid value for batch-size, top, max-persons, person-confidence or reference-weight.')
    listed = [folder.resolve() for folder in args.folder]
    output = args.output.resolve()
    # also refused: a photo folder inside the output folder, which the scan leaves out (review)
    problem = output_folder_problem(listed, output)
    if problem:
        parser.error(problem)
    # a folder listed twice or inside another listed folder is searched once (A25)
    roots, dropped = distinct_folders(listed)
    if not any(root.is_dir() for root in roots) and not output.is_dir():
        # nothing to report to: do not create an output folder (and its lock and status
        # files) for a mistyped call; an existing output folder, like the app's results
        # folder, gets the error in its status file (review)
        parser.error(missing_folders_message(roots))
    output.mkdir(parents=True, exist_ok=True)
    # one search per output folder: two would share cache.sqlite3 ("database is locked")
    # and the app's run.log (A4)
    lock = RunLock(output / RUN_LOCK)
    if not lock.acquire(timeout=LOCK_TIMEOUT):
        print(f'Another FrameScout search is already running with the output folder {output}. '
              'Wait until it has finished or stop it, then start again.', file=sys.stderr, flush=True)
        return EXIT_BUSY
    status = StatusReporter(output / RUN_STATUS, os.getpid())
    try:
        status.update('scanning')
        code = search(args, parser, roots, dropped, output, status)
    except SystemExit as exc:  # parser.error
        status.finish('failed', exc.code if isinstance(exc.code, int) else 1, parser.error_message)
        raise
    except KeyboardInterrupt:
        status.finish('interrupted', 130, 'Interrupted (Ctrl+C).')
        raise
    except BaseException as exc:
        # e.g. a model that cannot be loaded: the traceback goes to the log, the status names the error
        status.finish('failed', 1, f'{type(exc).__name__}: {exc}')
        raise
    else:
        # 0 finished, 130 interrupted, any other code failed (review)
        phase, message = final_status(code)
        status.finish(phase, code, message)
        return code
    finally:
        lock.release()


def search(args, parser, roots, dropped, output, status):
    """Run the search with the run lock of output held; report the phases to status (A5).

    roots: the photo folders to search (distinct_folders' kept list); dropped: the listed
    folders left out, with the reason, for the log.
    """
    for _, note in dropped:
        print(note, flush=True)
    # checked here, not before the lock, so the app's status names the error: a folder
    # can disappear between the click on Start and the engine start. A missing folder of
    # several (e.g. on a disconnected drive) is left out with a note (A25).
    missing = [root for root in roots if not root.is_dir()]
    if len(missing) == len(roots):
        parser.error(missing_folders_message(roots))
    for root in missing:
        print(f'Photo folder not found, searched without it (e.g. a disconnected drive): {root}', flush=True)
    roots = [root for root in roots if root not in missing]
    try:
        profiles = load_profiles(args.profiles.resolve() if args.profiles else None, args.character)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    for p in profiles:
        for ref in p['refs']:
            if not ref.is_file():
                parser.error(f'Reference image not found: {ref}')
    # e.g. SigLIP without transformers: say so before the photos are scanned (E22)
    problem = model_problem(args.model)
    if problem:
        parser.error(problem)
    search_model = MODELS[args.model]
    scan = scan_folders(roots, supported_extensions(DECODERS), exclude=output)
    paths = scan.paths
    # files that are not analyzed are named, not skipped without a note (E25); a missing
    # decoder is named only if the folder has files of it (review)
    for line in skipped_lines(scan, DECODERS):
        print(line, flush=True)
    if not paths:
        parser.error('No supported images found. Please check the local photo folder.')
    device = ('cuda' if torch.cuda.is_available() else 'cpu') if args.device == 'auto' else args.device
    if device == 'cuda' and not torch.cuda.is_available():
        parser.error(f'CUDA is not available; use --device cpu. {cuda_hint(torch.version.cuda)}')
    torch.set_num_threads(min(12, max(1, torch.get_num_threads())))
    status.update('loading')
    print(f'{len(paths)} photos; {len(profiles)} search profiles; search model: {search_model.label} '
          f'({search_model.name}/{search_model.pretrained}); CLIP: {device}; '
          f'person detection (YOLO): {"off" if args.no_person_detection else device}', flush=True)
    print('Model weights are downloaded the first time a model is used.', flush=True)
    # imported here, offline once the model is cached: no Hugging Face Hub request per search
    # and no symlink warning (E16, E31, E33); huggingface_hub reads the variables on import,
    # and its constants are set too if anything imported it earlier
    open_clip, offline = import_open_clip(os.environ, importlib.import_module, search_model, modules=sys.modules)

    def load_model():
        model, _, preprocess = open_clip.create_model_and_transforms(search_model.name,
                                                                     pretrained=search_model.pretrained, device=device)
        return model, preprocess, open_clip.get_tokenizer(search_model.name)

    # an incomplete cache goes online again and downloads what is missing
    model, preprocess, tokenizer = load_with_hub_fallback(load_model, offline,
                                                          lambda: hub_go_online(os.environ, sys.modules),
                                                          lambda text: print(text, flush=True))
    model.eval()

    def embed_pixels(pixels):
        """Embed preprocessed images (one tensor, first dimension = images), batch_size at a time."""
        vectors = []
        with torch.inference_mode():
            for start in range(0, len(pixels), args.batch_size):
                emb = model.encode_image(pixels[start:start+args.batch_size].to(device)).float()
                emb /= emb.norm(dim=-1, keepdim=True).clamp_min(1e-8)
                vectors.append(emb.cpu().numpy())
        return np.concatenate(vectors, axis=0)

    def embed_images(images):
        return embed_pixels(torch.stack([preprocess(im) for im in images]))

    profile_vectors = {}
    with torch.inference_mode():
        for p in profiles:
            t = model.encode_text(tokenizer(p['prompts']).to(device)).float()
            t /= t.norm(dim=-1, keepdim=True).clamp_min(1e-8)
            ref_vectors = []
            for ref in p['refs']:
                try:
                    ref_vectors.append(embed_images([open_image(ref)])[0])
                except Exception as exc:
                    parser.error(f'Reference image cannot be read ({ref}): {exc}')
            # the generated templates are averaged into one query, custom prompts stay apart (E4)
            profile_vectors[p['name']] = (text_queries(t.cpu().numpy(), p['generated']),
                                          np.asarray(ref_vectors, dtype=np.float32) if ref_vectors else None)

    detector = None
    if not args.no_person_detection:
        # without Ultralytics' usage analytics and run-time pip installs (E27, E28)
        YOLO = import_detector_class(os.environ, importlib.import_module, Image)
        # downloaded into .cache on first use, not into the working folder (E9); the cache
        # signature below keeps the name as given
        detector = YOLO(yolo_weights(args.yolo_model, Path(__file__).resolve().parent, Path.cwd(), os.environ,
                                     lambda text: print(text, flush=True)))
    con = sqlite3.connect(output / CACHE_FILE)
    # also records which engine version and settings the signature stands for (E11)
    signature = prepare_cache(con, not args.no_person_detection, args.max_persons, args.person_confidence,
                              args.yolo_model, model=args.model)
    # the registry's input size (tested against the OpenCLIP config) if the model does not name it
    image_size = getattr(model.visual, 'image_size', search_model.image_size)
    min_size = draft_size(max(image_size) if isinstance(image_size, (tuple, list)) else int(image_size),
                          detector is not None)
    detect_lock = threading.Lock()
    # the detector runs on the CLIP device (E14)
    detect_options = detection_options(device, args.max_persons, args.person_confidence)

    def prepare(path):
        """Decode, detect and preprocess one photo; runs in a decoding thread (E2).

        The file is stat-ed right before it is decoded (not in the cache scan, which can be
        long before), so the stored modification time and size belong to the analyzed content.
        """
        stat = path.stat()
        crops = crops_for(open_image(path, min_size), detector, detect_options, detect_lock)
        return stat, [label for label, _ in crops], torch.stack([preprocess(im) for _, im in crops])

    fresh = reused = errors = done = 0

    def finished(new=0, cached=0, failed=0):
        nonlocal fresh, reused, errors, done
        before = done
        fresh, reused, errors = fresh + new, reused + cached, errors + failed
        done = fresh + reused + errors
        if progress_due(before, done, len(paths)):
            print(progress_line(done, len(paths), fresh, reused, errors), flush=True)
        # the status file is written at most once a second, the last photo always (A5)
        status.update(done=done, new=fresh, cached=reused, errors=errors, force=done == len(paths))

    def prepared(todo, pool, ahead):
        """Yield (path, stat, labels, pixels) of the photos in todo; failures are logged and skipped."""
        for path, future in prefetch(lambda item: pool.submit(prepare, item), todo, ahead):
            try:
                stat, labels, pixels = future.result()
            except Exception as exc:
                print(f'ERROR {path}: {exc}', flush=True)
                finished(failed=1)
                continue
            yield path, stat, labels, pixels

    def store(group):
        """Embed the crops of several photos in one go and cache them in one transaction (all or none)."""
        try:
            vectors = embed_pixels(torch.cat([pixels for *_, pixels in group]))
            offsets = np.cumsum([len(labels) for _, _, labels, _ in group])[:-1]
            for (path, stat, labels, _), vec in zip(group, np.split(vectors, offsets)):
                con.execute('INSERT OR REPLACE INTO features VALUES (?,?,?,?,?,?)',
                            (str(path), signature, stat.st_mtime_ns, stat.st_size,
                             json.dumps(labels, ensure_ascii=False), pack(vec)))
            con.commit()
        except BaseException:
            con.rollback()
            raise

    def store_failed(item, exc):
        print(f'ERROR {item[0]}: {exc}', flush=True)
        finished(failed=1)

    status.update('analyzing', total=len(paths))
    try:
        todo = []
        for path in paths:
            try:
                stat = path.stat()
                record = con.execute('SELECT mtime_ns,size FROM features WHERE path=? AND signature=?', (str(path), signature)).fetchone()
            except Exception as exc:
                print(f'ERROR {path}: {exc}', flush=True)
                finished(failed=1)
                continue
            if record == (stat.st_mtime_ns, stat.st_size):
                finished(cached=1)
            else:
                todo.append(path)
        # Photos are decoded (and searched for persons) in threads ahead of CLIP, and the
        # crops of several photos are embedded together, batch_size at a time (E2).
        threads = DECODE_THREADS if detector is None else DETECTION_DECODE_THREADS
        # enough photos ahead for the next group while CLIP embeds the current one (a group
        # holds at most batch_size photos); finished photos wait as small preprocessed
        # tensors, so memory grows with the batch size, not with the photo size (review)
        ahead = max(2 * threads, args.batch_size + threads)
        pool = ThreadPoolExecutor(threads)
        try:
            for group in group_batches(prepared(todo, pool, ahead), args.batch_size, size=lambda item: len(item[2])):
                # after a failure the photos are stored one by one, so only a broken one fails
                finished(new=store_group(group, store, store_failed))
        finally:
            pool.shutdown(cancel_futures=True)  # on an interruption: no new decoding
    except KeyboardInterrupt:
        print('\nInterrupted: images analyzed so far are in the cache. Start again to resume.')
        con.close()
        return 130

    print('Scoring the photos for each search profile ...', flush=True)
    status.update('scoring', total=len(paths))
    # first the per-crop text and reference scores of every photo, then per profile the
    # normalization over all crops of this search and the combination (E4, E5)
    scored, crop_labels, mtimes = [], [], []
    text_scores = {p['name']: [] for p in profiles}
    visual_scores = {p['name']: [] for p in profiles}
    for number, path in enumerate(paths, 1):
        status.update(done=number, force=number == len(paths))
        try:
            stat = path.stat()
            record = con.execute('SELECT mtime_ns,size,labels,vectors FROM features WHERE path=? AND signature=?',
                                 (str(path), signature)).fetchone()
            if record is None or record[:2] != (stat.st_mtime_ns, stat.st_size):
                continue
            labels = json.loads(record[2]); features = unpack(record[3])
            features /= np.maximum(np.linalg.norm(features, axis=1, keepdims=True), 1e-8)
            # a broken row (labels and vectors do not match, scores not finite) is skipped
            photo_text, photo_visual = photo_scores(features, labels, profile_vectors)
        except Exception as exc:
            print(f'CACHE ERROR {path}: {exc}', flush=True)
            continue
        scored.append(path); crop_labels.append(labels); mtimes.append(stat.st_mtime_ns)
        for name in profile_vectors:
            text_scores[name].append(photo_text[name])
            if name in photo_visual:
                visual_scores[name].append(photo_visual[name])
    con.close()
    if args.scores_file:
        # the same per-crop scores rank_photos combines below, so the evaluation ranks as
        # the galleries do, up to near-ties within the rounding to SCORE_DIGITS (E32)
        write_scores(args.scores_file.resolve(), scores_document(
            args.model, signature, list(zip(scored, mtimes, crop_labels)),
            [{'name': p['name'], 'prompts': p['prompts'], 'references': p['refs'],
              'text': [s.tolist() for s in text_scores[p['name']]],
              'visual': ([s.tolist() for s in visual_scores[p['name']]]
                         if profile_vectors[p['name']][1] is not None else None)} for p in profiles]))
        print(f'Scores written: {args.scores_file.resolve()}', flush=True)
    scores, normalized = {}, {}
    for p in profiles:
        name = p['name']
        has_refs = profile_vectors[name][1] is not None
        normalized[name], matches = rank_photos(text_scores[name], visual_scores[name] if has_refs else None,
                                                args.reference_weight)
        if not normalized[name] and scored:
            print(f'{name}: too few photos (or no spread) to normalize the scores; '
                  'the gallery shows the raw similarity.', flush=True)
        scores[name] = [(m, path, labels[m.crop]) for m, path, labels in zip(matches, scored, crop_labels)]

    thumbs = output / 'thumbnails'; thumbs.mkdir(exist_ok=True)
    # thumbnail folder of older versions: thumbnails are copied from it instead of being
    # rendered again; it is never written (old galleries link it), and the cleanup removes
    # its files once no gallery links them (E7)
    legacy_thumbs = output / 'vorschaubilder'

    def render_thumbnail(path, target):
        # decoded at reduced scale like an unloaded image in Image.thumbnail (E2)
        im = open_image(path, DRAFT_REDUCING_GAP * THUMBNAIL_SIZE)
        im.thumbnail((THUMBNAIL_SIZE, THUMBNAIL_SIZE)); im.save(target, quality=82)

    def log(message):
        print(message, flush=True)

    names = [p['name'] for p in profiles]
    slugs = dict(zip(names, profile_slugs(names)))
    # with several photo folders, a card names the photo's folder before its path in it (A25)
    labels = folder_labels(roots)
    # the folder the reference paths of profiles.json are relative to, as for the app (review)
    profiles_base = args.profiles.resolve().parent if args.profiles else Path.cwd()
    nav = '<nav>' + ' · '.join(f'<a href="{quote(slugs[p["name"]] + ".html")}">{html.escape(p["name"])}</a>' for p in profiles) + '</nav>'
    style = '''body{font:16px system-ui;background:#181818;color:#eee;margin:24px}a{color:#a9d2ff}
    main{display:grid;grid-template-columns:repeat(auto-fill,minmax(225px,1fr));gap:16px}
    article{background:#292929;padding:12px;border-radius:10px;overflow-wrap:anywhere}
    img{width:100%;height:250px;object-fit:contain;background:#111;border-radius:5px}
    small{color:#bbb}nav{margin-bottom:22px}'''
    # the full ranking: a photo skipped in the export is replaced by the next one (E12)
    rankings = {name: sorted(found, key=lambda x: x[0].score, reverse=True) for name, found in scores.items()}
    total_cards = sum(min(args.top, len(ranked)) for ranked in rankings.values())
    print('Writing the galleries ...', flush=True)
    status.update('exporting', total=total_cards)
    # skips (and logs) photos deleted or unreadable since scoring instead of aborting (E6),
    # each photo tried and logged once per export (review of E12)
    skipped = SkippedPhotos(log)
    progress = 0
    results = []  # the content of results.json: what each gallery shows (A12)
    pages = []  # [(file name, HTML)]: published together with results.json at the end (E24)
    for p in profiles:
        name = p['name']; ranked = rankings[name]
        cards, entries = [], []

        # progress counts every photo tried, also a skipped one (heartbeat), capped at the
        # gallery's share of the total; a full gallery or an exhausted ranking reaches it (review)
        def thumbnail(found, planned=progress + min(args.top, len(ranked))):
            nonlocal progress
            if progress < planned:
                progress += 1
                status.update(done=progress, force=progress == total_cards)
            return skipped.thumbnail(found[1], thumbs, legacy_thumbs, render_thumbnail)

        # ranks count only the cards shown, lower-ranked photos fill up to --top (E12)
        for rank, (match, path, label), thumb_name in gallery_cards(ranked, args.top, thumbnail):
            uri = html.escape(path.as_uri(), quote=True)
            relative = photo_name(path, roots, labels)  # once, for the HTML card and results.json (review)
            rel = html.escape(relative)
            score, detail = score_caption(match, normalized[name])
            label = crop_label(label)
            entries.append(result_card(rank, path, relative, label, match.score, match.text, match.visual, score, detail,
                                       thumb_name))
            cards.append(f'<article><a href="{uri}" target="_blank"><img loading="lazy" src="thumbnails/{quote(thumb_name)}" alt="{rel}"></a>'
                         f'<p><b>#{rank}</b> · {score} · {html.escape(label)}<br><small>{detail}</small><br>'
                         f'<a href="{uri}" target="_blank">{html.escape(path.name)}</a></p><small>{rel}</small></article>')
        page = ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                f'<title>FrameScout – {html.escape(name)}</title><style>{style}</style>' + nav +
                f'<h1>{html.escape(name)} – Top {len(cards)}</h1><p>Automatically generated ranking, not a guaranteed identification. '
                + (SCORE_NOTE if normalized[name] else RAW_NOTE) +
                ' "Full image" or "Person" names the best-scoring part of the photo. Click a photo to open the original. '
                f'Search model: {html.escape(search_model.label)}.</p><main>' + ''.join(cards) + '</main></html>')
        gallery = slugs[name] + '.html'
        pages.append((gallery, page))
        results.append({'name': name, 'fingerprint': search_fingerprint(p, profiles_base), 'gallery': gallery,
                        'normalized': normalized[name], 'cards': entries})
    if skipped.summary():
        log(skipped.summary())
    # results.json is published after all galleries, so the file always describes a complete
    # export (A12); a run stopped before leaves the galleries of the previous search (E24)
    settings = {'device': device, 'batch_size': args.batch_size, 'top': args.top,
                'person_detection': not args.no_person_detection, 'max_persons': args.max_persons,
                'person_confidence': args.person_confidence, 'reference_weight': args.reference_weight,
                'model': args.model}
    publish_export(output, pages, results_document(status.state['started'],
                   datetime.now().astimezone().isoformat(timespec='seconds'), roots, settings, len(paths), results))
    for (gallery, _), p in zip(pages, profiles):
        print(f"{p['name']}: {output / gallery}", flush=True)
    # the harmless part of the cleanup (E7, E13, E26): temporary thumbnails and other
    # temporary files of a stopped run, and thumbnails neither results.json nor any HTML file
    # in the output folder links; the run lock is still held, so no other search writes
    # thumbnails meanwhile
    try:
        cleaned = auto_cleanup(output)
    except Exception as exc:  # never fails a finished search
        print(f'Cleanup of the thumbnails skipped: {exc}', flush=True)
    else:
        if cleaned['files']:
            print(f"Removed {cleaned['files']} unused thumbnails or temporary files ({size_text(cleaned['freed'])}).",
                  flush=True)
        for note in cleaned['skipped']:
            print(note, flush=True)
    print(f'Done. New photo analyses: {fresh}, from cache: {reused}. Further search profiles can reuse the existing cache.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
