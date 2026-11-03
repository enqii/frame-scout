"""Exporting a result list as a CSV table and a file list (F5)."""
import csv
import io
from datetime import datetime
from pathlib import Path

from ._common import _publish_new, _publish_via_temp
from .marks import MARK_MATCH, MARK_NO_MATCH


# Export (F5): the ranked photos of one profile of the last search leave the app as a CSV
# table and a text file with one path per line, e.g. for a cataloging program. Both are
# written to results/exports/, never next to the photos; an export never replaces a file
# (an earlier export or anything else), and no cleanup category lists the folder: exports
# are the user's files. The paths are the absolute ones of this computer (like the cache
# and the marks, E8/A21), so a list made on another PC or after moving photos may name
# files that are not there.
EXPORTS_DIR = 'exports'
EXPORT_COLUMNS = ('rank', 'path', 'score', 'text_similarity', 'image_similarity', 'crop', 'mark')
# the mark column: an open (or no) mark is an empty cell
EXPORT_MARK_TEXT = {MARK_MATCH: 'match', MARK_NO_MATCH: 'no match'}
# names tried for one export (name, name-2, name-3, ...) before it fails
EXPORT_MAX_NAMES = 1000


def export_cards(cards, marks, only_matches=False):
    """Return the result cards to export, in rank order: all, or with only_matches those marked as match.

    cards: the cards of one profile of the result file; marks: {photo path: mark} of that
    profile, or None if the marks file cannot be read (ValueError with only_matches). A
    photo marked as match outside this result list has no rank or score: it is not exported.
    """
    if not only_matches:
        return list(cards)
    if marks is None:
        raise ValueError('the marks cannot be read')
    return [card for card in cards if marks.get(card['path']) == MARK_MATCH]


def _number(value):
    return '' if value is None else f'{value:.4f}'


def export_csv(cards, marks):
    """Return the CSV table of cards (a header and one row per card, columns EXPORT_COLUMNS).

    marks as for export_cards; None leaves the mark column empty. Comma-separated with
    "\\r\\n" line ends and a "." as decimal point (RFC 4180), quoted where needed.
    """
    out = io.StringIO(newline='')
    writer = csv.writer(out)
    writer.writerow(EXPORT_COLUMNS)
    for card in cards:
        mark = EXPORT_MARK_TEXT.get((marks or {}).get(card['path']), '')
        writer.writerow([card['rank'], card['path'], _number(card['score']), _number(card['text']),
                         _number(card['visual']), card['label'], mark])
    return out.getvalue()


def export_file_list(cards):
    """Return the paths of cards, one per line ("\\n"), in rank order."""
    return ''.join(card['path'] + '\n' for card in cards)


def export_name(slug, now, only_matches=False):
    """Return the base name of an export: <slug>-<YYYYMMDD-HHMMSS>[-matches]."""
    return f'{slug}-{now:%Y%m%d-%H%M%S}' + ('-matches' if only_matches else '')


def _write_new(path, data):
    """Write data to the new file path (FileExistsError if it exists; never a partial file)."""
    _publish_via_temp(path, lambda tmp: tmp.write_bytes(data), _publish_new)


def export_result_list(results, slug, cards, marks, only_matches=False, now=None):
    """Write the result list of one profile to results/exports/; return (CSV path, file list path).

    results: the results folder; slug: the profile's file name part (its gallery's name
    without .html); cards, marks, only_matches: as for export_cards. The CSV table
    (export_csv) is UTF-8 with a byte order mark, so that Excel decodes non-ASCII paths as
    UTF-8; the byte order mark does not set the delimiter: Excel splits a double-clicked CSV
    at the list separator of the system locale, which is ";" in German and other
    comma-decimal locales, so there the whole row lands in one column (the user guide points
    to Data -> From Text/CSV; a ";" option is F9). The file list (export_file_list) is UTF-8
    without a byte order mark. Both get the same name
    (export_name, from now or the current time) plus "-2", "-3", ... while either name is
    taken: nothing is ever replaced. Raises ValueError if there is nothing to export
    (nothing is written then) and OSError if a file cannot be written.
    """
    chosen = export_cards(cards, marks, only_matches)
    if not chosen:
        raise ValueError('there is no photo to export')
    folder = Path(results) / EXPORTS_DIR
    folder.mkdir(parents=True, exist_ok=True)
    base = export_name(slug, now or datetime.now(), only_matches)
    table = export_csv(chosen, marks).encode('utf-8-sig')
    listing = export_file_list(chosen).encode('utf-8')
    for n in range(1, EXPORT_MAX_NAMES + 1):
        name = base if n == 1 else f'{base}-{n}'
        csv_path, txt_path = folder / f'{name}.csv', folder / f'{name}.txt'
        if csv_path.exists() or txt_path.exists():
            continue
        try:
            _write_new(csv_path, table)
        except FileExistsError:
            continue
        try:
            _write_new(txt_path, listing)
        except FileExistsError:  # taken meanwhile: the pair moves on to the next name
            csv_path.unlink(missing_ok=True)
            continue
        except BaseException:
            csv_path.unlink(missing_ok=True)
            raise
        return csv_path, txt_path
    raise FileExistsError(f'no free name for {base} in {folder}')
