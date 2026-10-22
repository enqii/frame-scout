"""Shared helpers for the FrameScout app (app.py) and engine (framescout_engine.py).

This module uses only the Python standard library, so it can be imported and tested
without torch, Streamlit or any model download.
"""
import collections
import hashlib
import json
import os
import re
import shutil
import tempfile
import time
import unicodedata
from datetime import datetime
from pathlib import Path

if os.name == 'nt':
    import msvcrt
else:
    import fcntl

# Supported image file extensions (lowercase, with leading dot).
EXT = frozenset({'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff'})


# Lowercase Latin letters that Unicode decomposition does not reduce to ASCII (all of
# Latin-1 Supplement and Latin Extended-A, plus common stroke letters of Extended-B), and
# the German umlauts, whose conventional transliteration differs from dropping the
# diacritic. Letters missing here are dropped; a name left empty gets the hash fallback.
_TRANSLITERATION = str.maketrans({
    'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'ß': 'ss', 'æ': 'ae', 'œ': 'oe', 'ø': 'o', 'ł': 'l',
    'đ': 'd', 'ð': 'd', 'þ': 'th', 'ı': 'i', 'ħ': 'h', 'ŧ': 't', 'ŋ': 'ng', 'ĸ': 'k',
    'ƀ': 'b', 'ƈ': 'c', 'ƒ': 'f', 'ǥ': 'g', 'ƙ': 'k', 'ƚ': 'l', 'ƥ': 'p', 'ƭ': 't',
    'ƴ': 'y', 'ƶ': 'z', 'ȼ': 'c', 'ɇ': 'e', 'ɉ': 'j', 'ɍ': 'r', 'ɏ': 'y', 'ȷ': 'j'})
# Reserved Windows device names (Microsoft "Naming Files, Paths, and Namespaces"); some
# Windows versions and tools reject them as file names even with an extension. The
# superscript variants (COM¹ ...) become "com1" ... through NFKD and are covered too.
_WINDOWS_DEVICE_NAMES = frozenset({'con', 'prn', 'aux', 'nul',
                                   *(f'com{i}' for i in range(10)),
                                   *(f'lpt{i}' for i in range(10))})
SLUG_MAX_LENGTH = 60


def slugify(s):
    """Return a file-name-safe ASCII slug for a profile name.

    Latin letters with diacritics are transliterated ("Bär" -> "baer", "Café" -> "cafe");
    a name without any usable character (e.g. "猫") gets a stable 10-digit hash instead.
    The result contains only [a-z0-9-], is at most SLUG_MAX_LENGTH characters long and is
    never a Windows device name. It is not unique: use profile_slugs() for a profile list.
    """
    # NFC first, so that decomposed input ("a" + combining diaeresis) still matches "ä"
    # and the hash fallback does not depend on the normal form either
    s = unicodedata.normalize('NFC', s)
    text = unicodedata.normalize('NFKD', s.lower().translate(_TRANSLITERATION))
    # second pass for letters that only appear after decomposition ("ǽ" -> "æ" + acute)
    text = text.translate(_TRANSLITERATION).encode('ascii', 'ignore').decode('ascii')
    slug = re.sub('[^a-z0-9]+', '-', text).strip('-')[:SLUG_MAX_LENGTH].rstrip('-')
    if not slug:
        return hashlib.sha256(s.encode()).hexdigest()[:10]
    if slug in _WINDOWS_DEVICE_NAMES:
        slug += '-profile'
    return slug


def profile_slugs(names):
    """Return one unique slug per profile name, in list order.

    Colliding slugs get "-2", "-3", ... in the order of the list (the base is shortened
    so that the result stays within SLUG_MAX_LENGTH), so the app and the engine derive
    the same result file names (<slug>.html) from the same profile list.
    """
    slugs, used = [], set()
    for name in names:
        base = slugify(name)
        slug, n = base, 2
        while slug in used:
            suffix = f'-{n}'
            slug, n = base[:SLUG_MAX_LENGTH - len(suffix)].rstrip('-') + suffix, n + 1
        used.add(slug)
        slugs.append(slug)
    return slugs


def _path_key(path):
    """Comparable form of a path: resolved, and case-insensitive where the OS is (Windows)."""
    return os.path.normcase(path.resolve())


def reference_folder(refs_root, name, others, base):
    """Return the folder for new reference images of the profile name.

    That is refs_root/<slug>, or <slug>-2, <slug>-3, ... if the folder holds a reference
    image of one of the other profiles (dicts with "reference_images", paths relative to
    base), so two profiles never share a folder (A1). Leftover files that no other
    profile references do not block a folder: write_new_file never overwrites them.
    """
    used = {_path_key((base / ref).parent) for profile in others for ref in profile.get('reference_images', [])}
    slug = slugify(name)
    folder, n = refs_root / slug, 2
    while _path_key(folder) in used:
        folder, n = refs_root / f'{slug}-{n}', n + 1
    return folder


def stage_reference_move(refs, folder, refs_root, base, others):
    """First step of moving a renamed profile's reference images into folder (A1).

    refs: the profile's reference paths (relative to base, as in profiles.json); others:
    the other profiles. Every existing file inside refs_root that is not in folder yet and
    that no other profile references gets an additional name in folder: a hard link, or
    a copy where the file system has none. Its file name is kept if free, otherwise the
    next free reference-<n>; nothing is overwritten and nothing is removed here.

    Returns (new_refs, staged): refs with the new paths (relative to base, POSIX) and the
    (old, new) pairs. Save the profiles with new_refs, then call finish_reference_move;
    if the save fails, call undo_reference_move. Until then the old and the new path both
    exist, so a crash at any point leaves profiles.json pointing to existing files. Files
    outside refs_root, missing files and files of other profiles keep their paths. If
    staging fails, the names created so far are removed and the error is raised.
    """
    root = Path(_path_key(refs_root))
    taken = {_path_key(base / ref) for profile in others for ref in profile.get('reference_images', [])}
    moved, staged, new_refs = {}, [], []
    try:
        for ref in refs:
            old = base / ref
            k = _path_key(old)
            if k not in moved:
                inside = Path(k).is_relative_to(root) and Path(k) != root
                if not inside or k in taken or _path_key(old.parent) == _path_key(folder) or not old.is_file():
                    moved[k] = None  # keeps its path, exactly as written
                else:
                    new = _link_new(old.resolve(), folder)
                    staged.append((old.resolve(), new))
                    # lexically, like the paths the app writes: resolving would leave base
                    # if references/ is a junction or symlink to another place (review)
                    moved[k] = Path(os.path.relpath(new, base)).as_posix()
            new_refs.append(moved[k] or ref)
    except BaseException:
        undo_reference_move(staged)
        raise
    return new_refs, staged


