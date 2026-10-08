"""Audit for NMV integration events.

Two layers:
  * the platform audit trail (modules.audit.record_audit) for a durable,
    cross-module record of each boundary call;
  * the per-message nmv_sync_audit correlation row (written transactionally in
    repository, inside the data write).

Only counts, entity names and correlation ids are recorded. Tokens, keys and
row contents are never audited.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("nexora.nmv_integration")

try:  # the audit module is always present in HO; guard keeps unit imports cheap
    from modules.audit.writer import record_audit
    from modules.audit.models import AuditStatus
except Exception:  # pragma: no cover
    record_audit = None
    AuditStatus = None


def record(action, store_code, device_id=None, *, target_id=None, metadata=None,
           ok=True, error=None):
    """Fire-and-forget platform audit entry. Never raises."""
    if record_audit is None:
        return
    try:
        status = None
        if AuditStatus is not None:
            status = AuditStatus.SUCCESS if ok else AuditStatus.FAILURE
        safe_meta = _safe(metadata)
        safe_meta.setdefault("store_code", store_code)
        if device_id:
            # device id is an opaque correlation id, not a secret
            safe_meta.setdefault("device_id", device_id)
        kwargs = dict(
            action=action,
            target_type="nmv_store",
            target_id=target_id or store_code,
            target_label=f"NMV:{store_code}",
            metadata=safe_meta,
            category="integration",
            error_message=error,
        )
        if status is not None:
            kwargs["status"] = status
        record_audit(None, **kwargs)
    except Exception:
        logger.warning("NMV audit record failed for %s", action, exc_info=True)


def _safe(metadata):
    """Drop anything that looks like a secret before it reaches the audit log."""
    if not isinstance(metadata, dict):
        return {}
    banned = ("token", "secret", "password", "pwd", "signature", "key", "authorization")
    return {
        k: v for k, v in metadata.items()
        if not any(b in str(k).lower() for b in banned)
    }
