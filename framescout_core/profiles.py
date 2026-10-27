"""Search profiles: loading and validating them, reading and saving the app's profiles.json (A2, A13)."""
import hashlib
import json
from pathlib import Path

from ._common import _file_lock, _publish_new, _publish_via_temp, _read_with_retry, _replace_with_retry


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
    return _entries_of(filename.read_bytes())


def _entries_of(content):
    """Return the raw profile list of the bytes of a profiles JSON file (see _read_entries)."""
    data = json.loads(content.decode('utf-8-sig'))
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
    return read_profiles_versioned(filename)[0]


def read_profiles_versioned(filename, attempts=5, retry_delay=0.05):
    """Return (profiles, version) of the app's profiles JSON file, read once (A13).

    profiles as read_profiles() returns them (same errors); version identifies the file's
    exact content (None if it is missing). Pass it to save_profiles(expected=...) so that a
    save based on these profiles never overwrites a change made to the file since. On
    Windows, reading fails for a moment while another session replaces the file, so an
    OSError is retried up to attempts times, retry_delay seconds apart (review).
    """
    try:
        content = _read_with_retry(filename.read_bytes, attempts, retry_delay)
    except FileNotFoundError:
        return [], None
    raw = _entries_of(content)
    _check_entries(raw)
    return raw, _version_of(content)


class ProfilesChangedError(ValueError):
    """save_profiles refused a save: the file changed since the profiles it is based on were read (A13)."""


# the default of save_profiles(expected=...): save without comparing versions
_UNCHECKED = object()
# seconds save_profiles waits for another session's save
PROFILES_LOCK_TIMEOUT = 5.0


def save_profiles(filename, profiles, expected=_UNCHECKED, lock_timeout=PROFILES_LOCK_TIMEOUT, attempts=5,
                  retry_delay=0.05):
    """Write profiles to filename as {"profiles": [...]} (other top-level keys are kept), with a .bak.

    expected: the version (read_profiles_versioned) of the file the profiles are based on;
    if the file's content differs from it now (another tab, session or a text editor
    changed, created or deleted it), nothing is written and ProfilesChangedError is raised
    (A13). The comparison and the writes happen under a RunLock on <filename>.lock (the
    file stays, empty), so no other save can come in between; OSError if that lock is not
    free within lock_timeout seconds. Without expected, the file is saved unchecked.
    Returns the version of the saved file, the expected version of the next save based on
    these profiles (review).

    The previous content is copied byte for byte to <filename>.bak first (replacing an
    older backup, so only the state before the latest save is kept); if that fails,
    filename is left unchanged. Both files are written to a temporary file in the same
    folder, flushed to disk and then renamed, so a crash or power loss leaves a complete
    old or new file, never a half-written one. On Windows, reading or replacing a file fails
    while another session reads it at that moment (every app run reads profiles.json), so
    each read and replace is tried up to attempts times, retry_delay seconds apart (review).
    """
    with _file_lock(filename, lock_timeout):
        try:
            previous = _read_with_retry(filename.read_bytes, attempts, retry_delay)
        except FileNotFoundError:
            previous = None
        if expected is not _UNCHECKED and _version_of(previous) != expected:
            raise ProfilesChangedError(
                f'{filename.name} was changed in another tab or session, or by hand, since this page showed it')
        document = {'profiles': profiles}
        if previous is not None:
            _replace_with_retry(_backup_path(filename), previous, attempts, retry_delay)
            try:
                old = json.loads(previous.decode('utf-8-sig'))
            except ValueError:  # unreadable: nothing to keep (the .bak has it)
                old = None
            # other top-level keys (e.g. hand-added metadata) are kept in their order; a v3
            # file, whose keys are profile names, is not merged (review)
            if isinstance(old, dict) and 'profiles' in old:
                document = {**old, 'profiles': profiles}
        data = (json.dumps(document, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
        _replace_with_retry(filename, data, attempts, retry_delay)
    return _version_of(data)


def _version_of(content):
    """The version of a profiles file's content (bytes, or None for a missing file)."""
    return None if content is None else hashlib.sha256(content).hexdigest()


def _backup_path(filename):
    """Return the backup file of a profiles file: <filename>.bak."""
    return filename.with_name(filename.name + '.bak')
