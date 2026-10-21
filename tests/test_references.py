"""Saving uploaded reference images without overwriting files (framescout_core)."""
import os

import pytest

from framescout_core import reference_folder, write_new_file


def test_first_file_gets_number_one_and_the_folder_is_created(tmp_path):
    folder = tmp_path / 'references' / 'baer'
    path = write_new_file(folder, 'reference', '.jpg', b'one')
    assert path == folder / 'reference-1.jpg'
    assert path.read_bytes() == b'one'


def test_existing_files_are_never_overwritten(tmp_path):
    # e.g. a folder shared by "Bär" and "Baer" before A1, or files of a deleted profile:
    # a later upload must not replace a reference another profile may point to
    (tmp_path / 'reference-1.jpg').write_bytes(b'other profile')
    (tmp_path / 'reference-2.jpg').write_bytes(b'other profile 2')
    path = write_new_file(tmp_path, 'reference', '.jpg', b'new')
    assert path.name == 'reference-3.jpg'
    assert (tmp_path / 'reference-1.jpg').read_bytes() == b'other profile'
    assert (tmp_path / 'reference-2.jpg').read_bytes() == b'other profile 2'


def test_gaps_are_reused_and_numbers_are_per_extension(tmp_path):
    (tmp_path / 'reference-2.jpg').write_bytes(b'x')
    assert write_new_file(tmp_path, 'reference', '.jpg', b'a').name == 'reference-1.jpg'
    assert write_new_file(tmp_path, 'reference', '.jpg', b'b').name == 'reference-3.jpg'
    assert write_new_file(tmp_path, 'reference', '.png', b'c').name == 'reference-1.png'


def test_a_profile_gets_the_folder_of_its_slug(tmp_path):
    others = [{'name': 'Dog', 'reference_images': ['references/dog/reference-1.jpg']}]
    assert reference_folder(tmp_path / 'references', 'Bär', others, tmp_path) == tmp_path / 'references' / 'baer'


def test_a_folder_with_references_of_another_profile_is_not_shared(tmp_path):
    # A1: "Bär" and "Baer" have the same slug; the second one gets its own folder
    others = [{'name': 'Bär', 'reference_images': ['references/baer/reference-1.jpg']}]
    assert reference_folder(tmp_path / 'references', 'Baer', others, tmp_path) == tmp_path / 'references' / 'baer-2'


def test_the_next_free_number_is_used(tmp_path):
    others = [{'name': 'Bär', 'reference_images': ['references/baer/reference-1.jpg']},
              {'name': 'Baer', 'reference_images': ['references/baer-2/reference-1.png']},
              {'name': 'Bärenfoto'}]
    assert reference_folder(tmp_path / 'references', 'BAER!', others, tmp_path) == tmp_path / 'references' / 'baer-3'


def test_profiles_without_references_in_the_folder_do_not_block_it(tmp_path):
    # files of deleted profiles or of removed references stay on disk, but write_new_file
    # never overwrites them, so the folder can still be used
    (tmp_path / 'references' / 'baer').mkdir(parents=True)
    (tmp_path / 'references' / 'baer' / 'reference-1.jpg').write_bytes(b'deleted profile')
    others = [{'name': 'Bär'}, {'name': 'Bär 2', 'reference_images': ['photos/baer/bear.jpg']}]
    assert reference_folder(tmp_path / 'references', 'Baer', others, tmp_path) == tmp_path / 'references' / 'baer'


def test_reference_paths_are_compared_after_resolving(tmp_path):
    others = [{'name': 'Bär', 'reference_images': ['./references/x/../baer/reference-1.jpg']}]
    assert reference_folder(tmp_path / 'references', 'Baer', others, tmp_path) == tmp_path / 'references' / 'baer-2'


@pytest.mark.skipif(os.name != 'nt', reason='Windows paths are case-insensitive')
def test_reference_paths_are_compared_case_insensitively_on_windows(tmp_path):
    others = [{'name': 'Bär', 'reference_images': ['References\\BAER\\reference-1.jpg']}]
    assert reference_folder(tmp_path / 'references', 'Baer', others, tmp_path) == tmp_path / 'references' / 'baer-2'