def _link_new(src, folder):
    """Give src an additional name in folder (its own name if free, else reference-<n>)."""
    folder.mkdir(parents=True, exist_ok=True)
    names = [src.name] + [f'reference-{n}{src.suffix.lower()}' for n in range(1, 100000)]
    for name in names:
        dst = folder / name
        try:
            os.link(src, dst)
        except FileExistsError:
            continue
        except OSError:  # no hard links on this file system (e.g. FAT32/exFAT)
            try:
                _copy_new(src, dst)
            except FileExistsError:
                continue
        return dst
    raise FileExistsError(f'No free file name in {folder}')


def _copy_new(src, dst):
    """Copy src to the new file dst (FileExistsError if dst exists; no partial dst is left)."""
    try:
        with open(src, 'rb') as source, open(dst, 'xb') as target:
            shutil.copyfileobj(source, target)
    except FileExistsError:
        raise
    except BaseException:
        dst.unlink(missing_ok=True)
        raise


def finish_reference_move(staged, refs_root):
    """Last step after the profiles were saved: remove the old names of the moved files.

    An old name is removed only while its new name still exists with the same size; an
    old folder inside refs_root is removed only if it is empty afterwards. Returns a list
    of messages for old names that could not be removed (the files are then in both
    places; the saved profile uses the new one).
    """
    problems, folders = [], set()
    for old, new in staged:
        try:
            if new.stat().st_size != old.stat().st_size:
                raise OSError('the new copy differs in size')
            old.unlink()
            folders.add(old.parent)
        except OSError as exc:
            problems.append(f'{old}: {exc}')
    root = _path_key(refs_root)
    for folder in folders:
        if _path_key(folder) != root:
            try:
                folder.rmdir()  # only succeeds if the folder is empty
            except OSError:
                pass
    return problems


def undo_reference_move(staged):
    """Undo stage_reference_move after a failed save: remove only the new names."""
    for _, new in staged:
        try:
            new.unlink(missing_ok=True)
        except OSError:
            pass


