"""Quick search: one search text over the photos already analyzed, without a profile (F10).

The engine's --quick-query scores only photos with a current cache row of the search's
signature (no analysis, no person detector) and writes its gallery and result file to the
folder QUICK_DIR inside the output folder, with thumbnails of its own, so the galleries,
results.json and marks.json of the profile search stay untouched. The cleanup of the output
folder does not look into it; the quick search cleans its own folder (auto_cleanup).
"""
from .profiles import generic_prompts

QUICK_DIR = 'quick'
QUICK_GALLERY = 'quick.html'
# characters of a quick search text; CLIP reads at most 77 tokens of a prompt anyway
QUICK_QUERY_MAX = 300


def quick_profile(query):
    """Return the search profile of a quick search for query, as load_profiles builds one of that name.

    White space (also line breaks) is joined to single spaces; the text is not split at
    "|" as a --character is. Raises ValueError for an empty text or one longer than
    QUICK_QUERY_MAX characters.
    """
    name = ' '.join(str(query).split())
    if not name:
        raise ValueError('The quick search text is empty.')
    if len(name) > QUICK_QUERY_MAX:
        raise ValueError(f'The quick search text is longer than {QUICK_QUERY_MAX} characters.')
    prompts = generic_prompts(name)
    return {'name': name, 'prompts': prompts, 'generated': len(prompts), 'refs': []}


def quick_photos(paths, fallbacks, current, trouble=None):
    """Return (photos to score, photos not analyzed) of a quick search, both in the order of paths.

    paths: the photos of the scan; fallbacks: {partner: RAW file} (raw_fallbacks, E30): a
    partner without a current row is scored through its RAW file if that has one (a full
    search analyzed it in the partner's place), once per shot; current(path): whether path
    has a cache row of the search's signature with its current modification time and size.
    A photo whose check raises counts as not analyzed, after trouble(path, exc) if given.
    A partner of a shot whose other partner is analyzed counts as not analyzed too, although
    a full search would not analyze it either.
    """
    def has_row(path):
        try:
            return current(path)
        except Exception as exc:
            if trouble is not None:
                trouble(path, exc)
            return False

    chosen, missing, used = [], [], set()
    for path in paths:
        if has_row(path):
            chosen.append(path)
            continue
        raw = fallbacks.get(path)
        if raw is not None and raw not in used and has_row(raw):
            used.add(raw)
            chosen.append(raw)
            continue
        missing.append(path)
    return chosen, missing


def quick_scope_text(photos, analyzed):
    """Return what the app says before a quick search: how many photos it searches and how many not.

    photos: the photos counted in the folders; analyzed: those with a current cache row of
    the current settings (analyzed_photos).
    """
    if photos <= 0:
        return 'No supported photos found in these folders: there is nothing to search.'
    analyzed = min(max(analyzed, 0), photos)
    if not analyzed:
        return (f'None of the {photos:,} photos is analyzed with these AI settings yet, so a quick search finds '
                'nothing. Start a search with your profiles first: it analyzes them.')
    if analyzed == photos:
        return f'All {photos:,} photos are analyzed with these AI settings and searched.'
    return (f'{analyzed:,} of {photos:,} photos are analyzed with these AI settings and searched; the other '
            f'{photos - analyzed:,} are not searched until a search with your profiles analyzes them.')


def quick_note(searched, not_analyzed):
    """Return the note of a quick search's gallery and results: what was searched and why its scores differ."""
    text = f'Quick search over the {searched:,} photos analyzed with these AI settings'
    text += (f'; {not_analyzed:,} {"photo was" if not_analyzed == 1 else "photos were"} not analyzed and not '
             'searched.'
             if not_analyzed else '.')
    return text + (' The scores are scaled over the photos searched, so they differ from those of a search with '
                   'profiles.')
