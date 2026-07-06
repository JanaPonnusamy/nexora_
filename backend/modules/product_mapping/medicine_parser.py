"""Structured medicine parser — pure, DB-free, unit-tested.

``extract_medicine_attributes`` pulls Brand / Strength / Unit / Dosage Form /
Pack Size out of a raw product name so they become structured, searchable and
scorable signals.

    DOLO 650MG TAB 15'S
        -> brand=DOLO strength=650 unit=MG form=TAB pack=15

Design rules (from the NMA/NMC migration):
* Dosage form and pack are extracted BEFORE anything is stripped, so numeric
  strength always survives.
* The brand is everything alphabetic that appears BEFORE the first strength
  number (e.g. ``GENPRAZ DSR`` keeps the ``DSR`` qualifier — it is part of the
  identity, not a dosage form).
* Dosage-form vocabulary is configurable (defaults mirror the seeded
  dictionary) and canonicalized (TABLET/TABS/TAB -> TAB).
"""

import re

FORM_CANON = {
    "TABLET": "TAB", "TABLETS": "TAB", "TABS": "TAB", "TAB": "TAB",
    "CAPSULE": "CAP", "CAPSULES": "CAP", "CAPS": "CAP", "CAP": "CAP",
    "SYRUP": "SYP", "SYP": "SYP",
    "SUSPENSION": "SUSP", "SUSP": "SUSP", "SUS": "SUSP",
    "INJECTION": "INJ", "INJ": "INJ",
    "DROPS": "DROP", "DROP": "DROP",
    "OINTMENT": "OINT", "OINT": "OINT",
    "SOLUTION": "SOLN", "SOLN": "SOLN",
    "CREAM": "CREAM", "GEL": "GEL", "LOTION": "LOTION", "SPRAY": "SPRAY",
    "SOAP": "SOAP", "POWDER": "POWDER", "SACHET": "SACHET",
}

DEFAULT_FORMS = frozenset(FORM_CANON)
UNITS = frozenset({"MG", "MCG", "GM", "ML", "IU", "%"})

# tokens: alphabetic runs OR decimal/integer numbers (keeps 0.5, 12.5 intact)
_TOKEN_RE = re.compile(r"[A-Z]+|\d+(?:\.\d+)?")
# pack size:  15'S / 15`S   or trailing  X15 / *15
_PACK_APOS_RE = re.compile(r"(\d+)\s*['`]\s*S\b")
_PACK_TAIL_RE = re.compile(r"[X*]\s*(\d+)\s*$")


def extract_medicine_attributes(name, forms=None, form_canon=None):
    """Return ``{brand, strength, unit, dosage_form, pack_size}`` for ``name``.

    Every value is a string or None. ``forms`` overrides the recognised
    dosage-form vocabulary (uppercase words); ``form_canon`` overrides the
    canonical mapping.
    """
    result = {"brand": None, "strength": None, "unit": None,
              "dosage_form": None, "pack_size": None}
    if not name:
        return result

    text = str(name).upper()
    known_forms = frozenset(f.upper() for f in forms) if forms is not None else DEFAULT_FORMS
    canon = form_canon if form_canon is not None else FORM_CANON

    # --- pack size (extracted first, from the raw text) ---
    m = _PACK_APOS_RE.search(text) or _PACK_TAIL_RE.search(text)
    if m:
        result["pack_size"] = m.group(1)

    # --- walk tokens: brand before first strength, then strength/unit/form ---
    tokens = _TOKEN_RE.findall(text)
    brand_tokens = []
    strength_set = False
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if re.fullmatch(r"\d+(?:\.\d+)?", tok):
            if not strength_set:
                result["strength"] = tok
                if i + 1 < len(tokens) and tokens[i + 1] in UNITS:
                    result["unit"] = tokens[i + 1]
                    i += 1
                strength_set = True
        elif tok in known_forms:
            if result["dosage_form"] is None:
                result["dosage_form"] = canon.get(tok, tok)
        elif tok in UNITS:
            pass  # a stray unit without a number — ignore
        elif not strength_set:
            brand_tokens.append(tok)  # alpha qualifier before strength => brand
        i += 1

    if brand_tokens:
        result["brand"] = " ".join(brand_tokens)
    return result
