"""How long a search takes: the remaining-time estimate of a run and the summary before its start (F12, F16)."""
import collections
import math
import time
from datetime import datetime


# A first search on a CPU can take hours. The engine measures how many new photos it
# analyzes per minute and writes it into the status file: "rate", a moving average the app
# turns into "about 25 min left", and "throughput", the speed of the whole analysis per
# cache signature and device, which a new run keeps, so the run tab can estimate the next
# search before its start. Estimates are rough (a busy PC, other photo sizes): they are
# rounded generously and never name seconds.
# seconds the moving average covers at least
RATE_WINDOW = 300
# a rate needs at least this many new photos over at least this many seconds
RATE_MIN_PHOTOS = 16
RATE_MIN_SECONDS = 60
# the app names no time left once the status has not changed for this many seconds
RATE_STALE = RATE_WINDOW
# throughput records kept in the status file (newest first)
THROUGHPUT_KEPT = 8
# a run replaces the stored speed of its settings and device only after measuring this
# many seconds: a search stopped after a minute is a poor sample of a whole analysis
THROUGHPUT_MIN_SECONDS = RATE_WINDOW
# What follows the analysis (F16): scoring every photo and rendering the gallery thumbnails.
# Their speeds do not depend on the settings or the device much, so the status file keeps
# one "finishing" record, {'scoring': photos scored per minute, 'thumbnails': thumbnails
# rendered per minute}, from the last search that measured each. A thumbnail copied or
# reused from an earlier search is not counted, so the estimate is on the safe side.
FINISHING_STEPS = ('scoring', 'thumbnails')
# a step's speed is stored only if it measured at least this many items, and it replaces
# a stored speed of the step only after this many seconds: a small search (e.g. a few
# thumbnails from a cold disk) is a poor sample of a large one (review). Both steps are far
# faster than the analysis, so a large search measures this long, unlike THROUGHPUT_MIN_SECONDS
FINISHING_MIN_ITEMS = RATE_MIN_PHOTOS
FINISHING_MIN_SECONDS = 10


def _rate(first, last):
    """Photos per minute between the samples first and last ((seconds, photos)), or None if too few."""
    seconds, photos = last[0] - first[0], last[1] - first[1]
    if photos < RATE_MIN_PHOTOS or seconds < RATE_MIN_SECONDS:
        return None
    return photos * 60 / seconds


class AnalysisRate:
    """The speed of the analysis of new photos, from samples (seconds, photos analyzed so far).

    The engine adds a sample after each stored group of photos; the first sample starts the
    measurement, so loading the models and the person detector is not counted. per_minute()
    is the moving average over the last RATE_WINDOW seconds (or the whole run, if that window
    holds too few photos), overall() the average since the first sample; both None until
    RATE_MIN_PHOTOS photos over RATE_MIN_SECONDS seconds were measured.
    """

    def __init__(self):
        self.first = None
        self.samples = collections.deque()

    def add(self, photos, now):
        """Record that photos new photos were analyzed by now (seconds of a monotonic clock)."""
        sample = (now, photos)
        if self.first is None:
            self.first = sample
        self.samples.append(sample)
        # the oldest sample is dropped only while the next one still spans the window
        while len(self.samples) > 2 and now - self.samples[1][0] >= RATE_WINDOW:
            self.samples.popleft()

    def per_minute(self):
        if not self.samples:
            return None
        recent = _rate(self.samples[0], self.samples[-1])
        return recent if recent is not None else self.overall()

    def overall(self):
        return None if self.first is None else _rate(self.first, self.samples[-1])

    def seconds(self):
        """Seconds measured since the first sample."""
        return 0.0 if self.first is None else self.samples[-1][0] - self.first[0]