def update_backup_references(filename, staged, base):
    """After a move was saved, point the moved reference paths in <filename>.bak to the new names.

    Call it between save_profiles (which wrote the backup with the old paths) and
    finish_reference_move (which removes the old names), so restoring the backup keeps
    working after a rename (review). Only the paths of the moved files (staged, from
    stage_reference_move; relative to base) change; everything else, including other
    top-level keys and their order, stays. The backup is replaced via a flushed temporary
    file, so a crash leaves the old or the new backup, and while the old names still
    exist both point to existing files.

    Returns True if the backup now fits the moved files (also if nothing had to change,
    it is missing or in the v3 format without reference paths) and False if it cannot be
    read, so it is left alone. Raises OSError if rewriting fails: the caller should then
    keep the old names (not call finish_reference_move), so the backup still works.
    """
    if not staged:
        return True
    backup = _backup_path(filename)
    try:
        data = backup.read_bytes()
    except FileNotFoundError:
        return True
    try:
        document = json.loads(data.decode('utf-8-sig'))
    except ValueError:
        return False
    if not isinstance(document, dict):
        return False
    profiles = document.get('profiles') if 'profiles' in document else []  # v3: no paths
    new_paths = {_path_key(old): Path(os.path.relpath(new, base)).as_posix() for old, new in staged}
    changed = False
    for profile in profiles if isinstance(profiles, list) else []:
        refs = profile.get('reference_images') if isinstance(profile, dict) else None
        for i, ref in enumerate(refs if isinstance(refs, list) else []):
            if isinstance(ref, str) and ref.strip():
                new = new_paths.get(_path_key(base / ref))
                if new is not None and new != ref:
                    refs[i], changed = new, True
    if changed:
        _replace_atomically(backup, (json.dumps(document, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    return True


def write_new_file(folder, stem, suffix, data):
    """Write data to folder/<stem>-<n><suffix> with the smallest free n >= 1; return the path.

    Never overwrites an existing file (exclusive create), so leftover reference images
    (e.g. of a deleted profile, or in a folder shared by profiles before A1) are kept.
    Creates the folder if needed.
    """
    folder.mkdir(parents=True, exist_ok=True)
    n = 1
    while True:
        path = folder / f'{stem}-{n}{suffix}'
        try:
            with open(path, 'xb') as handle:
                handle.write(data)
            return path
        except FileExistsError:
            n += 1


def create_from_example(target, example):
    """Create target as a copy of example if target does not exist; return True if created.

    Used for profiles.json, the user's working file, which is not in the repository:
    the app creates it from the shipped profiles.example.json on the first start. An
    existing file (even an empty one) is never replaced, and nothing is created if the
    example is missing. The copy is written to a temporary file next to target first and
    only then published under the final name, so a crash or a parallel session never
    sees a half-written target.
    """
    if target.exists():  # the usual case: cheap check, the publish step still guards races
        return False
    try:
        data = example.read_bytes()
    except FileNotFoundError:
        return False
    try:
        _publish_via_temp(target, lambda tmp: tmp.write_bytes(data), _publish_new)
    except FileExistsError:
        return False
    return True


def _publish_via_temp(target, write, publish, suffix='.tmp', durable=True):
    """Create target from a complete temporary file; never leave a partial target behind.

    write(tmp) fills a new temporary file in target's folder (named <target name>.<random>
    <suffix>); with durable, its data is flushed to disk (fsync) so that after a power
    loss the final name cannot point to an empty or partial file. Then publish(tmp, target)
    gives it the final name (os.replace, or _publish_new to never replace a file). The
    temporary file is removed whatever happens.
    """
    fd, name = tempfile.mkstemp(dir=target.parent, prefix=target.name + '.', suffix=suffix)
    os.close(fd)
    tmp = Path(name)
    try:
        write(tmp)
        if durable:
            with open(tmp, 'r+b') as handle:
                os.fsync(handle.fileno())
        publish(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)


def _publish_new(tmp, target):
    """Give the complete file tmp the name target; raise FileExistsError if target exists."""
    if os.name == 'nt':
        os.rename(tmp, target)  # never replaces an existing file on Windows (any file system)
    else:
        os.link(tmp, target)  # POSIX rename would replace target; a hard link does not


# OpenCLIP model and weights. The OpenAI CLIP weights were trained with QuickGELU;
# the plain "ViT-B-32" config uses GELU, loads them with only a warning and yields
# degraded embeddings (E1). Same weights file, so switching needs no new download.
CLIP_MODEL = 'ViT-B-32-quickgelu'
CLIP_PRETRAINED = 'openai'
# Part of the feature cache signature: change it whenever cached embeddings become
# incompatible (other model, weights, preprocessing or crops). v4 was ViT-B-32 with GELU.
ENGINE = f'v5-clip-{CLIP_MODEL}-{CLIP_PRETRAINED}-crop-features-1'


def feature_signature(person_detection, max_persons, person_confidence, yolo_model):
    """Return the cache signature of the image features for these engine settings.

    Cached rows are reused only under the same signature, so any setting that changes
    the stored embeddings or crops belongs here, and nothing else: without person
    detection only the full image is embedded, so the detector settings are left out.
    Without person detection JPEGs are decoded at reduced scale (draft_size, E2), so that
    signature also names the decoding; with detection photos keep full resolution and the
    signature is the same as before E2, so those cached rows stay valid.
    """
    config = [ENGINE, bool(person_detection)]
    if person_detection:
        config += [max_persons, person_confidence, yolo_model]
    else:
        config.append(DRAFT_DECODING)
    return hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()


# PyTorch version the installer installs (I3), the version of the verified end-to-end run.
# requirements.txt pins the same versions; a test keeps them in sync.
TORCH_VERSION = '2.14.1'
TORCHVISION_VERSION = '0.29.1'
TORCH_INDEX = 'https://download.pytorch.org/whl/'
# CUDA builds of PyTorch the installer chooses from, newest first (A7):
# (build, oldest compute capability, first unsupported compute capability, oldest Windows
# driver). From the CUDA 12.6/13.0 release notes and PyTorch's build targets as known when
# this was written; not verified on a GPU (the development PC has none). CUDA 13 dropped
# Maxwell, Pascal and Volta (< 7.5); the CUDA 12.6 build ends before Blackwell (10.0).
CUDA_BUILDS = (('cu130', (7, 5), None, (580,)),
               ('cu126', (5, 0), (10, 0), (528, 33)))


def _version(text):
    return tuple(int(x) for x in text.strip().split('.'))


def parse_gpu_query(text):
    """Return [(compute capability, driver version, name)] from nvidia-smi's GPU query.

    text is the output of nvidia-smi --query-gpu=compute_cap,driver_version,name
    --format=csv,noheader, one GPU per line, e.g. "8.9, 581.57, NVIDIA GeForce RTX 4070".
    Raises ValueError if it lists no GPU or a line cannot be read (e.g. "[N/A]" from an
    old driver).
    """
    gpus = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            cc, driver, name = (x.strip() for x in line.split(',', 2))
            gpus.append((_version(cc), _version(driver), name))
        except ValueError:
            raise ValueError(f'cannot read the GPU details from nvidia-smi: {line.strip()!r}') from None
    if not gpus:
        raise ValueError('nvidia-smi lists no GPU')
    return gpus


def _supports(build, gpu):
    cc, version, _ = gpu
    for name, oldest, unsupported, driver in CUDA_BUILDS:
        if name == build:
            return oldest <= cc and (unsupported is None or cc < unsupported) and version >= driver
    raise ValueError(f'unknown PyTorch build: {build}')


def unsupported_gpus(build, gpus):
    """Return the names of the gpus (as from parse_gpu_query) that build cannot use."""
    return [gpu[2] for gpu in gpus if not _supports(build, gpu)]


def cuda_build(gpus):
    """Return the CUDA build of PyTorch ("cu130", "cu126") to install for gpus.

    gpus as returned by parse_gpu_query. The newest build that supports every GPU is
    preferred, since CUDA can number the GPUs differently from nvidia-smi. Otherwise the
    newest build for the most capable GPU (highest compute capability) is used, so an old
    second card does not drop the PC to the CPU build (review); unsupported_gpus names the
    GPUs that build cannot use. Raises ValueError with the reason if no build supports the
    most capable GPU (GPU too old, or driver too old for it).
    """
    if not gpus:
        raise ValueError('no NVIDIA GPU found')
    for build, *_ in CUDA_BUILDS:
        if all(_supports(build, gpu) for gpu in gpus):
            return build
    best = max(gpus, key=lambda gpu: gpu[0])
    for build, *_ in CUDA_BUILDS:
        if _supports(build, best):
            return build
    cc, version, name = best
    oldest = min(supported for _, supported, *_ in CUDA_BUILDS)
    hint = ('The GPU is too old for current PyTorch builds.' if cc < oldest
            else 'A current NVIDIA driver may help.')
    raise ValueError(f'no CUDA build of PyTorch {TORCH_VERSION} suits {name} (compute capability '
                     f'{".".join(map(str, cc))}) with driver {driver_text(version)}. {hint}')


def driver_text(version):
    """Return an NVIDIA driver version tuple as nvidia-smi prints it, e.g. (590, 1) -> "590.01"."""
    major, *rest = version
    return '.'.join([str(major)] + [f'{x:02d}' for x in rest])


def torch_requirements(build):
    """Return the pip requirements of PyTorch for build ("cpu", "cu126", "cu130").

    The local version label (+cpu, +cu130) makes pip replace an installed build of the same
    version, so running the installer again switches between the CPU and the CUDA build.
    """
    return [f'torch=={TORCH_VERSION}+{build}', f'torchvision=={TORCHVISION_VERSION}+{build}']


def installed_build_matches(torch_version, torchvision_version, build):
    """Return True if the installed torch and torchvision are the pinned versions of build.

    The versions are those of the installed packages (None = not installed), e.g.
    "2.14.1+cu130". PyPI's Windows wheels are the CPU build without a local label, so a
    plain "2.14.1" counts as "cpu": an existing CPU install is not downloaded again.
    """
    def matches(installed, version):
        if installed is None:
            return False
        base, _, label = installed.partition('+')
        return base == version and (label == build or (build == 'cpu' and label == ''))
    return matches(torch_version, TORCH_VERSION) and matches(torchvision_version, TORCHVISION_VERSION)


def installed_cuda_build(torch_version):
    """Return the CUDA build ("cu130", ...) of an installed torch version, or None for a CPU build or none."""
    label = (torch_version or '').partition('+')[2]
    return label if label.startswith('cu') else None


def torch_index_url(build):
    """Return the PyTorch package index of build ("cpu" or one of CUDA_BUILDS)."""
    if build != 'cpu' and build not in {b for b, *_ in CUDA_BUILDS}:
        raise ValueError(f'unknown PyTorch build: {build}')
    return TORCH_INDEX + build


def device_choices(cuda_available):
    """Return the compute devices the app offers: "cuda" only if PyTorch can use a CUDA GPU (A7)."""
    return ['auto', 'cpu'] + (['cuda'] if cuda_available else [])


def cuda_hint(torch_cuda):
    """Return how to get GPU support when PyTorch cannot use CUDA (A7).

    torch_cuda is torch.version.cuda (None for the CPU build). FrameScout must be closed
    first: pip cannot replace torch's files while the app has them loaded, and the app sees
    a new build only after a restart (review).
    """
    if torch_cuda is None:
        return 'For an NVIDIA GPU, close FrameScout, run Install-FrameScout.bat cuda and start FrameScout again.'
    return ('Update the NVIDIA driver, or close FrameScout, run Install-FrameScout.bat cuda (it picks the build '
            'for the installed driver) and start FrameScout again.')


def cuda_status(cuda_available, torch_cuda, gpu_name):
    """Describe whether the engine can use a CUDA GPU, for the app's system details.

    torch_cuda is torch.version.cuda: None for the CPU build of PyTorch, which never uses
    a GPU, even an NVIDIA GPU with a current driver (A7). A CUDA build that cannot use the
    GPU often means a driver too old for that build, not a missing GPU (review).
    """
    if cuda_available:
        return f'CUDA: {gpu_name}'
    if torch_cuda is None:
        return f'PyTorch without CUDA support (CPU build), so the analysis runs on the CPU. {cuda_hint(None)}'
    return (f'PyTorch for CUDA {torch_cuda} finds no usable GPU (no NVIDIA GPU, or a driver too old for this '
            f'build), so the analysis runs on the CPU. {cuda_hint(torch_cuda)}')


# Input size of the person detection: it decides which persons are found, i.e. which
# crops are cached, so changing it needs an ENGINE bump.
DETECTION_IMAGE_SIZE = 640


def detection_options(device, max_persons, person_confidence):
    """Return the keyword arguments of the person detection (YOLO predict) of one photo.

    The detector runs on the same device as CLIP (E14): on a CUDA GPU it was the slowest
    step when it stayed on the CPU. Only class 0 (person) is detected.
    """
    return dict(classes=[0], conf=person_confidence, imgsz=DETECTION_IMAGE_SIZE, max_det=max_persons,
                verbose=False, device=device)


# Label of the uncropped photo among the crops; person crops are labelled "Person <n>".
FULL_IMAGE_LABEL = 'Full image'
# Labels are stored in the feature cache; rows written before the English translation
# (I7) carry the German label. Mapping them on display keeps those rows valid.
_LEGACY_LABELS = {'Gesamtbild': FULL_IMAGE_LABEL}


def crop_label(stored):
    """Return the gallery label for a crop label stored in the feature cache."""
    return _LEGACY_LABELS.get(stored, stored)


def thumbnail_name(path, mtime_ns):
    """Return the file name of the gallery thumbnail of path at modification time mtime_ns."""
    return hashlib.sha256((str(path) + str(mtime_ns)).encode()).hexdigest()[:24] + '.jpg'


def ensure_thumbnail(path, thumbs, legacy_thumbs, render, log):
    """Return the file name of path's thumbnail in the folder thumbs, or None on failure.

    An existing thumbnail is reused; one of an older version in legacy_thumbs (same name =
    same photo and modification time) is copied and left in place; otherwise
    render(path, target) writes a new one. Any failure, including a photo that was
    deleted or moved after scoring (E6), is reported with log(message) and the photo
    is skipped, so one missing file cannot abort the whole HTML export. render must
    write to the target it is given (a temporary .jpg name, not the final one).
    """
    try:
        name = thumbnail_name(path, path.stat().st_mtime_ns)
        target = thumbs / name
        if not target.exists():
            old = legacy_thumbs / name
            if old.is_file():
                def write(tmp):
                    shutil.copyfile(old, tmp)
            else:
                def write(tmp):
                    render(path, tmp)
            # via a temporary .jpg file (Pillow picks the format from the extension), so an
            # interrupted copy or render never leaves a broken thumbnail that later runs reuse
            _publish_via_temp(target, write, os.replace, suffix='.jpg', durable=False)
        return name
    except Exception as exc:
        log(f'Thumbnail not possible ({path}): {exc}')
        return None


def progress_line(done, total, new, cached, errors):
    """Return the progress line the engine prints to its log during the analysis.

    For people reading the log only: the app reads the progress from the status file
    (StatusReporter, A5), not from the log text (A11).
    """
    return f'Progress: {done}/{total} | New: {new} | Cached: {cached} | Errors: {errors}'


def progress_due(before, after, total, every=25):
    """Return True if the engine should print a progress line after going from before to after done photos.

    That is every `every` photos and once at the end. Photos can finish several at a time
    (one embedded batch, E2), so a multiple of `every` that was jumped over counts too.
    """
    return after > before and (after == total or after // every > before // every)


# One search at a time per output folder (A4): the engine holds RUN_LOCK in the output
# folder while it runs and reports its phase and progress in RUN_STATUS (A5), which the
# app reads to show a run again after a browser reload, in another tab or session.
RUN_LOCK = 'run.lock'
RUN_STATUS = 'run-status.json'
STATUS_FORMAT = 1
# phases in run order; the app writes "starting", the engine the others
PHASE_LABELS = {
    'starting': 'Starting the search',
    'scanning': 'Looking for photos',
    'loading': 'Loading the AI models',
    'analyzing': 'Analyzing photos',
    'scoring': 'Scoring photos',
    'exporting': 'Writing galleries',
    'finished': 'Finished',
    'failed': 'Failed',
    'interrupted': 'Interrupted',
}
FINAL_PHASES = frozenset({'finished', 'failed', 'interrupted'})


def _try_lock(fd):
    """Lock fd exclusively without waiting; raise OSError if another handle holds the lock."""
    if os.name == 'nt':
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)  # one byte, beyond the end of the empty file
    else:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(fd):
    if os.name == 'nt':
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)


class RunLock:
    """An exclusive lock on a file, held while a search runs in an output folder (A4).

    It is a lock of the operating system (Windows byte-range lock, flock elsewhere) on an
    open file, not the existence of the file: when the process ends in any way, including
    terminate()/kill() or a crash, the operating system releases it, so a stopped run never
    leaves a stale lock behind. The file stays in place (empty) after the run. Two RunLock
    objects conflict even within one process.
    """

    def __init__(self, path):
        self.path = Path(path)
        self._fd = None

    @property
    def held(self):
        return self._fd is not None

    def acquire(self, timeout=0.0, poll=0.1, clock=time.monotonic, sleep=time.sleep):
        """Take the lock, trying for up to timeout seconds; return True if it is held now."""
        if self._fd is not None:
            return True
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT)  # not inherited by child processes (PEP 446)
        deadline = clock() + timeout
        while True:
            try:
                _try_lock(fd)
            except OSError:
                if clock() >= deadline:
                    os.close(fd)
                    return False
                sleep(poll)
            else:
                self._fd = fd
                return True

    def release(self):
        """Give the lock back (nothing happens if it is not held)."""
        fd, self._fd = self._fd, None
        if fd is None:
            return
        try:
            _unlock(fd)
        except OSError:
            pass  # closing the file releases the lock as well
        finally:
            os.close(fd)


def lock_held(path):
    """Return True if a process holds the RunLock on path; never creates the file.

    Checks by taking the lock for a moment, so a RunLock.acquire at that very moment fails
    once: the engine and the app therefore acquire with a timeout. A file that exists but
    cannot be opened (e.g. PermissionError while it is pending delete or held by an antivirus
    scanner on Windows) counts as held, the safe side: no start (review).
    """
    try:
        fd = os.open(path, os.O_RDWR)
    except FileNotFoundError:
        return False
    except OSError:
        return True
    try:
        try:
            _try_lock(fd)
        except OSError:
            return True
        _unlock(fd)
        return False
    finally:
        os.close(fd)


def _timestamp():
    return datetime.now().astimezone().isoformat(timespec='seconds')


class StatusReporter:
    """Writes the status file of a search run: process id, phase and progress (A4, A5).

    update() merges the given fields; it writes the file when the phase changes, when force
    is set, and otherwise at most every interval seconds, so a progress update per photo
    costs nothing. The file is replaced atomically (never half-written). Writing is best
    effort: on Windows replacing a file fails while another process has it open (the app
    reads it every two seconds); a failed update is retried with the next one and never
    stops the search. finish() writes the final phase, trying harder.
    """

    def __init__(self, path, pid, interval=1.0, clock=time.monotonic, retries=20, retry_delay=0.05):
        self.path = Path(path)
        self.interval, self.clock, self.retries, self.retry_delay = interval, clock, retries, retry_delay
        started = _timestamp()
        self.state = {'format': STATUS_FORMAT, 'pid': pid, 'phase': None, 'started': started, 'updated': started,
                      'done': 0, 'total': 0, 'new': 0, 'cached': 0, 'errors': 0,
                      'exit_code': None, 'message': None}
        self._written = None  # clock() of the last successful write

    def update(self, phase=None, force=False, **fields):
        """Merge phase and fields into the status; write it if due. Returns True if written now."""
        if phase is not None and phase != self.state['phase']:
            # a new phase starts its own progress count; the analysis counts are kept
            self.state.update(phase=phase, done=0, total=0)
            force = True
        self.state.update(fields)
        if not force and self._written is not None and self.clock() - self._written < self.interval:
            return False
        # a phase change is worth a few retries, a single progress update is not
        return self._write(attempts=1 + self.retries if force else 1)

    def finish(self, phase, exit_code, message=None):
        """Write the final phase (one of FINAL_PHASES) with the exit code; returns True if written."""
        self.state.update(phase=phase, exit_code=exit_code, message=message)
        return self._write(attempts=1 + self.retries)

    def _write(self, attempts):
        self.state['updated'] = _timestamp()
        if not write_status(self.path, self.state, attempts, self.retry_delay):
            return False
        self._written = self.clock()
        return True


def write_status(path, status, attempts=1, retry_delay=0.05):
    """Replace the status file path with the dict status atomically; return True if written.

    Tries up to attempts times, retry_delay seconds apart; never raises OSError.
    """
    data = (json.dumps(status, ensure_ascii=False, indent=1) + '\n').encode('utf-8')
    try:
        _replace_with_retry(path, data, attempts, retry_delay, durable=False)
    except OSError:
        return False
    return True


def stopped_status(status):
    """Return status marked as stopped from the app: phase "interrupted", progress kept.

    terminate()/kill() skips the engine's own final write, so the app writes this instead.
    """
    return {**status, 'phase': 'interrupted', 'exit_code': None, 'message': 'Stopped in the app.',
            'updated': _timestamp()}


def started_in_time(status, create_time, tolerance=2.0):
    """Return True if a process created at create_time (seconds since the epoch) can be the run of status.

    The process of a run exists before its status is written (the app writes "starting"
    after Popen, the engine its status after it started), so a process with the status's
    pid that was created later got the pid after the run's process ended (review). The
    tolerance covers the whole seconds of "started" and clock rounding.
    """
    try:
        started = datetime.fromisoformat(status['started']).timestamp()
    except (KeyError, TypeError, ValueError):
        return False
    return create_time <= started + tolerance


def final_status(code):
    """Return (phase, message) of the engine's final status for its exit code."""
    if code == 0:
        return 'finished', None
    if code == 130:
        return 'interrupted', 'Interrupted (Ctrl+C).'
    return 'failed', f'The search ended with exit code {code}.'


def read_status(path):
    """Return the status dict of a run (see StatusReporter), or None if missing or unreadable."""
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):  # ValueError includes JSON and Unicode decoding errors
        return None
    return data if isinstance(data, dict) else None


