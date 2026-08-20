"""Optional Claude LLM category auto-suggest for Shelf Sorting.

Classifies product names into the fixed shelf-category vocabulary when the
keyword rules and cross-store UnitDescription can't. This is a SUGGESTION
engine — results are written to the learned table as source='llm', confirmed=0,
and only become authoritative once a human confirms them on the review screen.

Deliberately optional and gracefully degrading: it runs only when an
ANTHROPIC_API_KEY is configured (the store backends are LAN-based and may be
offline). With no key, or on any API error, it returns {} and the caller falls
back to keyword + cross-store rules — nothing breaks.

Uses the official Anthropic SDK with claude-opus-4-8 and structured JSON output
(output_config.format) so the response is guaranteed-parseable.
"""

import json
import logging
import os

from modules.procurement import export_document_service as docs

logger = logging.getLogger("procurement.category_ai")

_MODEL = "claude-opus-4-8"
_BATCH = 60  # product names per request


def is_available():
    """True when the LLM suggestion path can run (an API key is configured)."""
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _valid_categories():
    return list(docs._SHELF_ORDER)  # Tablet..Others


def _classify_batch(client, items):
    """items: [(name, unit_description_or_None)]."""
    categories = _valid_categories()
    system = (
        "You are a pharmacy shelf-classification assistant. Classify each product "
        "into exactly one of these shelf categories: "
        + ", ".join(categories)
        + ". Each product is given as its name and, when known, its pack/unit "
        "description (e.g. '10 TAB', '100 ML SYP', 'VET BOLUS') — the unit "
        "description is the strongest signal for drug-form categories (Tablet, "
        "Capsule, Syrup, Injection, Inhaler, Drops, etc.) when it conflicts with "
        "the name. Use 'Veterinary' for animal/vet products, 'Food' for "
        "nutritional supplements/health drinks/granules (e.g. Cerelac, Horlicks, "
        "Boost, Complan, Ensure), 'Paste' for toothpaste, 'Soap'/'Wash' for "
        "cleansers, 'Bandage'/'Cloth' for surgical supplies. If genuinely "
        "unclear, use 'Others'. Return only the JSON object."
    )
    schema = {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "category": {"type": "string", "enum": categories},
                    },
                    "required": ["name", "category"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["items"],
        "additionalProperties": False,
    }
    lines = []
    for name, unit in items:
        unit = (unit or "").strip()
        lines.append(f"- {name} | unit: {unit}" if unit else f"- {name}")
    payload = "\n".join(lines)
    resp = client.messages.create(
        model=_MODEL,
        max_tokens=8000,
        system=system,
        output_config={"format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": f"Classify these products:\n{payload}"}],
    )
    text = next((b.text for b in resp.content if b.type == "text"), "")
    data = json.loads(text)
    valid = set(categories)
    out = {}
    for row in data.get("items", []):
        name = row.get("name")
        cat = row.get("category")
        if name and cat in valid:
            out[name] = cat
    return out


def classify(names, units=None):
    """names -> {name: category}. `units` (optional) is a same-length list of
    UnitDescription strings (or None) aligned by index with `names`, giving
    Claude the pack-type signal alongside the name. Returns {} if unavailable
    or on any failure."""
    units = units or []
    unit_by_name = {}
    for i, n in enumerate(names):
        if n and str(n).strip() and n not in unit_by_name:
            unit_by_name[n] = units[i] if i < len(units) else None
    names = list(unit_by_name.keys())
    if not names or not is_available():
        return {}
    try:
        import anthropic
    except ImportError:
        logger.warning("anthropic SDK not installed — LLM category suggest skipped")
        return {}
    try:
        client = anthropic.Anthropic()
        result = {}
        for i in range(0, len(names), _BATCH):
            batch = [(n, unit_by_name[n]) for n in names[i:i + _BATCH]]
            result.update(_classify_batch(client, batch))
        logger.info("LLM classified %s/%s product names", len(result), len(names))
        return result
    except Exception as exc:
        logger.warning("LLM category suggest failed: %s", exc)
        return {}
