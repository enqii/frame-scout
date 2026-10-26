"""Engine pipeline helpers: progress lines, JPEG draft size, crop batches and prefetching."""
import collections


def progress_line(done, total, new, cached, errors):
    """Return the progress line the engine prints to its log during the analysis.

    For people reading the log only: the app reads the progress from the status file
    (StatusReporter, A5), not from the log text (A11).
    """
    return f'Progress: {done}/{total} | New: {new} | Cached: {cached} | Errors: {errors}'


def progress_due(before, after, total, every=25):
    """Return True if the engine should print a progress line after going from before to after done photos.

    That is every `every` photos and once at the end. Photos can finish several at a time
    (one embedded batch, E2), so a multiple of `every` that was jumped over counts too.
    """
    return after > before and (after == total or after // every > before // every)


# Pillow's Image.thumbnail decodes JPEGs at a reduced scale only down to twice the
# requested size (reducing_gap=2) and resizes the rest of the way with its filter; the
# engine keeps the same quality margin for CLIP's input.
DRAFT_REDUCING_GAP = 2
# Names the drafted decoding in the cache signature of runs without person detection;
# change it if the decoding of those runs changes (the user decided in the PR #7 review
# that drafted and full-resolution embeddings are not mixed in the cache).
DRAFT_DECODING = f'jpeg-draft-{DRAFT_REDUCING_GAP}x-clip-size'


def draft_size(clip_size, person_detection):
    """Return the smallest edge length a photo may be decoded at for the analysis, or None.

    JPEG decoding can scale by 1/2, 1/4 or 1/8 on the fly (Image.draft), which makes it
    several times faster (E2). Without person detection CLIP sees only the whole photo,
    resized to clip_size, so twice that is enough. With person detection the photo is
    decoded at full resolution: a person crop (e.g. in a group photo) covers only part of
    it and would lose detail.
    """
    return None if person_detection else DRAFT_REDUCING_GAP * clip_size


def group_batches(items, batch_size, size):
    """Yield lists of consecutive items with at most batch_size crops each.

    size(item) is the number of crops of an item (a photo). Items are added to a list as
    long as their crops fit, so CLIP embeds the crops of several photos in one forward
    pass instead of one photo at a time (E2), and a list never needs a second, small pass
    for a few leftover crops (review). An item with more than batch_size crops is a list
    on its own. Items are read lazily: a full list is yielded before the next item is
    requested; otherwise a list is yielded when the next item does not fit any more.
    """
    if batch_size < 1:
        raise ValueError('batch_size must be at least 1')
    group, count = [], 0
    for item in items:
        n = size(item)
        if group and count + n > batch_size:
            yield group
            group, count = [], 0
        group.append(item)
        count += n
        if count >= batch_size:
            yield group
            group, count = [], 0
    if group:
        yield group


def store_group(group, store, failed):
    """Store a group of items with store(group); return the number of items stored.

    store must store all items or none (one transaction). If it raises and the group has
    several items, each item is stored on its own, so a single broken photo or a failure
    that hits only one of them (review) does not fail the whole group, and failed(item,
    exc) reports every item that still fails with its own error. KeyboardInterrupt and
    other BaseExceptions are not caught.
    """
    try:
        store(group)
        return len(group)
    except Exception as exc:
        if len(group) == 1:
            failed(group[0], exc)
            return 0
    stored = 0
    for item in group:
        try:
            store([item])
            stored += 1
        except Exception as exc:
            failed(item, exc)
    return stored


def prefetch(submit, items, depth):
    """Yield (item, future) in input order, with up to depth items submitted ahead.

    submit(item) starts the work (e.g. ThreadPoolExecutor.submit) and returns a Future.
    The work for later items runs while the consumer handles the current one (decoding
    photos in parallel, E2), but never more than depth items ahead, which bounds memory.
    Errors stay in the futures: future.result() raises them for that item only. Closing
    the generator (e.g. on KeyboardInterrupt) cancels the work that has not started yet.
    """
    if depth < 1:
        raise ValueError('depth must be at least 1')
    queue = collections.deque()
    try:
        for item in items:
            queue.append((item, submit(item)))
            if len(queue) >= depth:
                yield queue.popleft()
        while queue:
            yield queue.popleft()
    finally:
        for _, future in queue:
            future.cancel()
