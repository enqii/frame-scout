"""Shared helpers for the FrameScout app (app.py) and engine (framescout_engine.py).

This module uses only the Python standard library, so it can be imported and tested
without torch, Streamlit or any model download.

The user-facing error messages are still German (see backlog item I7).
"""
import hashlib
import json
import re
from pathlib import Path

# Supported image file extensions (lowercase, with leading dot).
EXT = frozenset({'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff'})


def slugify(s):
    """Return a file-name-safe slug for a profile name."""
    return re.sub('[^a-z0-9]+', '-', s.lower()).strip('-') or hashlib.sha256(s.encode()).hexdigest()[:10]


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
        if not isinstance(name, str) or not name.strip() or name.lower() in names:
            raise ValueError(f'Profilname fehlt oder ist doppelt: {name!r}')
        names.add(name.lower())
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
