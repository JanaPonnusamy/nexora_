from __future__ import annotations

"""Metadata redaction and payload bounding engine.

REDACTION STRATEGY:
This scrubber is a backstop denylist — only as good as its last review.
When instrumenting an area, hand-pick the metadata payload rather than spreading
raw request bodies or large objects. The pattern and bounding guards below prevent
accidental leaks of passwords, tokens, and oversized payloads into the immutable audit trail.
"""

import json
import re
from typing import Any

# Case-insensitive secret key pattern matching (singular, plural, separated)
_SECRET_KEY_PATTERN = re.compile(
    r"^(pass(word|wd)?s?|secrets?|tokens?|otps?|api_?keys?|private_?keys?|credentials?|creds|auth_?codes?|epp|cvv|signatures?|mfa)$",
    re.IGNORECASE,
)

MAX_DEPTH = 4
MAX_STRING_LENGTH = 300
MAX_ARRAY_WIDTH = 25


def _is_secret_key(key: str) -> bool:
    """Check if key name matches sensitive credentials pattern anywhere in tree."""
    # Matches key exactly or when combined with separators (e.g. user_password, api_token)
    if _SECRET_KEY_PATTERN.match(key):
        return True
    # Also check normalized alphanumeric sub-tokens
    parts = re.split(r"[_\-\.]", key)
    return any(_SECRET_KEY_PATTERN.match(p) for p in parts)


def _sanitize_value(val: Any, depth: int) -> Any:
    """Recursively sanitize, redact, and bound an arbitrary data structure."""
    if depth > MAX_DEPTH:
        return "[Max depth reached]"

    if val is None:
        return None

    if isinstance(val, (int, float, bool)):
        return val

    if isinstance(val, str):
        if len(val) > MAX_STRING_LENGTH:
            return val[:MAX_STRING_LENGTH] + "... [truncated]"
        return val

    if isinstance(val, (list, tuple, set)):
        items = list(val)
        sanitized = [_sanitize_value(item, depth + 1) for item in items[:MAX_ARRAY_WIDTH]]
        if len(items) > MAX_ARRAY_WIDTH:
            sanitized.append(f"... [{len(items) - MAX_ARRAY_WIDTH} more items truncated]")
        return sanitized

    if isinstance(val, dict):
        sanitized_dict: dict[str, Any] = {}
        for k, v in val.items():
            key_str = str(k)
            if _is_secret_key(key_str):
                sanitized_dict[key_str] = "[redacted]"
            else:
                sanitized_dict[key_str] = _sanitize_value(v, depth + 1)
        return sanitized_dict

    # Handle Pydantic models or objects with dict conversion
    if hasattr(val, "model_dump"):
        return _sanitize_value(val.model_dump(), depth)
    if hasattr(val, "dict"):
        return _sanitize_value(val.dict(), depth)
    if hasattr(val, "__dict__"):
        return _sanitize_value(vars(val), depth)

    # Fallback to string representation
    s = str(val)
    if len(s) > MAX_STRING_LENGTH:
        return s[:MAX_STRING_LENGTH] + "... [truncated]"
    return s


def redact_and_bound_metadata(metadata: Any) -> Optional[str]:
    """Sanitize metadata and serialize to a clean JSON string."""
    if metadata is None:
        return None
    try:
        sanitized = _sanitize_value(metadata, depth=1)
        return json.dumps(sanitized, default=str, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"_error": f"Failed to serialize metadata: {str(e)}"})
