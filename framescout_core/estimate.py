"""How long a search takes: the remaining-time estimate of a run and the summary before its start (F12)."""
import collections
import math


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
# throughput records kept in the status file (newest first)
THROUGHPUT_KEPT = 8


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


def remaining_text(status):
    """Return e.g. "about 25 min left" for the analysis of a status (A5), or None without a usable rate.

    Only during the phase "analyzing": the engine counts the photos of the cache first, so
    the photos left are the ones to analyze. Scoring and the galleries are not included.
    """
    if status.get('phase') != 'analyzing':
        return None
    rate = _positive(status.get('rate'))
    done, total = status.get('done'), status.get('total')
    if rate is None or not all(isinstance(n, int) and not isinstance(n, bool) for n in (done, total)):
        return None
    left = total - done
    if left <= 0:
        return None
    return f'{duration_text(left / rate)} left'


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


def start_summary(photos, analyzed, per_minute):
    """Return the summary the run tab shows before a search starts.

    photos: the photos counted in the folders; analyzed: those with a cache row of the
    current settings (analyzed_photos); per_minute: known_throughput of these settings, or
    None. The duration covers only the analysis of the new photos.
    """
    if photos <= 0:
        # not "all already analyzed": there is nothing to analyze or rank (review)
        return 'No supported photos found in these folders: the search has nothing to analyze.'
    analyzed = min(analyzed, photos)
    todo = photos - analyzed
    if not todo:
        return (f'{_photos(photos)} found, all already analyzed with these settings: the search only ranks them '
                'and writes the galleries.')
    text = f'{_photos(photos)} found · {analyzed:,} already analyzed with these settings · {todo:,} to analyze.'
    per_minute = _positive(per_minute)
    if per_minute is None:
        return text + ' The search shows how long it takes after its first minutes.'
    return (text + f' At the speed of an earlier search with these settings, the analysis takes '
            f'{duration_text(todo / per_minute)} (a rough estimate: it depends on the photos and on what else the '
            'PC does).')