def run_active(status, held, alive):
    """Return True if a search is running in the output folder of status.

    held: whether the RunLock of that folder is held (lock_held). Without the lock, a run
    counts only while it is being started: the app writes the status "starting" with the
    engine's process id before the engine takes the lock, and alive(pid) tells whether
    that process still runs. A status that is not final (e.g. after kill(), which skips
    the final write) does not count once its process is gone.
    """
    if held:
        return True
    if not status or status.get('phase') in FINAL_PHASES:
        return False
    pid = status.get('pid')
    return isinstance(pid, int) and not isinstance(pid, bool) and bool(alive(pid))


def _count(status, key):
    value = status.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def status_fraction(status):
    """Return the progress of the current phase between 0 and 1, or None if it has no count."""
    done, total = _count(status, 'done'), _count(status, 'total')
    if done is None or not total or total < 0:
        return None
    return min(max(done / total, 0.0), 1.0)


def status_text(status):
    """Return the line the app shows for a status: the phase and, if it counts, its progress."""
    phase = status.get('phase')
    label = PHASE_LABELS.get(phase, str(phase))
    done, total = _count(status, 'done'), _count(status, 'total')
    if not total or done is None:
        return label
    if phase == 'analyzing':
        new, cached, errors = (_count(status, k) or 0 for k in ('new', 'cached', 'errors'))
        return f'{label}: {done:,}/{total:,} · {new:,} new · {cached:,} from cache · {errors:,} errors'
    if phase == 'exporting':
        return f'{label}: {done:,}/{total:,} matches'
    return f'{label}: {done:,}/{total:,}'


