"""Data access for the Product Mapping tables (dbo.product_mapping*, dictionary).

Raw pyodbc, parameterized, tenant-scoped. Persists engine decisions, serves the
review/approval workflow, and reads the configurable normalization dictionary.
Client-generated GUIDs let mappings and their candidates be bulk-inserted with
``fast_executemany`` in a single round trip each.
"""

import uuid

from config.database import get_connection
from modules.procurement._dbutil import as_uid, rows_to_dicts as _rows_to_dicts, stringify
from modules.product_mapping import scoring

# Statuses a re-run must never overwrite. PENDING is the only regenerable state;
# APPROVED/AUTO are prior successes and REJECTED is a human "no" — all three are
# kept (and, being non-deleted, also protect the unique source→target index).
_PRESERVED = ("APPROVED", "AUTO", "REJECTED")

_MAP_COLS = (
    "mapping_id", "tenant_id", "run_id", "source_store_id", "source_product_code",
    "source_product_name", "source_normalized_name", "target_store_id",
    "target_product_code", "target_product_name", "match_method", "match_phase",
    "confidence", "status", "brand", "strength", "unit", "dosage_form",
    "pack_size", "mrp", "created_by",
)
_CAND_COLS = (
    "candidate_id", "mapping_id", "tenant_id", "target_product_code",
    "target_product_name", "target_normalized_name", "name_score", "brand_score",
    "strength_score", "form_score", "mrp_score", "total_score", "brand",
    "strength", "dosage_form", "mrp", "reason",
)
_AUDIT_COLS = (
    "audit_id", "tenant_id", "mapping_id", "run_id", "action",
    "old_status", "new_status", "actor_user_id", "detail",
)


# --------------------------------------------------------------------------
# Dictionary (configurable normalization vocabulary)
# --------------------------------------------------------------------------

def load_active_terms(tenant_id):
    """Set of uppercase strip-terms in effect for a tenant (global + tenant)."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT term FROM dbo.product_normalization_dictionary
            WHERE is_active = 1 AND (tenant_id IS NULL OR tenant_id = ?)
            """,
            (as_uid(tenant_id),),
        )
        return {r[0].upper() for r in cur.fetchall() if r[0]}
    finally:
        conn.close()


def list_dictionary(tenant_id=None):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT entry_id, tenant_id, term, canonical, kind, is_active, created_at
            FROM dbo.product_normalization_dictionary
            WHERE tenant_id IS NULL OR tenant_id = ?
            ORDER BY kind, term
            """,
            (as_uid(tenant_id),),
        )
        return [stringify(r) for r in _rows_to_dicts(cur)]
    finally:
        conn.close()


def add_term(tenant_id, term, canonical, kind, actor=None):
    conn = get_connection()
    try:
        cur = conn.cursor()
        entry_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO dbo.product_normalization_dictionary
                (entry_id, tenant_id, term, canonical, kind, is_active, created_by)
            VALUES (?, ?, ?, ?, ?, 1, ?)
            """,
            (entry_id, as_uid(tenant_id), term.upper(), (canonical or term).upper(),
             kind or "DOSAGE_FORM", as_uid(actor)),
        )
        conn.commit()
        return entry_id
    finally:
        conn.close()


def update_term(entry_id, term=None, canonical=None, kind=None, is_active=None, actor=None):
    sets, params = [], []
    if term is not None:
        sets.append("term = ?"); params.append(term.upper())
    if canonical is not None:
        sets.append("canonical = ?"); params.append(canonical.upper())
    if kind is not None:
        sets.append("kind = ?"); params.append(kind)
    if is_active is not None:
        sets.append("is_active = ?"); params.append(1 if is_active else 0)
    if not sets:
        return
    sets.append("updated_at = GETDATE()")
    sets.append("updated_by = ?"); params.append(as_uid(actor))
    params.append(entry_id)
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE dbo.product_normalization_dictionary SET {', '.join(sets)} WHERE entry_id = ?",
            tuple(params),
        )
        conn.commit()
    finally:
        conn.close()


def delete_term(entry_id):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM dbo.product_normalization_dictionary WHERE entry_id = ?", (entry_id,))
        conn.commit()
    finally:
        conn.close()


