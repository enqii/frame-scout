"""Moving a renamed profile's reference images to the folder of its new name (A1, review)."""
import json
import os

import pytest

import framescout_core
from framescout_core import (finish_reference_move, save_profiles, stage_reference_move, undo_reference_move,
                             update_backup_references)


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


@pytest.mark.skipif(os.name != 'nt', reason='directory junctions are a Windows feature')
def test_a_references_folder_that_is_a_junction_elsewhere_works(tmp_path):
    # review: resolving the new path left the project folder and relative_to raised ValueError
    _winapi = pytest.importorskip('_winapi')
    target = tmp_path / 'elsewhere' / 'refs'
    (target / 'red-car').mkdir(parents=True)
    (target / 'red-car' / 'reference-1.jpg').write_bytes(b'one')
    project = tmp_path / 'project'
    project.mkdir()
    _winapi.CreateJunction(str(target), str(project / 'references'))
    new_refs, staged = stage(project, ['references/red-car/reference-1.jpg'])
    assert new_refs == ['references/blue-car/reference-1.jpg']
    assert finish_reference_move(staged, project / 'references') == []
    assert (target / 'blue-car' / 'reference-1.jpg').read_bytes() == b'one'
    assert not (target / 'red-car').exists()


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


def rename_red_car(project, previous):
    """Rename "Red car" to "Blue car" like the app: stage, save (writes the .bak), return staged."""
    path = project / 'profiles.json'
    path.write_text(json.dumps(previous, ensure_ascii=False), encoding='utf-8')
    refs = previous['profiles'][0]['reference_images']
    others = previous['profiles'][1:]
    new_refs, staged = stage(project, refs, others=others)
    save_profiles(path, [{'name': 'Blue car', 'reference_images': new_refs}] + others)
    return path, staged


def test_the_backup_points_to_the_moved_files_after_a_rename(project):
    # review: restoring profiles.json.bak after a rename pointed at removed file names
    (project / 'photos').mkdir()
    (project / 'photos' / 'bike.jpg').write_bytes(b'bike')
    previous = {'version': 2, 'profiles': [
        {'name': 'Red car', 'reference_images': ['references/red-car/reference-1.jpg',
                                                 'references/red-car/reference-2.png']},
        {'name': 'Bike', 'reference_images': ['photos/bike.jpg']}], 'note': 'mine'}
    path, staged = rename_red_car(project, previous)
    assert update_backup_references(path, staged, project) is True
    backup = json.loads((project / 'profiles.json.bak').read_text(encoding='utf-8'))
    assert list(backup) == ['version', 'profiles', 'note']
    assert backup['version'] == 2 and backup['note'] == 'mine'
    assert backup['profiles'] == [
        {'name': 'Red car', 'reference_images': ['references/blue-car/reference-1.jpg',
                                                 'references/blue-car/reference-2.png']},
        {'name': 'Bike', 'reference_images': ['photos/bike.jpg']}]
    assert finish_reference_move(staged, project / 'references') == []
    for ref in backup['profiles'][0]['reference_images'] + backup['profiles'][1]['reference_images']:
        assert (project / ref).is_file()


def test_the_backup_is_flushed_to_disk_before_it_replaces_the_old_one(project, monkeypatch):
    previous = {'profiles': [{'name': 'Red car', 'reference_images': ['references/red-car/reference-1.jpg']}]}
    path, staged = rename_red_car(project, previous)
    events = []
    real_fsync, real_replace = framescout_core.os.fsync, framescout_core.os.replace

    def fsync(fd):
        events.append('fsync')
        real_fsync(fd)

    def replace(src, dst):
        events.append(('replace', os.path.basename(dst)))
        real_replace(src, dst)

    monkeypatch.setattr(framescout_core.os, 'fsync', fsync)
    monkeypatch.setattr(framescout_core.os, 'replace', replace)
    assert update_backup_references(path, staged, project) is True
    assert events == ['fsync', ('replace', 'profiles.json.bak')]


def test_nothing_is_rewritten_without_moved_files(project):
    previous = {'profiles': [{'name': 'Red car', 'reference_images': ['references/red-car/reference-1.jpg']}]}
    path = project / 'profiles.json'
    path.write_text(json.dumps(previous), encoding='utf-8')
    save_profiles(path, previous['profiles'])
    before = (project / 'profiles.json.bak').read_bytes()
    assert update_backup_references(path, [], project) is True
    assert (project / 'profiles.json.bak').read_bytes() == before


@pytest.mark.parametrize('content, usable', [
    (b'{"Red car": ["a red car"]}', True),  # v3: no reference paths, restoring works as is
    (b'{"profiles": [', False),             # unreadable: cannot be updated
    (b'', False),
])
def test_a_backup_in_the_v3_format_or_unreadable_is_left_alone(project, content, usable):
    path = project / 'profiles.json'
    (project / 'profiles.json.bak').write_bytes(content)
    _, staged = stage(project, ['references/red-car/reference-1.jpg'])
    assert update_backup_references(path, staged, project) is usable
    assert (project / 'profiles.json.bak').read_bytes() == content


def test_a_missing_backup_needs_no_update(project):
    _, staged = stage(project, ['references/red-car/reference-1.jpg'])
    assert update_backup_references(project / 'profiles.json', staged, project) is True
    assert not (project / 'profiles.json.bak').exists()


def test_a_failed_backup_rewrite_raises_and_keeps_the_old_backup(project, monkeypatch):
    previous = {'profiles': [{'name': 'Red car', 'reference_images': ['references/red-car/reference-1.jpg']}]}
    path, staged = rename_red_car(project, previous)
    before = (project / 'profiles.json.bak').read_bytes()

    def replace(src, dst):
        raise PermissionError('backup not writable')

    monkeypatch.setattr(framescout_core.os, 'replace', replace)
    with pytest.raises(PermissionError):
        update_backup_references(path, staged, project)
    assert (project / 'profiles.json.bak').read_bytes() == before
