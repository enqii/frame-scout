"""Helpers of the engine's analysis pipeline (E2): batching, prefetching, draft size, progress."""
from concurrent.futures import Future, ThreadPoolExecutor

import pytest

from framescout_core import draft_size, group_batches, prefetch, progress_due


# --- group_batches: crops of several photos go through CLIP together ---

def sizes(groups):
    return [[n for _, n in group] for group in groups]


def test_photos_are_grouped_until_the_batch_is_full():
    items = [('a', 1), ('b', 1), ('c', 1), ('d', 1), ('e', 1)]
    groups = list(group_batches(items, 2, size=lambda item: item[1]))
    assert [[name for name, _ in g] for g in groups] == [['a', 'b'], ['c', 'd'], ['e']]


def test_a_group_never_exceeds_the_batch_size():
    # each group is one CLIP forward pass of at most batch_size crops (review: a group of
    # 9 crops at batch size 8 needed a second pass for a single crop); a photo whose crops
    # do not fit any more starts the next group, a photo with more crops than batch_size
    # is a group on its own (embedded in several passes)
    assert sizes(group_batches([('a', 3), ('b', 13), ('c', 2), ('d', 5), ('e', 1), ('f', 7), ('g', 2)], 8,
                               size=lambda item: item[1])) == [[3], [13], [2, 5, 1], [7], [2]]


def test_order_is_kept_and_nothing_is_lost():
    items = [(str(i), 1 + i % 4) for i in range(50)]
    groups = list(group_batches(items, 7, size=lambda item: item[1]))
    assert [item for group in groups for item in group] == items
    assert all(sum(n for _, n in group) <= 7 for group in groups)
    # a group is closed only when the next photo does not fit
    for group, following in zip(groups, groups[1:]):
        assert sum(n for _, n in group) + following[0][1] > 7
    assert all(group for group in groups)


def test_batch_size_one_embeds_photo_by_photo():
    assert sizes(group_batches([('a', 1), ('b', 3)], 1, size=lambda item: item[1])) == [[1], [3]]


def test_no_photos_no_groups():
    assert list(group_batches([], 8, size=len)) == []


def test_group_batches_reads_its_input_lazily():
    # the engine feeds it a generator over decoding threads: a group must be yielded
    # before later photos are requested, so embedding overlaps with decoding
    pulled = []

    def source():
        for i in range(6):
            pulled.append(i)
            yield i

    groups = group_batches(source(), 2, size=lambda item: 1)
    assert next(groups) == [0, 1]
    assert pulled == [0, 1]


def test_group_batches_rejects_an_invalid_batch_size():
    with pytest.raises(ValueError):
        list(group_batches([1], 0, size=lambda item: 1))


# --- prefetch: bounded, ordered decoding ahead of the consumer ---

def resolved(value):
    future = Future()
    future.set_result(value)
    return future


def test_prefetch_yields_items_and_futures_in_input_order():
    with ThreadPoolExecutor(4) as pool:
        results = [(item, future.result()) for item, future in
                   prefetch(lambda x: pool.submit(lambda: x * x), range(20), depth=3)]
    assert results == [(i, i * i) for i in range(20)]


def test_prefetch_submits_at_most_depth_items_ahead():
    submitted = []

    def submit(item):
        submitted.append(item)
        return resolved(item)

    stream = prefetch(submit, range(10), depth=3)
    assert submitted == []  # nothing happens before the first item is requested
    next(stream)
    assert submitted == [0, 1, 2]
    next(stream)
    assert submitted == [0, 1, 2, 3]
    assert [item for item, _ in stream] == list(range(2, 10))


def test_prefetch_passes_errors_through_the_future():
    def submit(item):
        future = Future()
        if item == 1:
            future.set_exception(OSError('broken file'))
        else:
            future.set_result(item)
        return future

    futures = list(prefetch(submit, range(3), depth=2))
    assert [item for item, _ in futures] == [0, 1, 2]
    with pytest.raises(OSError, match='broken file'):
        futures[1][1].result()
    assert futures[2][1].result() == 2


def test_closing_prefetch_cancels_the_work_not_yet_started():
    # an interrupted analysis must not keep decoding photos nobody will embed
    futures = []

    def submit(item):
        futures.append(Future())  # never started
        return futures[-1]

    stream = prefetch(submit, range(10), depth=4)
    next(stream)
    stream.close()
    assert len(futures) == 4
    assert all(f.cancelled() for f in futures[1:])
    assert not futures[0].cancelled()  # already handed to the consumer


def test_prefetch_rejects_an_invalid_depth():
    with pytest.raises(ValueError):
        next(prefetch(resolved, [1], depth=0))


# --- draft_size: how far JPEG decoding may scale a photo down (Image.draft) ---

def test_without_person_detection_photos_are_decoded_at_twice_the_clip_input_size():
    # same reducing gap as Pillow's Image.thumbnail: the DCT scaling stays at least
    # twice the final size, the last step is CLIP's own bicubic resize
    assert draft_size(224, person_detection=False) == 448


def test_with_person_detection_photos_are_decoded_at_full_resolution():
    # person crops need the detail: a person in a group photo covers few pixels
    assert draft_size(224, person_detection=True) is None


# --- progress_due: when the engine writes a progress line ---

@pytest.mark.parametrize('before,after,total,expected', [
    (23, 24, 100, False),
    (24, 25, 100, True),
    (20, 30, 100, True),   # several photos finished at once (one embedded batch)
    (26, 49, 100, False),
    (98, 99, 99, True),    # always at the end
    (0, 0, 10, False),
    (10, 10, 10, False),   # nothing new: the final line was already written
])
def test_progress_due(before, after, total, expected):
    assert progress_due(before, after, total) is expected


def test_progress_due_interval():
    assert progress_due(9, 10, 100, every=10) is True
    assert progress_due(10, 11, 100, every=10) is False
