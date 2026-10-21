"""File-name slugs for result pages and reference folders (framescout_core)."""
import hashlib

import pytest

from framescout_core import EXT, slugify


@pytest.mark.parametrize('name, slug', [
    ('Red car', 'red-car'),
    ('  Rotes  Auto! ', 'rotes-auto'),
    ('2B', '2b'),
    ('Golden_Retriever (Dog)', 'golden-retriever-dog'),
])
def test_ascii_names(name, slug):
    assert slugify(name) == slug


@pytest.mark.parametrize('name, slug', [
    ('Bär', 'baer'),
    ('Größe Ü', 'groesse-ue'),
    ('Straße', 'strasse'),
    ('Café crème', 'cafe-creme'),
    ('Ñandú', 'nandu'),
    ('Ærø Œuvre', 'aero-oeuvre'),
    ('Łódź', 'lodz'),
])
def test_latin_letters_with_diacritics_are_transliterated(name, slug):
    assert slugify(name) == slug


def test_name_without_usable_characters_falls_back_to_a_stable_hash():
    assert slugify('!!!') == hashlib.sha256('!!!'.encode()).hexdigest()[:10]
    assert slugify('???') != slugify('!!!')


def test_non_latin_name_falls_back_to_a_stable_hash():
    assert slugify('猫') == hashlib.sha256('猫'.encode()).hexdigest()[:10]
    assert slugify('猫') != slugify('犬')


@pytest.mark.parametrize('name', ['CON', 'prn', 'Aux', 'nul', 'COM1', 'lpt9'])
def test_windows_device_names_are_not_used_as_slugs(name):
    slug = slugify(name)
    assert slug.startswith(name.lower())
    assert slug != name.lower()


def test_long_names_are_shortened_without_a_trailing_dash():
    slug = slugify('word ' * 40)
    assert len(slug) <= 60
    assert slug.startswith('word-word') and not slug.endswith('-')


def test_supported_extensions():
    assert EXT == {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff'}