def _positive(value):
    """value if it is a positive finite number (not a bool), else None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        return None
    return value


def duration_text(minutes):
    """Return a duration of minutes as the app shows it: rounded generously, never seconds."""
    if minutes < 2:
        return 'under 2 min'
    if minutes < 10:
        step = 1
    elif minutes < 60:
        step = 5
    elif minutes < 300:
        step = 30
    else:
        step = 60
    rounded = int(minutes / step + 0.5) * step
    hours, rest = divmod(rounded, 60)
    if not hours:
        return f'about {rest} min'
    return f'about {hours} h {rest} min' if rest else f'about {hours} h'


def _stalled(status, now):
    """True if status was last written more than RATE_STALE seconds before now (or has no usable time)."""
    try:
        return (now - datetime.fromisoformat(status['updated'])).total_seconds() > RATE_STALE
    except (KeyError, TypeError, ValueError):  # TypeError: also a time without its time zone
        return True


def _count(status, key):
    value = status.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def remaining_text(status, now=None):
    """Return e.g. "about 25 min left" for a running search (A5, F16), or None without a usable speed.

    During the phase "analyzing" (the engine counts the photos of the cache first, so the
    photos left are the ones to analyze) the time comes from the run's rate; scoring all
    photos and rendering the planned gallery thumbnails ("thumbnails" of the status) are
    added at the speeds of earlier searches ("finishing", F16). Without these the text names
    the analysis alone ("... left for the analysis"); once every photo is analyzed, only
    the earlier speeds count (review). During "scoring" and "exporting" only
    the earlier speeds count, for the photos and cards left (each card may need a new
    thumbnail). now: the current time (an aware datetime; default now). A status not
    written for RATE_STALE seconds names no time (review: else a stalled analysis kept
    "about 25 min left").
    """
    phase = status.get('phase')
    if phase not in ('analyzing', 'scoring', 'exporting'):
        return None
    done, total = _count(status, 'done'), _count(status, 'total')
    if done is None or total is None or total <= 0:
        return None
    if _stalled(status, now or datetime.now().astimezone()):
        return None
    left = max(0, total - done)
    thumbnails = _count(status, 'thumbnails')
    finishing = status.get('finishing')
    if phase == 'analyzing':
        rest = None if thumbnails is None else finishing_minutes(finishing, total, thumbnails)
        if not left:
            # every photo is analyzed (or came from the cache, without a rate), but scoring
            # and the thumbnails still take their time (review)
            analysis = 0.0
        else:
            rate = _positive(status.get('rate'))
            if rate is None:
                return None
            analysis = left / rate
            if rest is None:
                return f'{duration_text(analysis)} left for the analysis'
        return None if rest is None else f'{duration_text(analysis + rest)} left'
    if phase == 'scoring':
        rest = None if thumbnails is None else finishing_minutes(finishing, left, thumbnails)
    else:
        rest = finishing_minutes(finishing, 0, left)
    return None if not rest else f'{duration_text(rest)} left'


def stored_finishing(value):
    """Return the valid speeds of a status file's "finishing" value ({step: per minute}), else {}."""
    if not isinstance(value, dict):
        return {}
    return {step: value[step] for step in FINISHING_STEPS if _positive(value.get(step)) is not None}


def remember_finishing(finishing, step, items, seconds):
    """Return finishing with the speed of step (FINISHING_STEPS) measured over items in seconds, or None.

    None (keep finishing as it is) if fewer than FINISHING_MIN_ITEMS items were measured,
    or if a speed of step is stored and the measurement took less than FINISHING_MIN_SECONDS
    (review: the first speed of a step is stored at once).
    """
    if items < FINISHING_MIN_ITEMS or not seconds > 0:
        return None
    stored = stored_finishing(finishing)
    if step in stored and seconds < FINISHING_MIN_SECONDS:
        return None
    return {**stored, step: items * 60 / seconds}


class StepSpeed:
    """The items of a step after the analysis and the seconds they took (F16).

    timed(func) returns func counting each call that returns (one that raises is not
    counted), e.g. the engine's rendering of a gallery thumbnail; remember(finishing, step)
    is remember_finishing of what was counted.
    """

    def __init__(self, clock=time.monotonic):
        self.items, self.seconds, self.clock = 0, 0.0, clock

    def timed(self, func):
        def run(*args, **kwargs):
            start = self.clock()
            result = func(*args, **kwargs)
            self.items += 1
            self.seconds += self.clock() - start
            return result
        return run

    def remember(self, finishing, step):
        return remember_finishing(finishing, step, self.items, self.seconds)


