"""Server-side procurement capability checks.

Mirrors the frontend capability rule in frontend/src/types/access.ts
(capForCode): a module code that mentions procurement or purchase resolves to
one of four capabilities, most-specific first — PROCUREMENT_ADMIN (admin /
cycle / refresh), PROCUREMENT_EXPORT, PROCUREMENT_PENDING, PROCUREMENT_GRN —
and falls back to PROCUREMENT_WORKSPACE for any other procurement/purchase
code. PROCUREMENT_ADMIN is deliberately a separate, more elevated grant than
PROCUREMENT_WORKSPACE (lifecycle/cycle/refresh administration vs. ordinary
Purchase Manager workspace actions) — the two must not be conflated, or a
plain PM role would either be rejected from ordinary assignment/export work
(if everything required ADMIN) or an ordinary workspace grant would reach
cycle/refresh administration (if ADMIN were treated as a subset check only).
Platform users and full-access users pass every check without a module
lookup. A missing or unreadable module list fails closed (503, not a silent
allow) for every capability below, consistent with the existing ADMIN check.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException

from dependencies.auth import get_current_user, has_full_access
from repositories.user_repository import UserRepository


def _matches(module_codes, extra_keywords) -> bool:
    for code in module_codes or []:
        text = str(code or "").upper()
        if "PROCUREMENT" not in text and "PURCHASE" not in text:
            continue
        if any(keyword in text for keyword in extra_keywords):
            return True
    return False


def grants_procurement_admin(module_codes) -> bool:
    return _matches(module_codes, ("ADMIN", "CYCLE", "REFRESH"))


def grants_procurement_export(module_codes) -> bool:
    return _matches(module_codes, ("EXPORT",))


def grants_procurement_grn(module_codes) -> bool:
    return _matches(module_codes, ("GRN",))


def grants_procurement_workspace(module_codes) -> bool:
    """Ordinary Purchase Manager workspace actions (assign/reassign/remove
    assignment, skip/defer/restore, final-qty edits). PROCUREMENT_ADMIN is
    accepted too — an admin grant is a superset, matching capForCode's own
    `caps.has('PROCUREMENT_ADMIN') => caps.add('PROCUREMENT_WORKSPACE')` rule
    (frontend/src/types/access.ts) exactly, not loosened or tightened here."""
    if grants_procurement_admin(module_codes):
        return True
    for code in module_codes or []:
        text = str(code or "").upper()
        if "PROCUREMENT" not in text and "PURCHASE" not in text:
            continue
        # Any procurement/purchase code reaches at least PROCUREMENT_WORKSPACE
        # per capForCode's fallback branch — export/pending/grn codes are a
        # strict superset of workspace-eligible, not a separate silo.
        return True
    return False


def load_module_codes(user_id: str) -> list[str]:
    rows = UserRepository().get_user_modules(user_id)
    return [row[0] for row in rows]


def _require(current_user: dict, grant_check) -> dict:
    if has_full_access(current_user):
        return current_user
    try:
        codes = load_module_codes(str(current_user.get("sub") or ""))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Authorization could not be verified.") from exc
    if not grant_check(codes):
        raise HTTPException(status_code=403, detail="This procurement action requires an additional permission.")
    return current_user


def require_procurement_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if has_full_access(current_user):
        return current_user
    try:
        codes = load_module_codes(str(current_user.get("sub") or ""))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Authorization could not be verified.") from exc
    if not grants_procurement_admin(codes):
        raise HTTPException(status_code=403, detail="PROCUREMENT_ADMIN is required.")
    return current_user


def require_procurement_workspace(current_user: dict = Depends(get_current_user)) -> dict:
    """Gate for ordinary Purchase Manager mutation routes (assignment,
    export, GRN submission) — least-privilege: any genuine procurement
    module grant qualifies, matching the existing live UI's own gating
    (PurchaseWorkspacePage renders for any PROCUREMENT_* capability)."""
    return _require(current_user, grants_procurement_workspace)


def require_procurement_export(current_user: dict = Depends(get_current_user)) -> dict:
    return _require(current_user, lambda codes: grants_procurement_export(codes) or grants_procurement_workspace(codes))


def require_procurement_grn(current_user: dict = Depends(get_current_user)) -> dict:
    return _require(current_user, lambda codes: grants_procurement_grn(codes) or grants_procurement_workspace(codes))
