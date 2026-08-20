from __future__ import annotations

"""Before-and-after mutation diffing utility for audit logging."""

import json
from typing import Any, Dict, List, Optional, Tuple

from .redaction import _is_secret_key, redact_and_bound_metadata


def compute_mutation_diff(
    before: Optional[Dict[str, Any]],
    after_input: Optional[Dict[str, Any]],
) -> Tuple[List[str], Dict[str, Any]]:
    """Compute field changes between before snapshot and mutation inputs.
    
    RULES:
    1. Only compares keys present in after_input (partial update support).
    2. Compares by serialized value so nested objects/lists work.
    3. If key is a secret, flags as changed WITHOUT reading or exposing either value.
    4. Returns tuple of (changed_field_names, diff_details_dict).
    """
    if not after_input:
        return [], {}

    if before is None:
        # Full creation
        changed_keys = list(after_input.keys())
        sanitized_input = {}
        for k, v in after_input.items():
            if _is_secret_key(str(k)):
                sanitized_input[k] = "[redacted]"
            else:
                sanitized_input[k] = v
        return changed_keys, {"created": sanitized_input}

    changed_fields: List[str] = []
    diff_details: Dict[str, Any] = {}

    for key, new_val in after_input.items():
        key_str = str(key)
        old_val = before.get(key)

        # Handle secrets without exposing values
        if _is_secret_key(key_str):
            if new_val is not None:
                changed_fields.append(key_str)
                diff_details[key_str] = {
                    "old": "[redacted]",
                    "new": "[redacted]",
                    "status": "changed",
                }
            continue

        # Compare serialized values
        try:
            old_json = json.dumps(old_val, sort_keys=True, default=str)
            new_json = json.dumps(new_val, sort_keys=True, default=str)
        except Exception:
            old_json = str(old_val)
            new_json = str(new_val)

        if old_json != new_json:
            changed_fields.append(key_str)
            diff_details[key_str] = {
                "old": old_val,
                "new": new_val,
            }

    return changed_fields, diff_details
