"""File-name slugs for result pages and reference folders (framescout_core)."""
import hashlib
import unicodedata

import pytest

from framescout_core import EXT, profile_slugs, slugify


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


@pytest.mark.parametrize('form', ['NFC', 'NFD'])
def test_transliteration_does_not_depend_on_the_unicode_normal_form(form):
    assert slugify(unicodedata.normalize(form, 'Bär Größe')) == 'baer-groesse'
    # the hash fallback, too (Hangul decomposes into Jamo under NFD)
    assert slugify(unicodedata.normalize(form, '고양이')) == hashlib.sha256('고양이'.encode()).hexdigest()[:10]


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


def test_profile_slugs_are_unique_in_list_order():
    names = ['Rotes Auto', 'rotes-auto', 'ROTES AUTO!', 'Golden Retriever']
    assert profile_slugs(names) == ['rotes-auto', 'rotes-auto-2', 'rotes-auto-3', 'golden-retriever']


def test_profile_slugs_never_reuse_a_generated_suffix():
    assert profile_slugs(['a', 'a!', 'a-2']) == ['a', 'a-2', 'a-2-2']


def test_profile_slugs_match_slugify_without_collisions():
    names = ['Bär', 'Café', '猫']
    assert profile_slugs(names) == [slugify(n) for n in names]
    assert profile_slugs([]) == []


def test_supported_extensions():
    assert EXT == {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff'}
