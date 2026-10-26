"""File names: the supported image extensions (EXT) and the slugs of profile names."""
import hashlib
import re
import unicodedata


# Supported image file extensions (lowercase, with leading dot).
EXT = frozenset({'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff'})


# Lowercase Latin letters that Unicode decomposition does not reduce to ASCII (all of
# Latin-1 Supplement and Latin Extended-A, plus common stroke letters of Extended-B), and
# the German umlauts, whose conventional transliteration differs from dropping the
# diacritic. Letters missing here are dropped; a name left empty gets the hash fallback.
_TRANSLITERATION = str.maketrans({
    'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'ß': 'ss', 'æ': 'ae', 'œ': 'oe', 'ø': 'o', 'ł': 'l',
    'đ': 'd', 'ð': 'd', 'þ': 'th', 'ı': 'i', 'ħ': 'h', 'ŧ': 't', 'ŋ': 'ng', 'ĸ': 'k',
    'ƀ': 'b', 'ƈ': 'c', 'ƒ': 'f', 'ǥ': 'g', 'ƙ': 'k', 'ƚ': 'l', 'ƥ': 'p', 'ƭ': 't',
    'ƴ': 'y', 'ƶ': 'z', 'ȼ': 'c', 'ɇ': 'e', 'ɉ': 'j', 'ɍ': 'r', 'ɏ': 'y', 'ȷ': 'j'})
# Reserved Windows device names (Microsoft "Naming Files, Paths, and Namespaces"); some
# Windows versions and tools reject them as file names even with an extension. The
# superscript variants (COM¹ ...) become "com1" ... through NFKD and are covered too.
_WINDOWS_DEVICE_NAMES = frozenset({'con', 'prn', 'aux', 'nul',
                                   *(f'com{i}' for i in range(10)),
                                   *(f'lpt{i}' for i in range(10))})
SLUG_MAX_LENGTH = 60


def slugify(s):
    """Return a file-name-safe ASCII slug for a profile name.

    Latin letters with diacritics are transliterated ("Bär" -> "baer", "Café" -> "cafe");
    a name without any usable character (e.g. "猫") gets a stable 10-digit hash instead.
    The result contains only [a-z0-9-], is at most SLUG_MAX_LENGTH characters long and is
    never a Windows device name. It is not unique: use profile_slugs() for a profile list.
    """
    # NFC first, so that decomposed input ("a" + combining diaeresis) still matches "ä"
    # and the hash fallback does not depend on the normal form either
    s = unicodedata.normalize('NFC', s)
    text = unicodedata.normalize('NFKD', s.lower().translate(_TRANSLITERATION))
    # second pass for letters that only appear after decomposition ("ǽ" -> "æ" + acute)
    text = text.translate(_TRANSLITERATION).encode('ascii', 'ignore').decode('ascii')
    slug = re.sub('[^a-z0-9]+', '-', text).strip('-')[:SLUG_MAX_LENGTH].rstrip('-')
    if not slug:
        return hashlib.sha256(s.encode()).hexdigest()[:10]
    if slug in _WINDOWS_DEVICE_NAMES:
        slug += '-profile'
    return slug


def profile_slugs(names):
    """Return one unique slug per profile name, in list order.

    Colliding slugs get "-2", "-3", ... in the order of the list (the base is shortened
    so that the result stays within SLUG_MAX_LENGTH), so the app and the engine derive
    the same result file names (<slug>.html) from the same profile list.
    """
    slugs, used = [], set()
    for name in names:
        base = slugify(name)
        slug, n = base, 2
        while slug in used:
            suffix = f'-{n}'
            slug, n = base[:SLUG_MAX_LENGTH - len(suffix)].rstrip('-') + suffix, n + 1
        used.add(slug)
        slugs.append(slug)
    return slugs
