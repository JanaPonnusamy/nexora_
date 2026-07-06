"""Data access for the Product Mapping tables (dbo.product_mapping*, dictionary).

Raw pyodbc, parameterized, tenant-scoped. Persists engine decisions, serves the
review/approval workflow, and reads the configurable normalization dictionary.
Client-generated GUIDs let mappings and their candidates be bulk-inserted with
``fast_executemany`` in a single round trip each.
"""

import uuid

from config.database import get_connection
from modules.procurement._dbutil import as_uid, rows_to_dicts as _rows_to_dicts, stringify

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
        where.append("status = ?"); params.append(status)
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


def set_status(tenant_id, mapping_id, new_status, actor=None,
               target_product_code=None, target_product_name=None,
               method=None, confidence=None):
    """Approve / reject / remap a mapping and write an audit row."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT status FROM dbo.product_mapping WHERE tenant_id = ? AND mapping_id = ? AND is_deleted = 0",
            (tenant_id, mapping_id),
        )
        row = cur.fetchone()
        if not row:
            return None
        old_status = row[0]

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