# Pillow's Image.thumbnail decodes JPEGs at a reduced scale only down to twice the
# requested size (reducing_gap=2) and resizes the rest of the way with its filter; the
# engine keeps the same quality margin for CLIP's input.
DRAFT_REDUCING_GAP = 2
# Names the drafted decoding in the cache signature of runs without person detection;
# change it if the decoding of those runs changes (the user decided in the PR #7 review
# that drafted and full-resolution embeddings are not mixed in the cache).
DRAFT_DECODING = f'jpeg-draft-{DRAFT_REDUCING_GAP}x-clip-size'


def draft_size(clip_size, person_detection):
    """Return the smallest edge length a photo may be decoded at for the analysis, or None.

    JPEG decoding can scale by 1/2, 1/4 or 1/8 on the fly (Image.draft), which makes it
    several times faster (E2). Without person detection CLIP sees only the whole photo,
    resized to clip_size, so twice that is enough. With person detection the photo is
    decoded at full resolution: a person crop (e.g. in a group photo) covers only part of
    it and would lose detail.
    """
    return None if person_detection else DRAFT_REDUCING_GAP * clip_size


def group_batches(items, batch_size, size):
    """Yield lists of consecutive items with at most batch_size crops each.

    size(item) is the number of crops of an item (a photo). Items are added to a list as
    long as their crops fit, so CLIP embeds the crops of several photos in one forward
    pass instead of one photo at a time (E2), and a list never needs a second, small pass
    for a few leftover crops (review). An item with more than batch_size crops is a list
    on its own. Items are read lazily: a full list is yielded before the next item is
    requested; otherwise a list is yielded when the next item does not fit any more.
    """
    if batch_size < 1:
        raise ValueError('batch_size must be at least 1')
    group, count = [], 0
    for item in items:
        n = size(item)
        if group and count + n > batch_size:
            yield group
            group, count = [], 0
        group.append(item)
        count += n
        if count >= batch_size:
            yield group
            group, count = [], 0
    if group:
        yield group


