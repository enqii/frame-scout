"""Saving uploaded reference images without overwriting files (framescout_core)."""
from framescout_core import write_new_file


def test_first_file_gets_number_one_and_the_folder_is_created(tmp_path):
    folder = tmp_path / 'references' / 'baer'
    path = write_new_file(folder, 'reference', '.jpg', b'one')
    assert path == folder / 'reference-1.jpg'
    assert path.read_bytes() == b'one'


def test_existing_files_are_never_overwritten(tmp_path):
    # e.g. "Bär" and "Baer" share references/baer/ (A1); a later upload for one
    # profile must not replace the reference another profile points to
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
