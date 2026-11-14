"""The app's state line next to its title and what a search needs at the Start button (F27)."""
from .run_status import FINAL_PHASES, PHASE_LABELS, _count, analysis_only, status_fraction

# the tab in which a missing need is fixed, as the app names its tabs
START_NEEDS_TAB = {'profiles': 'Search profiles', 'photos': 'Photo source', 'model': 'AI settings'}
# the tab with a run's progress, its log and the Stop button
RUN_TAB = 'Search & results'


def _plural(count, one, many):
    return f"{count:,} {one if count == 1 else many}"


def _short_phase(status):
    """The phase of a running status with its count and percentage, without the details of status_text."""
    phase = status.get('phase')
    if phase == 'starting' and analysis_only(status):
        text = 'Starting the analysis'
    else:
        text = PHASE_LABELS.get(phase, str(phase))
    # the counts as status_fraction reads them (the same _count), so a fraction implies both (review)
    done, total, fraction = _count(status, 'done'), _count(status, 'total'), status_fraction(status)
    if fraction is not None and done is not None and total is not None:
        text += f" {done:,}/{total:,} ({fraction:.0%})"
    return text


def _status_time(status):
    """The time the status was written as "YYYY-MM-DD HH:MM", or None.

    The local time of the engine that wrote it on this computer, shown as written (without
    its UTC offset), as show_status shows it in the search tab (review).
    """
    updated = status.get('updated')
    if not isinstance(updated, str) or len(updated) < 16:
        return None
    return updated[:16].replace('T', ' ')


def state_line(active, status, photos, cleanup=False):
    """Return the one-line state the app shows next to its title on every tab (F27).

    active: whether a run holds the output folder (run_state); status: its status dict or
    None; photos: the supported photos counted in the listed folders, or None without an
    existing folder; cleanup: "Clean up storage" or the cache check holds the run lock, no
    search runs. A running search or analysis shows its phase and progress and where to
    follow it; otherwise the line names how the last run ended, and the photo count.
    """
    if active and cleanup:
        return 'Storage cleanup or cache check running · searches can start again when it is done'
    if active:
        what = 'Analysis' if analysis_only(status) else 'Search'
        parts = [f'{what} running']
        if status and status.get('phase') not in FINAL_PHASES:
            parts.append(_short_phase(status))
        parts.append(f'progress and Stop in the tab "{RUN_TAB}"')
        return ' · '.join(parts)
    if not status:
        last = 'no search yet'
    else:
        name = 'analysis' if analysis_only(status) else 'search'
        phase = status.get('phase')
        last = f"last {name} {phase if phase in FINAL_PHASES else 'ended without finishing'}"
        when = _status_time(status)
        if when:
            last += f' {when}'
    count = ('no existing photo folder' if photos is None
             else _plural(photos, 'photo', 'photos') + ' in the photo folders')
    return f'Idle · {last} · {count}'


def start_needs(profiles, photos, folders_listed, model_label, model_missing):
    """Return what a search needs as (need, met, text) for profiles, photos and the search model (F27).

    profiles: the number of search profiles; photos: the supported photos counted in the
    listed folders that exist, or None if none exists (an existing folder is enough: a
    search reads the folders again, A27); folders_listed: whether any folder is entered;
    model_label: the search model's name; model_missing: why it cannot be used
    (model_problem), or None. A missing need names the tab to fix it in.
    """
    if profiles:
        profile_need = ('profiles', True, _plural(profiles, 'search profile', 'search profiles'))
    else:
        profile_need = ('profiles', False, f'no search profile (tab "{START_NEEDS_TAB["profiles"]}")')
    if photos is not None:
        photo_need = ('photos', True, _plural(photos, 'photo', 'photos'))
    elif folders_listed:
        photo_need = ('photos', False, f'none of the listed photo folders exists (tab "{START_NEEDS_TAB["photos"]}")')
    else:
        photo_need = ('photos', False, f'no photo folder (tab "{START_NEEDS_TAB["photos"]}")')
    if model_missing:
        model_need = ('model', False,
                      f'the search model "{model_label}" cannot be used (tab "{START_NEEDS_TAB["model"]}")')
    else:
        model_need = ('model', True, f'search model "{model_label}"')
    return [profile_need, photo_need, model_need]


def start_needs_line(needs):
    """Return the line listing the needs of start_needs, each marked as met (✓) or missing (✗)."""
    return 'A search needs: ' + ' · '.join(f"{'✓' if met else '✗'} {text}" for _, met, text in needs)


def start_blocked_text(needs, active=False, cleanup=False):
    """Return why Start is not available, or None if it is.

    A running search or analysis (active) or a cleanup holding the run lock (cleanup) comes
    first; otherwise the missing needs of start_needs are listed.
    """
    if active and cleanup:
        return 'Start is not available because the storage is being cleaned up or the cache checked.'
    if active:
        return 'Start is not available because a search or an analysis is running.'
    missing = [text for _, met, text in needs if not met]
    if not missing:
        return None
    return 'Start is not available because: ' + '; '.join(missing) + '.'