def store_group(group, store, failed):
    """Store a group of items with store(group); return the number of items stored.

    store must store all items or none (one transaction). If it raises and the group has
    several items, each item is stored on its own, so a single broken photo or a failure
    that hits only one of them (review) does not fail the whole group, and failed(item,
    exc) reports every item that still fails with its own error. KeyboardInterrupt and
    other BaseExceptions are not caught.
    """
    try:
        store(group)
        return len(group)
    except Exception as exc:
        if len(group) == 1:
            failed(group[0], exc)
            return 0
    stored = 0
    for item in group:
        try:
            store([item])
            stored += 1
        except Exception as exc:
            failed(item, exc)
    return stored


def prefetch(submit, items, depth):
    """Yield (item, future) in input order, with up to depth items submitted ahead.

    submit(item) starts the work (e.g. ThreadPoolExecutor.submit) and returns a Future.
    The work for later items runs while the consumer handles the current one (decoding
    photos in parallel, E2), but never more than depth items ahead, which bounds memory.
    Errors stay in the futures: future.result() raises them for that item only. Closing
    the generator (e.g. on KeyboardInterrupt) cancels the work that has not started yet.
    """
    if depth < 1:
        raise ValueError('depth must be at least 1')
    queue = collections.deque()
    try:
        for item in items:
            queue.append((item, submit(item)))
            if len(queue) >= depth:
                yield queue.popleft()
        while queue:
            yield queue.popleft()
    finally:
        for _, future in queue:
            future.cancel()


def generic_prompts(name, context='', features=''):
    """English CLIP prompts derived from a profile's name, context and features."""
    subject = name.strip()
    context = f' ({context.strip()})' if context.strip() else ''
    target = subject + context
    prompts = [f'A photograph of {target}.',
               f'An image showing {target}.',
               f'A detailed photo of {target}.',
               f'A scene featuring {target}.']
    if features.strip():
        prompts += [f'A photograph of {target}, with {features.strip()}.',
                    f'An image showing {features.strip()}, depicting {target}.']
    return prompts


