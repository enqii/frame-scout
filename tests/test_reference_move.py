"""Moving a renamed profile's reference images to the folder of its new name (A1, review)."""
import os

import pytest

import framescout_core
from framescout_core import finish_reference_move, stage_reference_move, undo_reference_move


@pytest.fixture
def project(tmp_path):
    refs = tmp_path / 'references'
    (refs / 'red-car').mkdir(parents=True)
    (refs / 'red-car' / 'reference-1.jpg').write_bytes(b'one')
    (refs / 'red-car' / 'reference-2.png').write_bytes(b'two')
    return tmp_path


def stage(project, refs, folder='blue-car', others=()):
    return stage_reference_move(refs, project / 'references' / folder, project / 'references', project, others)


def test_a_renamed_profile_gets_its_files_under_the_new_folder(project):
    refs = ['references/red-car/reference-1.jpg', 'references/red-car/reference-2.png']
    new_refs, staged = stage(project, refs)
    assert new_refs == ['references/blue-car/reference-1.jpg', 'references/blue-car/reference-2.png']
    # until the profiles are saved, the old and the new paths both exist (crash safety)
    for old, new in zip(refs, new_refs):
        assert (project / old).read_bytes() == (project / new).read_bytes()
    assert finish_reference_move(staged, project / 'references') == []
    assert sorted(p.relative_to(project).as_posix() for p in (project / 'references').rglob('*')) == [
        'references/blue-car', 'references/blue-car/reference-1.jpg', 'references/blue-car/reference-2.png']
    assert (project / new_refs[0]).read_bytes() == b'one'


def test_undo_removes_only_the_new_names(project):
    refs = ['references/red-car/reference-1.jpg']
    new_refs, staged = stage(project, refs)
    undo_reference_move(staged)
    assert not (project / new_refs[0]).exists()
    assert (project / refs[0]).read_bytes() == b'one'


def test_files_of_other_profiles_and_leftovers_stay_in_the_old_folder(project):
    # e.g. a folder shared by two profiles before A1, or files removed from the profile
    (project / 'references' / 'red-car' / 'reference-3.jpg').write_bytes(b'leftover')
    others = [{'name': 'Red Car!', 'reference_images': ['references/red-car/reference-2.png']}]
    refs = ['references/red-car/reference-1.jpg', 'references/red-car/reference-2.png']
    new_refs, staged = stage(project, refs, others=others)
    assert new_refs == ['references/blue-car/reference-1.jpg', 'references/red-car/reference-2.png']
    assert finish_reference_move(staged, project / 'references') == []
    assert sorted(p.name for p in (project / 'references' / 'red-car').iterdir()) == [
        'reference-2.png', 'reference-3.jpg']


def test_paths_outside_the_references_folder_and_missing_files_are_kept(project):
    (project / 'photos').mkdir()
    (project / 'photos' / 'car.jpg').write_bytes(b'photo')
    refs = ['photos/car.jpg', 'references/red-car/missing.jpg', str(project / 'photos' / 'car.jpg')]
    new_refs, staged = stage(project, refs)
    assert new_refs == refs
    assert staged == []
    assert (project / 'photos' / 'car.jpg').read_bytes() == b'photo'


def test_files_already_in_the_target_folder_are_not_moved(project):
    refs = ['references/red-car/reference-1.jpg']
    assert stage(project, refs, folder='red-car') == (refs, [])


def test_a_taken_name_in_the_target_folder_is_never_overwritten(project):
    target = project / 'references' / 'blue-car'
    target.mkdir()
    (target / 'reference-1.jpg').write_bytes(b'leftover')
    new_refs, staged = stage(project, ['references/red-car/reference-1.jpg'])
    assert new_refs == ['references/blue-car/reference-2.jpg']
    assert (target / 'reference-1.jpg').read_bytes() == b'leftover'
    assert (target / 'reference-2.jpg').read_bytes() == b'one'


def test_the_same_file_listed_twice_is_moved_once(project):
    refs = ['references/red-car/reference-1.jpg', './references/red-car/reference-1.jpg']
    new_refs, staged = stage(project, refs)
    assert new_refs == ['references/blue-car/reference-1.jpg'] * 2
    assert len(staged) == 1


def test_without_hard_links_the_file_is_copied(project, monkeypatch):
    def link(src, dst):
        raise OSError('hard links are not supported on this file system')

    monkeypatch.setattr(framescout_core.os, 'link', link)
    new_refs, staged = stage(project, ['references/red-car/reference-1.jpg'])
    assert (project / new_refs[0]).read_bytes() == b'one'
    assert finish_reference_move(staged, project / 'references') == []
    assert not (project / 'references' / 'red-car' / 'reference-1.jpg').exists()


def test_a_failure_while_staging_undoes_the_files_staged_before(project, monkeypatch):
    real_link, calls = os.link, []

    def link(src, dst):
        calls.append(dst)
        if len(calls) == 2:
            raise PermissionError('access denied')
        real_link(src, dst)

    def copy(src, dst):
        raise PermissionError('access denied')

    monkeypatch.setattr(framescout_core.os, 'link', link)
    monkeypatch.setattr(framescout_core, '_copy_new', copy)
    with pytest.raises(PermissionError):
        stage(project, ['references/red-car/reference-1.jpg', 'references/red-car/reference-2.png'])
    assert sorted(p.name for p in (project / 'references' / 'red-car').iterdir()) == [
        'reference-1.jpg', 'reference-2.png']
    assert list((project / 'references' / 'blue-car').iterdir()) == []


def test_an_old_name_that_cannot_be_removed_is_reported(project, monkeypatch):
    new_refs, staged = stage(project, ['references/red-car/reference-1.jpg'])
    real_unlink = framescout_core.Path.unlink

    def unlink(self, missing_ok=False):
        if self.name == 'reference-1.jpg' and self.parent.name == 'red-car':
            raise PermissionError('in use')
        real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(framescout_core.Path, 'unlink', unlink)
    problems = finish_reference_move(staged, project / 'references')
    assert len(problems) == 1 and 'reference-1.jpg' in problems[0]
    assert (project / new_refs[0]).read_bytes() == b'one'