def finishing_minutes(finishing, photos, thumbnails):
    """Return the minutes scoring photos and rendering thumbnails take at the speeds of finishing, or None.

    None if a step with something to do has no stored speed.
    """
    speeds = stored_finishing(finishing)
    minutes = 0.0
    for step, items in (('scoring', photos), ('thumbnails', thumbnails)):
        if items > 0:
            if step not in speeds:
                return None
            minutes += items / speeds[step]
    return minutes


def gallery_thumbnails(photos, top, profiles):
    """Return how many gallery thumbnails a search of photos with profiles galleries of top cards renders at most.

    A photo in several galleries has one thumbnail; every one counts as new (on the safe side).
    """
    return min(photos, top * profiles)


def _record(value):
    return (isinstance(value, dict) and isinstance(value.get('signature'), str)
            and isinstance(value.get('device'), str) and _positive(value.get('per_minute')) is not None)


def stored_throughput(value):
    """Return the valid throughput records of a status file's value (at most THROUGHPUT_KEPT), else []."""
    if not isinstance(value, list):
        return []
    return [record for record in value if _record(record)][:THROUGHPUT_KEPT]


def remember_throughput(records, signature, device, per_minute):
    """Return records with the speed per_minute of signature and device first, replacing an older one of them."""
    kept = [r for r in stored_throughput(records) if (r['signature'], r['device']) != (signature, device)]
    return [{'signature': signature, 'device': device, 'per_minute': per_minute}, *kept][:THROUGHPUT_KEPT]


def run_throughput(records, signature, device, speed):
    """Return records with the speed of this run (speed: its AnalysisRate), or None to keep them as they are.

    The first speed measured for signature and device is stored at once; an earlier record
    of them is replaced only once the run measured THROUGHPUT_MIN_SECONDS, so a search
    stopped after its first minute keeps the speed of an earlier, longer analysis (review).
    """
    per_minute = speed.overall()
    if per_minute is None:
        return None
    known = any((r['signature'], r['device']) == (signature, device) for r in stored_throughput(records))
    if known and speed.seconds() < THROUGHPUT_MIN_SECONDS:
        return None
    return remember_throughput(records, signature, device, per_minute)


def known_throughput(status, signature, device):
    """Return the photos per minute an earlier search measured for signature and device, or None.

    device None (e.g. "auto" when the app cannot tell which device it picks) takes the
    newest record of signature on any device.
    """
    if not isinstance(status, dict):
        return None
    for record in stored_throughput(status.get('throughput')):
        if record['signature'] == signature and device in (None, record['device']):
            return record['per_minute']
    return None


def _photos(count):
    return f'{count:,} photo' + ('' if count == 1 else 's')


def start_summary(photos, analyzed, per_minute, finishing=None):
    """Return the summary the run tab shows before a search starts.

    photos: the photos counted in the folders; analyzed: those with a current cache row of
    the current settings (analyzed_photos); per_minute: known_throughput of these settings,
    or None; finishing: finishing_minutes of scoring all photos and rendering the gallery
    thumbnails (F16), or None if unknown. It is named as an upper bound ("up to"): thumbnails
    of earlier searches are reused. Without the speed of the analysis no duration is named.
    """
    if photos <= 0:
        # not "all already analyzed": there is nothing to analyze or rank (review)
        return 'No supported photos found in these folders: the search has nothing to analyze.'
    analyzed = min(analyzed, photos)
    todo = photos - analyzed
    finishing = None if finishing is None or finishing < 0 else finishing
    if not todo:
        text = (f'{_photos(photos)} found, all already analyzed with these settings: the search only ranks them '
                'and writes the galleries')
        if finishing is None:
            return text + '.'
        return text + f', which takes up to {duration_text(finishing)} at the speed of earlier searches.'
    text = f'{_photos(photos)} found · {analyzed:,} already analyzed with these settings · {todo:,} to analyze.'
    per_minute = _positive(per_minute)
    if per_minute is None:
        return text + ' The search shows how long it takes after its first minutes.'
    text += (f' At the speed of an earlier search with these settings, the analysis takes '
             f'{duration_text(todo / per_minute)}')
    if finishing is not None:
        text += f', scoring and writing the galleries up to {duration_text(finishing)} more'
    return text + ' (a rough estimate: it depends on the photos and on what else the PC does).'