def load_profiles(filename, inline):
    """Load and validate search profiles.

    filename: path of a profiles JSON file or None; inline: list of "NAME|CONTEXT|FEATURES"
    strings (CLI option --character). Returns a list of dicts with the keys "name",
    "prompts" (generated + custom prompts), "generated" (how many of the prompts are
    generated templates; they are averaged into one query, E4) and "refs" (reference image
    paths, resolved relative to the JSON file's folder). Raises ValueError for invalid input.
    """
    raw = list(_read_entries(filename)) if filename else []
    for item in inline:
        fields = [s.strip() for s in item.split('|', 2)]
        raw.append({'name': fields[0], 'franchise': fields[1] if len(fields) > 1 else '',
                    'features': fields[2] if len(fields) > 2 else ''})
    if not raw:
        raise ValueError('Please specify --profiles or at least one --character.')
    _check_entries(raw)
    profiles = []
    for item in raw:
        name = item['name']
        franchise, features = item.get('franchise', ''), item.get('features', '')
        prompts, refs = item.get('prompts', []), item.get('reference_images', [])
        generated = generic_prompts(name, franchise, features)
        profiles.append({'name': name.strip(), 'prompts': generated + prompts, 'generated': len(generated),
                         'refs': [((filename.parent if filename else Path.cwd()) / x).resolve() for x in refs]})
    return profiles


def _read_entries(filename):
    """Return the raw profile list of a profiles JSON file; the v3 format is converted."""
    data = json.loads(filename.read_text(encoding='utf-8-sig'))
    if isinstance(data, dict) and 'profiles' in data:
        raw = data['profiles']
    elif isinstance(data, dict):  # v3 migration: {name: [prompts, ...]}
        raw = [{'name': n, 'prompts': ps} for n, ps in data.items()]
    else:
        raise ValueError('The JSON file must be an object with "profiles" (or the previous v3 format).')
    if not isinstance(raw, list):
        raise ValueError('"profiles" must be a list.')
    return raw


def _check_entries(raw):
    """Raise ValueError unless raw is a list of valid profile dicts with unique names."""
    names = set()
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError('Every profile must be a JSON object.')
        name = item.get('name', '')
        # compare the stripped name: it is the one stored and used as key (E10)
        if not isinstance(name, str) or not name.strip() or name.strip().lower() in names:
            raise ValueError(f'Profile name missing or duplicate: {name!r}')
        names.add(name.strip().lower())
        franchise = item.get('franchise', '')
        features = item.get('features', '')
        prompts = item.get('prompts', [])
        refs = item.get('reference_images', [])
        if not isinstance(franchise, str) or not isinstance(features, str) or not isinstance(prompts, list) or not isinstance(refs, list):
            raise ValueError(f'Invalid profile: {name}')
        if any(not isinstance(x, str) or not x.strip() for x in prompts + refs):
            raise ValueError(f'Prompts and reference images must be non-empty strings: {name}')


def read_profiles(filename):
    """Return the profile dicts of the app's profiles JSON file as stored ([] if it is missing).

    Validated like load_profiles(), but an empty list is allowed and unknown keys are
    kept. The previous v3 format {name: [prompts, ...]} is converted, so saving it does
    not lose the profiles (A2). Raises ValueError (including json.JSONDecodeError) for a
    file the app cannot represent, so that the app never saves over it.
    """
    try:
        raw = _read_entries(filename)
    except FileNotFoundError:
        return []
    _check_entries(raw)
    return raw


def save_profiles(filename, profiles):
    """Write profiles to filename as {"profiles": [...]} (other top-level keys are kept), with a .bak.

    The previous content is copied byte for byte to <filename>.bak first (replacing an
    older backup, so only the state before the latest save is kept); if that fails,
    filename is left unchanged. Both files are written to a temporary file in the same
    folder, flushed to disk and then renamed, so a crash or power loss leaves a complete
    old or new file, never a half-written one.
    """
    try:
        previous = filename.read_bytes()
    except FileNotFoundError:
        previous = None
    document = {'profiles': profiles}
    if previous is not None:
        _replace_atomically(_backup_path(filename), previous)
        try:
            old = json.loads(previous.decode('utf-8-sig'))
        except ValueError:  # unreadable: nothing to keep (the .bak has it)
            old = None
        # other top-level keys (e.g. hand-added metadata) are kept in their order; a v3
        # file, whose keys are profile names, is not merged (review)
        if isinstance(old, dict) and 'profiles' in old:
            document = {**old, 'profiles': profiles}
    text = json.dumps(document, ensure_ascii=False, indent=2) + '\n'
    _replace_atomically(filename, text.encode('utf-8'))


def _backup_path(filename):
    """Return the backup file of a profiles file: <filename>.bak."""
    return filename.with_name(filename.name + '.bak')


def _replace_atomically(target, data):
    """Replace target with data via a temporary file that is flushed to disk first."""
    _publish_via_temp(target, lambda tmp: tmp.write_bytes(data), os.replace)


def _replace_with_retry(target, data, attempts, retry_delay, durable=True):
    """Replace target with the bytes data atomically, trying up to attempts times.

    On Windows, replacing a file fails while another process or thread has it open, e.g. an
    app session reading the status or settings file at that moment; the tries are
    retry_delay seconds apart. Raises the last OSError if every try fails.
    """
    for attempt in range(max(attempts, 1)):
        try:
            _publish_via_temp(Path(target), lambda tmp: tmp.write_bytes(data), os.replace, durable=durable)
            return
        except OSError:
            if attempt + 1 >= attempts:
                raise
            time.sleep(retry_delay)


# The app's settings (A8): kept in settings.json in the project folder, so they survive a
# browser reload and a restart. Only values that differ from the defaults are written, so
# the default photo folder follows the project folder when it is moved.
SETTINGS_FILE = 'settings.json'
# the engine's --device choices
DEVICES = ('auto', 'cpu', 'cuda')
# (minimum, maximum) of each number setting; the app builds its widgets from them (Streamlit
# raises for a value outside a widget's range), so both always agree (review). Float
# bounds mark a float setting.
SETTING_RANGES = {'batch_size': (1, 64), 'top': (1, 5000), 'max_persons': (1, 50),
                  'person_confidence': (0.1, 0.9), 'reference_weight': (0.0, 1.0)}