# --------------------------------------------------------------------------
# Persisting a run's decisions
# --------------------------------------------------------------------------

def live_statuses_for_pair(cur, tenant_id, source_store_id, target_store_id):
    """{source_product_code: status} for non-deleted mappings of a store pair."""
    cur.execute(
        """
        SELECT source_product_code, status FROM dbo.product_mapping
        WHERE tenant_id = ? AND source_store_id = ? AND target_store_id = ? AND is_deleted = 0
        """,
        (tenant_id, source_store_id, target_store_id),
    )
    return {r[0]: r[1] for r in cur.fetchall()}


def save_run(tenant_id, run_id, source_store_id, target_store_id, decisions, actor=None):
    """Persist a run's decisions. Preserves APPROVED/AUTO mappings (never
    overwrites a prior success); refreshes stale PENDING ones. Returns a summary
    dict (auto / pending / preserved / total)."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.fast_executemany = True
        actor_uid = as_uid(actor)

        existing = live_statuses_for_pair(cur, tenant_id, source_store_id, target_store_id)

        # Retire stale PENDING mappings (+ their candidates) for this pair with
        # set-based statements — a run can produce tens of thousands of rows, far
        # past SQL Server's 2100-parameter IN(...) limit, so never enumerate ids.
        pair = (tenant_id, source_store_id, target_store_id)
        cur.execute(
            """
            DELETE c FROM dbo.product_mapping_candidate c
            JOIN dbo.product_mapping m ON m.mapping_id = c.mapping_id
            WHERE m.tenant_id = ? AND m.source_store_id = ? AND m.target_store_id = ?
              AND m.is_deleted = 0 AND m.status = 'PENDING'
            """,
            pair,
        )
        cur.execute(
            """
            UPDATE dbo.product_mapping SET is_deleted = 1, deleted_at = GETDATE()
            WHERE tenant_id = ? AND source_store_id = ? AND target_store_id = ?
              AND is_deleted = 0 AND status = 'PENDING'
            """,
            pair,
        )

        map_rows, cand_rows, audit_rows = [], [], []
        summary = {"auto": 0, "pending": 0, "preserved": 0, "total": len(decisions)}

        for d in decisions:
            if existing.get(d["source_product_code"]) in _PRESERVED:
                summary["preserved"] += 1
                continue
            mid = str(uuid.uuid4())
            status = d["status"]
            summary["auto" if status == "AUTO" else "pending"] += 1
            map_rows.append((
                mid, tenant_id, run_id, source_store_id, d["source_product_code"],
                d["source_product_name"], d["source_normalized_name"], target_store_id,
                d["target_product_code"], d["target_product_name"], d["match_method"],
                d["match_phase"], d["confidence"], status, d["brand"], d["strength"],
                d["unit"], d["dosage_form"], d["pack_size"], d["mrp"], actor_uid,
            ))
            for c in d.get("candidates", []):
                cand_rows.append((
                    str(uuid.uuid4()), mid, tenant_id, c["target_product_code"],
                    c["target_product_name"], c.get("target_normalized_name"),
                    c["name_score"], c["brand_score"], c["strength_score"],
                    c["form_score"], c["mrp_score"], c["total_score"], c.get("brand"),
                    c.get("strength"), c.get("dosage_form"), c.get("mrp"), c.get("reason"),
                ))
            audit_rows.append((
                str(uuid.uuid4()), tenant_id, mid, run_id,
                "AUTO_MATCH" if status == "AUTO" else "RUN",
                None, status, actor_uid,
                f"{d['match_method'] or 'no-match'} @ {d['confidence']}",
            ))

        if map_rows:
            cur.executemany(
                f"INSERT INTO dbo.product_mapping ({','.join(_MAP_COLS)}) "
                f"VALUES ({','.join('?' * len(_MAP_COLS))})",
                map_rows,
            )
        if cand_rows:
            cur.executemany(
                f"INSERT INTO dbo.product_mapping_candidate ({','.join(_CAND_COLS)}) "
                f"VALUES ({','.join('?' * len(_CAND_COLS))})",
                cand_rows,
            )
        if audit_rows:
            cur.executemany(
                f"INSERT INTO dbo.product_mapping_audit ({','.join(_AUDIT_COLS)}) "
                f"VALUES ({','.join('?' * len(_AUDIT_COLS))})",
                audit_rows,
            )
        conn.commit()
        return summary
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# --------------------------------------------------------------------------
# Reads for the workspace
# --------------------------------------------------------------------------

def list_mappings(tenant_id, status=None, source_store_id=None, target_store_id=None,
                  run_id=None, search=None, page=1, page_size=50):
    where = ["tenant_id = ?", "is_deleted = 0"]
    params = [tenant_id]
    if status:
        # CAST pins the comparison type to the column's VARCHAR(20); without it
        # pyodbc sends the Python str as NVARCHAR and SQL Server's implicit
        # CONVERT on the (indexed) status column blocks index seeks entirely.
        where.append("status = CAST(? AS VARCHAR(20))"); params.append(status)
    if source_store_id:
        where.append("source_store_id = ?"); params.append(source_store_id)
    if target_store_id:
        where.append("target_store_id = ?"); params.append(target_store_id)
    if run_id:
        where.append("run_id = ?"); params.append(run_id)
    if search:
        where.append("(source_product_name LIKE '%' + ? + '%' OR source_product_code LIKE ? + '%')")
        params.extend([search, search])
    clause = " AND ".join(where)
    offset = max(0, (int(page) - 1) * int(page_size))
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM dbo.product_mapping WHERE {clause}", tuple(params))
        total = cur.fetchone()[0]
        cur.execute(
            f"""
            SELECT * FROM dbo.product_mapping WHERE {clause}
            ORDER BY confidence DESC, source_product_name
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
            """,
            tuple(params) + (offset, int(page_size)),
        )
        items = [stringify(r) for r in _rows_to_dicts(cur)]
        return {"total": total, "page": page, "page_size": page_size, "items": items}
    finally:
        conn.close()


def list_review_batch(tenant_id, source_store_id, target_store_id, search=None,
                       after_confidence=None, after_mapping_id=None, limit=100):
    """Keyset (seek) page of PENDING mappings for Manual Review continuous
    batches. Ordered by (confidence DESC, mapping_id) — the same order as
    IX_product_mapping_review_queue, so this is an index seek + TOP with no
    Sort operator, and cost stays flat (~15ms) no matter how deep into the
    queue the reviewer is, unlike OFFSET which re-scans/discards every prior
    row. ``after_confidence``/``after_mapping_id`` are the last row's keys from
    the previous batch; omit both for the first batch.
    """
    where = [
        "tenant_id = ?", "is_deleted = 0", "status = CAST(? AS VARCHAR(20))",
        "source_store_id = ?", "target_store_id = ?",
    ]
    params = [tenant_id, "PENDING", source_store_id, target_store_id]
    if search:
        where.append("(source_product_name LIKE '%' + ? + '%' OR source_product_code LIKE ? + '%')")
        params.extend([search, search])
    if after_confidence is not None and after_mapping_id is not None:
        where.append(
            "(confidence < CAST(? AS DECIMAL(5,2)) "
            "OR (confidence = CAST(? AS DECIMAL(5,2)) AND mapping_id > ?))"
        )
        params.extend([after_confidence, after_confidence, after_mapping_id])
    clause = " AND ".join(where)
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT TOP (?) * FROM dbo.product_mapping WHERE {clause}
            ORDER BY confidence DESC, mapping_id
            """,
            tuple([int(limit)] + params),
        )
        items = [stringify(r) for r in _rows_to_dicts(cur)]
        return items
    finally:
        conn.close()


