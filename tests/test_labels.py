"""Crop labels shown in the HTML gallery (framescout_core.crop_label)."""
import pytest

from framescout_core import FULL_IMAGE_LABEL, crop_label


def test_full_image_label_is_english():
    assert FULL_IMAGE_LABEL == 'Full image'


@pytest.mark.parametrize('stored, shown', [
    ('Full image', 'Full image'),
    ('Person 3', 'Person 3'),
    # cache rows written before the translation (I7) keep the German label
    ('Gesamtbild', 'Full image'),
])
def test_stored_labels_are_shown_in_english(stored, shown):
    assert crop_label(stored) == shown