# seconds save_settings waits for the lock around its read-merge-write
SETTINGS_LOCK_TIMEOUT = 5.0


def default_settings(base):
    """Return the app's default settings; base is the project folder (photos/ is the default input)."""
    return {'photo_folder': str(Path(base) / 'photos'), 'device': 'auto', 'batch_size': 8, 'top': 150,
            'person_detection': True, 'max_persons': 12, 'person_confidence': 0.30, 'reference_weight': 0.35}


def _setting_value(key, value):
    """Return value as the setting key uses it, or None if it is not allowed."""
    if key == 'photo_folder':
        return value if isinstance(value, str) else None
    if key == 'device':
        return value if isinstance(value, str) and value in DEVICES else None
    if key == 'person_detection':
        return value if isinstance(value, bool) else None
    if key not in SETTING_RANGES:
        return None
    low, high = SETTING_RANGES[key]
    number = isinstance(value, (int, float)) and not isinstance(value, bool)
    if isinstance(low, float):
        # rounded: a slider computes min + n * step, e.g. 0.30000000000000004 (review)
        return round(float(value), 4) if number and low <= value <= high else None  # NaN is never in range
    return value if number and isinstance(value, int) and low <= value <= high else None


def _read_settings_file(filename, attempts=5, retry_delay=0.05):
    """Return the JSON object of a settings file ({} if it is missing); ValueError if unreadable.

    On Windows, reading fails for a moment while another session replaces the file, so an
    OSError is retried up to attempts times, retry_delay seconds apart (review).
    """
    for attempt in range(max(attempts, 1)):
        try:
            text = Path(filename).read_text(encoding='utf-8-sig')
            break
        except FileNotFoundError:
            return {}
        except OSError:
            if attempt + 1 >= attempts:
                raise
            time.sleep(retry_delay)
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError('The settings file must be a JSON object.')
    return data


def read_settings(filename, defaults, attempts=5, retry_delay=0.05):
    """Return (settings, problems) of the app's settings file.

    settings has the keys of defaults: a saved value replaces its default if it is allowed
    (the same range as the app's widget); a missing file gives the defaults. problems lists
    the saved values that are not allowed and were replaced by their defaults. Unknown keys
    are ignored (save_settings keeps them). Raises ValueError (including JSON and Unicode
    decoding errors) for a file that is not a JSON object, and OSError if it still cannot
    be read after attempts tries.
    """
    data = _read_settings_file(filename, attempts, retry_delay)
    settings, problems = dict(defaults), []
    for key in defaults:
        if key not in data:
            continue
        value = _setting_value(key, data[key])
        if value is None:
            problems.append(f'{key}: {data[key]!r} is not allowed, the default {defaults[key]!r} is used')
        else:
            settings[key] = value
    return settings, problems


def save_settings(filename, changes, defaults, attempts=5, retry_delay=0.05, lock_timeout=SETTINGS_LOCK_TIMEOUT):
    """Write the changed settings into the app's settings file; return them as written.

    changes are merged into the file as it is now (another tab or session may have saved
    other settings in between). The read-merge-write holds a RunLock on <filename>.lock
    (app sessions are threads of one process, and two RunLocks conflict there too), so two
    sessions saving at the same moment cannot lose a change (review); the lock file stays
    (empty). Saved values that are not allowed (read_settings replaced them by their
    defaults and reported them) and values equal to their default are removed; unknown
    keys are kept. No file is created if there is nothing to write. The file is replaced
    atomically; on Windows that fails while another session reads it at that moment, so
    reading and replacing are tried up to attempts times. The returned dict holds the
    changes as stored, e.g. rounded floats. Raises ValueError for a change that is not
    allowed and for an unreadable file, which is never replaced, and OSError if the lock is
    not free within lock_timeout seconds or reading or writing keeps failing.
    """
    filename = Path(filename)
    normalized = {}
    for key, value in changes.items():
        allowed = _setting_value(key, value) if key in defaults else value
        if allowed is None:
            raise ValueError(f'{key}: {value!r} is not allowed')
        normalized[key] = allowed
    lock = RunLock(filename.with_name(filename.name + '.lock'))
    if not lock.acquire(timeout=lock_timeout, poll=0.01):
        raise OSError(f'{filename.name} is being saved by another session')
    try:
        document = {}
        for key, value in {**_read_settings_file(filename, attempts, retry_delay), **normalized}.items():
            if key in defaults:
                # after normalizing, a known setting has the type of its default (no True == 1)
                value = _setting_value(key, value)
                if value is None or value == defaults[key]:
                    continue
            document[key] = value
        if document or filename.exists():
            data = (json.dumps(document, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
            _replace_with_retry(filename, data, attempts, retry_delay)
    finally:
        lock.release()
    return normalized


def reconcile_settings(widgets, seen, shown, saved, defaults):
    """Bring the app's settings widgets and the saved settings together (A8 review).

    Called at the start of every page run, before the widgets are drawn. widgets maps a
    setting to its widget's current value (missing: a new page, or the widget was not drawn
    in the last run). seen and shown are this session's records per setting: seen is the
    saved value it last took from or wrote to the file, shown is the value its widget showed
    then. They differ for a substitute (e.g. "auto" shown for a saved device PyTorch cannot
    use) and for slider noise (0.30000000000000004 shown, 0.3 saved). saved is the result of
    read_settings, or None if the file cannot be read.

    Returns (updates, changed, taken_over). updates are the values to put into the widgets
    now. changed are the widgets changed in this session, to be saved; after a successful
    save the caller stores the widget values in shown and the result of save_settings in
    seen, and after a failed one neither, so the save is tried again on the next run.
    taken_over lists the settings another session saved, now shown here. A change in this
    session wins over another session's save, since it is the later action. seen and shown
    are updated for the updates.
    """
    updates, changed, taken_over = {}, {}, []
    for name, default in defaults.items():
        file_value = default if saved is None else saved[name]
        if name not in widgets:
            updates[name] = seen[name] = shown[name] = file_value
        elif widgets[name] != shown.get(name, widgets[name]):
            changed[name] = widgets[name]
        elif saved is not None and file_value != seen.get(name, file_value):
            updates[name] = seen[name] = shown[name] = file_value
            taken_over.append(name)
    return updates, changed, taken_over