def get_mapping(tenant_id, mapping_id):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM dbo.product_mapping WHERE tenant_id = ? AND mapping_id = ? AND is_deleted = 0",
            (tenant_id, mapping_id),
        )
        rows = _rows_to_dicts(cur)
        return stringify(rows[0]) if rows else None
    finally:
        conn.close()


def list_candidates(tenant_id, mapping_id):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT * FROM dbo.product_mapping_candidate
            WHERE tenant_id = ? AND mapping_id = ?
            ORDER BY total_score DESC
            """,
            (tenant_id, mapping_id),
        )
        return [stringify(r) for r in _rows_to_dicts(cur)]
    finally:
        conn.close()


def _resolve_supplier(cur, tenant_id, source_store_id, target_store_id):
    """Resolve the SOURCE store's own local SupplierCode/name for the TARGET
    store, via procurement.store_supplier_map + sync.Suppliers — never
    guessed, never hardcoded (e.g. NMA's local code for NMW is data-driven,
    currently '94', but that is looked up fresh every time). Raises
    ValueError — the caller rolls back — when either link is missing, so an
    unverified SupplierCode can never reach sync.SupplierProductMatch."""
    cur.execute("SELECT store_code FROM dbo.stores WHERE store_id = ?", (target_store_id,))
    row = cur.fetchone()
    if not row or not row[0]:
        raise ValueError(f"Target store {target_store_id} has no store_code in dbo.stores.")
    target_store_code = row[0]

    cur.execute(
        """
        SELECT local_supplier_code FROM procurement.store_supplier_map
        WHERE tenant_id = ? AND store_id = ? AND source_store_code = ?
        """,
        (tenant_id, source_store_id, target_store_code),
    )
    row = cur.fetchone()
    if not row:
        raise ValueError(
            f"No procurement.store_supplier_map entry linking store {source_store_id} "
            f"to source_store_code '{target_store_code}' — refusing to guess a SupplierCode."
        )
    supplier_code = row[0]

    cur.execute(
        """
        SELECT suppliername FROM sync.Suppliers
        WHERE store_id = ? AND CAST(suppliercode AS VARCHAR(50)) = CAST(? AS VARCHAR(50))
          AND ISNULL(isActive, 1) = 1
        """,
        (source_store_id, supplier_code),
    )
    row = cur.fetchone()
    if not row:
        raise ValueError(
            f"SupplierCode {supplier_code} is not an active supplier at store {source_store_id} "
            f"in sync.Suppliers — refusing to insert an unverified SupplierProductMatch."
        )
    return supplier_code, row[0]


def _upsert_supplier_product_match(cur, tenant_id, store_id, supplier_code,
                                    supplier_product_code, supplier_product_name,
                                    own_product_code, actor):
    """Idempotent upsert into sync.SupplierProductMatch (PK: store_id,
    SupplierCode, SupplierProductCode) — same shape as
    supplier_stock_analysis.repository.upsert_mapping. Runs on the caller's
    own cursor/transaction so an approval and its SupplierProductMatch row
    commit or roll back together.

    sync.SupplierProductMatch is populated by the legacy store agent's own
    sync process, not just by this code path, so a (store, SupplierCode,
    SupplierProductCode) key can already carry a DIFFERENT, legitimately
    correct ProductCode (e.g. from the store's own GRN history). Silently
    overwriting that would corrupt real invoice auto-resolution data, so a
    conflicting existing row raises instead of being clobbered — the
    approval fails and the mapping stays PENDING for a human to resolve."""
    try:
        own_code_int = int(own_product_code)
    except (TypeError, ValueError):
        raise ValueError(f"source_product_code {own_product_code!r} is not a numeric ProductCode.")

    cur.execute(
        """
        SELECT ProductCode FROM sync.SupplierProductMatch
        WHERE store_id = ? AND SupplierCode = ? AND SupplierProductCode = ?
        """,
        (store_id, supplier_code, supplier_product_code),
    )
    row = cur.fetchone()
    if row and row[0] is not None and int(row[0]) != own_code_int:
        raise ValueError(
            f"sync.SupplierProductMatch already links SupplierCode {supplier_code} / "
            f"SupplierProductCode {supplier_product_code} at store {store_id} to a DIFFERENT "
            f"ProductCode {row[0]} — refusing to overwrite it with {own_code_int}."
        )

    if row:
        cur.execute(
            """
            UPDATE sync.SupplierProductMatch
            SET SupplierProductName = ?, ProductCode = ?, UserName = ?,
                LastModifiedDate = GETDATE(), IsActive = 1, tenant_id = ?
            WHERE store_id = ? AND SupplierCode = ? AND SupplierProductCode = ?
            """,
            (supplier_product_name, own_code_int, actor, tenant_id,
             store_id, supplier_code, supplier_product_code),
        )
    else:
        cur.execute(
            """
            INSERT INTO sync.SupplierProductMatch
                (store_id, tenant_id, SupplierCode, SupplierProductCode,
                 SupplierProductName, ProductCode, UserName, LastModifiedDate, IsActive)
            VALUES (?, ?, ?, ?, ?, ?, ?, GETDATE(), 1)
            """,
            (store_id, tenant_id, supplier_code, supplier_product_code,
             supplier_product_name, own_code_int, actor),
        )


def set_status(tenant_id, mapping_id, new_status, actor=None,
               target_product_code=None, target_product_name=None,
               method=None, confidence=None):
    """Approve / reject / remap a mapping and write an audit row. An APPROVE
    also upserts sync.SupplierProductMatch for the mapping's store pair in
    the SAME transaction — the mapping only flips to APPROVED if that write
    succeeds too, never leaving a status change with no matching
    SupplierProductMatch row."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT status, source_store_id, target_store_id,
                   source_product_code, target_product_code, target_product_name
            FROM dbo.product_mapping WHERE tenant_id = ? AND mapping_id = ? AND is_deleted = 0
            """,
            (tenant_id, mapping_id),
        )
        row = cur.fetchone()
        if not row:
            return None
        (old_status, source_store_id, target_store_id,
         source_product_code, cur_target_code, cur_target_name) = row

        sets = ["status = ?", "updated_at = GETDATE()", "updated_by = ?"]
        params = [new_status, as_uid(actor)]
        if target_product_code is not None:
            sets.append("target_product_code = ?"); params.append(target_product_code)
        if target_product_name is not None:
            sets.append("target_product_name = ?"); params.append(target_product_name)
        if method is not None:
            sets.append("match_method = ?"); params.append(method)
        if confidence is not None:
            sets.append("confidence = ?"); params.append(confidence)

        if new_status == "APPROVED":
            final_target_code = target_product_code if target_product_code is not None else cur_target_code
            final_target_name = target_product_name if target_product_name is not None else cur_target_name
            supplier_code, _supplier_name = _resolve_supplier(cur, tenant_id, source_store_id, target_store_id)
            _upsert_supplier_product_match(
                cur, tenant_id, source_store_id, supplier_code,
                final_target_code, final_target_name, source_product_code, as_uid(actor),
            )

        params.extend([tenant_id, mapping_id])
        cur.execute(
            f"UPDATE dbo.product_mapping SET {', '.join(sets)} WHERE tenant_id = ? AND mapping_id = ?",
            tuple(params),
        )
        action = {"APPROVED": "APPROVE", "REJECTED": "REJECT"}.get(new_status, "REMAP")
        cur.execute(
            f"INSERT INTO dbo.product_mapping_audit ({','.join(_AUDIT_COLS)}) "
            f"VALUES ({','.join('?' * len(_AUDIT_COLS))})",
            (str(uuid.uuid4()), tenant_id, mapping_id, None, action,
             old_status, new_status, as_uid(actor),
             target_product_code and f"-> {target_product_code}"),
        )
        conn.commit()
        return get_mapping(tenant_id, mapping_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _pending_count(cur, tenant_id, source_store_id, target_store_id):
    cur.execute(
        """
        SELECT COUNT(*) FROM dbo.product_mapping
        WHERE tenant_id = ? AND is_deleted = 0 AND status = 'PENDING'
          AND source_store_id = ? AND target_store_id = ?
        """,
        (tenant_id, source_store_id, target_store_id),
    )
    return cur.fetchone()[0]


def _approved_today(cur, tenant_id, source_store_id, target_store_id):
    cur.execute(
        """
        SELECT COUNT(*) FROM dbo.product_mapping
        WHERE tenant_id = ? AND is_deleted = 0 AND status = 'APPROVED'
          AND source_store_id = ? AND target_store_id = ?
          AND updated_at >= CAST(GETDATE() AS DATE)
        """,
        (tenant_id, source_store_id, target_store_id),
    )
    return cur.fetchone()[0]


def review_progress(tenant_id, source_store_id, target_store_id):
    """Live counters for the Manual Review dashboard (remaining + approved today)."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        return {
            "remaining": _pending_count(cur, tenant_id, source_store_id, target_store_id),
            "approved_today": _approved_today(cur, tenant_id, source_store_id, target_store_id),
        }
    finally:
        conn.close()


