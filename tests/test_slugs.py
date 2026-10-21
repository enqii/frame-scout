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


def test_name_without_usable_characters_falls_back_to_a_stable_hash():
    assert slugify('!!!') == hashlib.sha256('!!!'.encode()).hexdigest()[:10]
    assert slugify('???') != slugify('!!!')


def test_supported_extensions():
    assert EXT == {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff'}
