"""Normalization-dictionary service — configurable strip vocabulary.

Keeps dosage-form / unit / noise terms out of hardcoded Python so operators can
tune matching without a code change. Thin wrapper over the repository.
"""

from modules.product_mapping import repository

VALID_KINDS = {"DOSAGE_FORM", "UNIT", "NOISE"}


def list_terms(tenant_id=None):
    return repository.list_dictionary(tenant_id)


def add_term(tenant_id, term, canonical=None, kind="DOSAGE_FORM", actor=None):
    if not term or not term.strip():
        raise ValueError("term is required")
    if kind not in VALID_KINDS:
        raise ValueError(f"kind must be one of {sorted(VALID_KINDS)}")
    return repository.add_term(tenant_id, term.strip(), canonical, kind, actor)


def update_term(entry_id, **fields):
    if "kind" in fields and fields["kind"] not in VALID_KINDS:
        raise ValueError(f"kind must be one of {sorted(VALID_KINDS)}")
    repository.update_term(entry_id, **fields)


def delete_term(entry_id):
    repository.delete_term(entry_id)