def _approve_detail(old_code, old_name, new_code, new_name, confidence, manual):
    """Human-readable audit trail entry carrying old product, new product and
    confidence (the audit table has no dedicated product columns)."""
    conf = "" if confidence is None else f" @ {confidence:g}"
    new = f"{new_name or '—'} ({new_code or '—'})"
    if manual:
        old = f"{old_name or '—'} ({old_code or '—'})"
        return (f"manual override: {old} -> {new}{conf}")[:1000]
    return (f"confirm suggested: {new}{conf}")[:1000]


def bulk_review(tenant_id, action, items, source_store_id, target_store_id,
                page=1, page_size=50, actor=None):
    """Approve / reject a page of PENDING mappings in ONE transaction.

    ``items`` = ``[{mapping_id, target_product_code?, target_product_name?}]``.
    An APPROVE item carrying a target is a manual override (re-map @ MANUAL);
    without one it confirms the engine's suggestion.

    Hardening: duplicate ids collapse; only rows still PENDING change (a
    ``status = 'PENDING'`` guard + ``OUTPUT`` make it concurrency-safe — a row
    another reviewer already decided is never overwritten and counts as skipped);
    deleted rows are silently skipped; override targets are validated against the
    target store's live, active product master and rejected with a friendly
    reason if invalid. Every applied change writes an audit row (old product ->
    new product @ confidence). One transaction; batched, index-friendly SQL keeps
    a 50-row page well under a second.
    """
    by_id = {}
    for it in items:
        mid = it.get("mapping_id")
        if mid:
            by_id[str(mid)] = it            # duplicate review ids collapse here
    ids = list(by_id.keys())
    if not ids:
        raise ValueError("No mappings were selected.")
    if action not in ("APPROVE", "REJECT"):
        raise ValueError(f"Unsupported bulk action: {action}")

    actor_uid = as_uid(actor)
    conn = get_connection()
    try:
        cur = conn.cursor()

        # 1. Load the selected rows once: validates existence + not-deleted, and
        #    supplies current status, the existing (old) target and confidence
        #    for the audit trail. Single set query — no N+1.
        placeholders = ",".join("?" * len(ids))
        cur.execute(
            f"""
            SELECT CAST(mapping_id AS VARCHAR(50)), status, source_product_code,
                   target_product_code, target_product_name, confidence
            FROM dbo.product_mapping
            WHERE tenant_id = ? AND is_deleted = 0 AND mapping_id IN ({placeholders})
            """,
            tuple([tenant_id] + ids),
        )
        existing = {
            r[0]: {"status": r[1], "source_code": r[2], "old_code": r[3], "old_name": r[4],
                   "confidence": float(r[5]) if r[5] is not None else None}
            for r in cur.fetchall()
        }
        actionable = [i for i in ids if existing.get(i, {}).get("status") == "PENDING"]

        failed = []   # [{mapping_id, reason}] — invalid override targets

        # 2. Validate manual-override targets against the target store's live,
        #    active product master in one set query (rejects inactive / deleted /
        #    unknown / wrong-store codes).
        override_codes = {
            str(by_id[i]["target_product_code"])
            for i in actionable if by_id[i].get("target_product_code")
        }
        valid_targets = {}
        if override_codes:
            cph = ",".join("?" * len(override_codes))
            cur.execute(
                f"""
                SELECT CAST(ProductCode AS VARCHAR(50)), ProductName
                FROM sync.Products
                WHERE tenant_id = ? AND store_id = ? AND ISNULL(isActive, 1) = 1
                  AND CAST(ProductCode AS VARCHAR(50)) IN ({cph})
                """,
                tuple([tenant_id, target_store_id] + list(override_codes)),
            )
            valid_targets = {r[0]: r[1] for r in cur.fetchall()}

        approved = rejected = 0
        audit_rows = []

        if action == "APPROVE":
            plain, overrides = [], []
            for i in actionable:
                code = by_id[i].get("target_product_code")
                if code:
                    code = str(code)
                    if code in valid_targets:
                        overrides.append(i)
                    else:
                        failed.append({
                            "mapping_id": i,
                            "reason": f"Product {code} is not an active product in the target store.",
                        })
                else:
                    plain.append(i)

            # Resolve the store-pair's local SupplierCode/name ONCE — an
            # approval writes both dbo.product_mapping AND
            # sync.SupplierProductMatch in this same transaction, so a bad or
            # missing resolution must abort the whole batch before any row is
            # touched, not half-apply it.
            supplier_code = None
            if plain or overrides:
                supplier_code, _supplier_name = _resolve_supplier(
                    cur, tenant_id, source_store_id, target_store_id)

            # 2a. Plain approvals — one set-based, PENDING-guarded UPDATE. OUTPUT
            #     hands back exactly the rows we actually moved (concurrency-safe).
            if plain:
                pph = ",".join("?" * len(plain))
                cur.execute(
                    f"""
                    UPDATE dbo.product_mapping
                    SET status = 'APPROVED', updated_at = GETDATE(), updated_by = ?
                    OUTPUT CAST(inserted.mapping_id AS VARCHAR(50))
                    WHERE tenant_id = ? AND status = 'PENDING' AND mapping_id IN ({pph})
                    """,
                    tuple([actor_uid, tenant_id] + plain),
                )
                for (mid,) in cur.fetchall():
                    e = existing[mid]
                    _upsert_supplier_product_match(
                        cur, tenant_id, source_store_id, supplier_code,
                        e["old_code"], e["old_name"], e["source_code"], actor_uid,
                    )
                    approved += 1
                    audit_rows.append((str(uuid.uuid4()), tenant_id, mid, None, "APPROVE",
                                       "PENDING", "APPROVED", actor_uid,
                                       _approve_detail(e["old_code"], e["old_name"],
                                                       e["old_code"], e["old_name"],
                                                       e["confidence"], manual=False)))

            # 2b. Overrides re-map to a different target each, so loop with the
            #     same guard + OUTPUT (few rows; comfortably within budget).
            manual_conf = scoring.CONFIDENCE["MANUAL"]
            for i in overrides:
                new_code = str(by_id[i]["target_product_code"])
                new_name = by_id[i].get("target_product_name") or valid_targets[new_code]
                cur.execute(
                    """
                    UPDATE dbo.product_mapping
                    SET status = 'APPROVED', target_product_code = ?, target_product_name = ?,
                        match_method = 'MANUAL', confidence = ?, updated_at = GETDATE(), updated_by = ?
                    OUTPUT CAST(inserted.mapping_id AS VARCHAR(50))
                    WHERE tenant_id = ? AND status = 'PENDING' AND mapping_id = ?
                    """,
                    (new_code, new_name, manual_conf, actor_uid, tenant_id, i),
                )
                if cur.fetchone():
                    e = existing[i]
                    _upsert_supplier_product_match(
                        cur, tenant_id, source_store_id, supplier_code,
                        new_code, new_name, e["source_code"], actor_uid,
                    )
                    approved += 1
                    audit_rows.append((str(uuid.uuid4()), tenant_id, i, None, "APPROVE",
                                       "PENDING", "APPROVED", actor_uid,
                                       _approve_detail(e["old_code"], e["old_name"],
                                                       new_code, new_name, manual_conf, manual=True)))

        else:  # REJECT
            if actionable:
                aph = ",".join("?" * len(actionable))
                cur.execute(
                    f"""
                    UPDATE dbo.product_mapping
                    SET status = 'REJECTED', updated_at = GETDATE(), updated_by = ?
                    OUTPUT CAST(inserted.mapping_id AS VARCHAR(50))
                    WHERE tenant_id = ? AND status = 'PENDING' AND mapping_id IN ({aph})
                    """,
                    tuple([actor_uid, tenant_id] + actionable),
                )
                for (mid,) in cur.fetchall():
                    e = existing[mid]
                    rejected += 1
                    conf = "" if e["confidence"] is None else f" @ {e['confidence']:g}"
                    audit_rows.append((str(uuid.uuid4()), tenant_id, mid, None, "REJECT",
                                       "PENDING", "REJECTED", actor_uid,
                                       (f"reject suggested: {e['old_name'] or '—'} "
                                        f"({e['old_code'] or '—'}){conf}")[:1000]))

        if audit_rows:
            cur.fast_executemany = True
            cur.executemany(
                f"INSERT INTO dbo.product_mapping_audit ({','.join(_AUDIT_COLS)}) "
                f"VALUES ({','.join('?' * len(_AUDIT_COLS))})",
                audit_rows,
            )
        conn.commit()

        # Everything asked for that we did NOT apply (already decided, deleted,
        # lost a concurrency race, or invalid override target) counts as skipped.
        acted = approved + rejected
        skipped = len(ids) - acted

        remaining = _pending_count(cur, tenant_id, source_store_id, target_store_id)
        approved_today = _approved_today(cur, tenant_id, source_store_id, target_store_id)
        total_pages = max(1, -(-remaining // int(page_size)))  # ceil
        current_page = min(max(1, int(page)), total_pages)
        return {
            "approved": approved,
            "rejected": rejected,
            "skipped": skipped,
            "failed": failed,
            "remaining": remaining,
            "approved_today": approved_today,
            "current_page": current_page,
            "next_page": current_page,        # retained for client compatibility
            "total_pages": total_pages,
            "has_next": current_page < total_pages,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def search_mapped(tenant_id, source_store_id, source_product_code, target_store_id=None):
    """SearchMappedProduct — the approved target(s) for a source product."""
    where = ["tenant_id = ?", "is_deleted = 0", "source_store_id = ?",
             "source_product_code = ?", "status IN ('APPROVED','AUTO')"]
    params = [tenant_id, source_store_id, source_product_code]
    if target_store_id:
        where.append("target_store_id = ?"); params.append(target_store_id)
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT * FROM dbo.product_mapping WHERE {' AND '.join(where)} ORDER BY confidence DESC",
            tuple(params),
        )
        return [stringify(r) for r in _rows_to_dicts(cur)]
    finally:
        conn.close()


def status_counts(tenant_id, source_store_id=None, target_store_id=None):
    where = ["tenant_id = ?", "is_deleted = 0"]
    params = [tenant_id]
    if source_store_id:
        where.append("source_store_id = ?"); params.append(source_store_id)
    if target_store_id:
        where.append("target_store_id = ?"); params.append(target_store_id)
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT status, COUNT(*) FROM dbo.product_mapping WHERE {' AND '.join(where)} GROUP BY status",
            tuple(params),
        )
        counts = {s: 0 for s in ("AUTO", "PENDING", "APPROVED", "REJECTED")}
        for status, n in cur.fetchall():
            counts[status] = n
        return counts
    finally:
        conn.close()


def method_counts(tenant_id, source_store_id=None, target_store_id=None):
    where = ["tenant_id = ?", "is_deleted = 0"]
    params = [tenant_id]
    if source_store_id:
        where.append("source_store_id = ?"); params.append(source_store_id)
    if target_store_id:
        where.append("target_store_id = ?"); params.append(target_store_id)
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT ISNULL(match_method,'UNMATCHED') AS m, COUNT(*) "
            f"FROM dbo.product_mapping WHERE {' AND '.join(where)} GROUP BY match_method",
            tuple(params),
        )
        return {m: n for m, n in cur.fetchall()}
    finally:
        conn.close()


def list_audit(tenant_id, mapping_id=None, page=1, page_size=100):
    where = ["tenant_id = ?"]
    params = [tenant_id]
    if mapping_id:
        where.append("mapping_id = ?"); params.append(mapping_id)
    offset = max(0, (int(page) - 1) * int(page_size))
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT * FROM dbo.product_mapping_audit WHERE {' AND '.join(where)}
            ORDER BY created_at DESC
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
            """,
            tuple(params) + (offset, int(page_size)),
        )
        return [stringify(r) for r in _rows_to_dicts(cur)]
    finally:
        conn.close()
