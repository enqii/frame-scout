"""Shared helpers for the FrameScout app (app.py) and engine (framescout_engine.py).

This module uses only the Python standard library, so it can be imported and tested
without torch, Streamlit or any model download.

The user-facing error messages are still German (see backlog item I7).
"""
import hashlib
import json
import re
import unicodedata
from pathlib import Path

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
    "prompts" (generated + custom prompts) and "refs" (reference image paths, resolved
    relative to the JSON file's folder). Raises ValueError for invalid input.
    """
    raw = []
    if filename:
        data = json.loads(filename.read_text(encoding='utf-8-sig'))
        if isinstance(data, dict) and 'profiles' in data:
            raw = data['profiles']
        elif isinstance(data, dict):  # v3 migration: {name: [prompts, ...]}
            raw = [{'name': n, 'prompts': ps} for n, ps in data.items()]
        else:
            raise ValueError('JSON muss ein Objekt mit "profiles" sein (oder das bisherige v3-Format).')
        if not isinstance(raw, list):
            raise ValueError('"profiles" muss eine Liste sein.')
    for item in inline:
        fields = [s.strip() for s in item.split('|', 2)]
        raw.append({'name': fields[0], 'franchise': fields[1] if len(fields) > 1 else '',
                    'features': fields[2] if len(fields) > 2 else ''})
    if not raw:
        raise ValueError('Bitte --profiles oder mindestens ein --character angeben.')
    profiles = []
    names = set()
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError('Jedes Profil muss ein JSON-Objekt sein.')
        name = item.get('name', '')
        # compare the stripped name: it is the one stored and used as key (E10)
        if not isinstance(name, str) or not name.strip() or name.strip().lower() in names:
            raise ValueError(f'Profilname fehlt oder ist doppelt: {name!r}')
        names.add(name.strip().lower())
        franchise = item.get('franchise', '')
        features = item.get('features', '')
        prompts = item.get('prompts', [])
        refs = item.get('reference_images', [])
        if not isinstance(franchise, str) or not isinstance(features, str) or not isinstance(prompts, list) or not isinstance(refs, list):
            raise ValueError(f'Ungueltiges Profil: {name}')
        if any(not isinstance(x, str) or not x.strip() for x in prompts + refs):
            raise ValueError(f'Prompts und Referenzbilder muessen nichtleere Zeichenketten sein: {name}')
        profiles.append({'name': name.strip(), 'prompts': generic_prompts(name, franchise, features) + prompts,
                         'refs': [((filename.parent if filename else Path.cwd()) / x).resolve() for x in refs]})
    return profiles
