"""Product-name normalization — pure, DB-free, unit-tested.

Two levels, both faithful to the hard-won rules from the NMA/NMC migration:

* ``normalize_product_name`` — the Phase-3 matching key. Uppercase, strip every
  separator/punctuation, KEEP dosage-form words AND (critically) all numeric
  strength.  ``DOLO-650 TAB`` and ``DOLO 650 TAB`` both -> ``DOLO650TAB``.

* ``strip_dosage_terms`` — the structured "core" key. Removes only whole
  dosage-form / unit / noise WORDS supplied by the (configurable) dictionary,
  never digits.  ``DOLO 650 TAB`` with {'TAB'} -> ``DOLO650``.

NEVER remove numeric strength (650, 500, 250, 0.5, 12.5) — those identify
different medicines. Only dosage-form words are ever stripped, and only via the
dictionary so the behaviour is configurable rather than hardcoded.
"""

import re

# Fallback dosage-form / unit words when no DB dictionary is supplied. The live
# engine passes the configurable dbo.product_normalization_dictionary instead.
DEFAULT_DOSAGE_TERMS = frozenset({
    "TAB", "TABS", "TABLET", "TABLETS",
    "CAP", "CAPS", "CAPSULE", "CAPSULES",
    "SYP", "SYRUP", "SUSP", "SUS", "SUSPENSION",
    "INJ", "INJECTION", "DROP", "DROPS",
    "CREAM", "OINT", "OINTMENT", "GEL", "LOTION",
    "SPRAY", "SOAP", "POWDER", "SACHET", "SOLN", "SOLUTION",
    "MG", "MCG", "GM", "ML", "IU",
})

_SEP_RE = re.compile(r"[^A-Z0-9]+")
_TOKEN_RE = re.compile(r"[^A-Z0-9]+")


def normalize_product_name(name):
    """Phase-3 normalized key: uppercase + strip all separators/punctuation.

    Keeps dosage-form words and, crucially, all numeric strength. Two spellings
    of the same product that differ only in punctuation/spacing collapse to the
    same key.
    """
    if not name:
        return ""
    return _SEP_RE.sub("", str(name).upper())


def strip_dosage_terms(name, terms=None):
    """Structured "core" key: drop whole dosage-form / unit words, keep strength.

    ``terms`` is an iterable of uppercase words to remove (from the
    normalization dictionary). Digits are never removed. Separators are then
    stripped so ``DOLO 650 TAB`` -> ``DOLO650``.
    """
    if not name:
        return ""
    strip = frozenset(t.upper() for t in (terms if terms is not None else DEFAULT_DOSAGE_TERMS))
    tokens = [t for t in _TOKEN_RE.split(str(name).upper()) if t]
    kept = [t for t in tokens if t not in strip]
    return "".join(kept)
