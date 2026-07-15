"""Learned Product Category store (Shelf Sorting "trainable agent").

Persists a product -> shelf category mapping so categorisation improves over
time from three sources: human confirmations (manual), Claude suggestions
(llm), and other stores' UnitDescription (cross_store). Keyed by a normalised
product NAME, tenant-wide (ProductCode is not consistent across stores).

Also provides the cross-store lookup: borrow a product's UnitDescription from
any store in the tenant that has one, matched by normalised name.
"""

import os
import re

from config.database import get_connection
from modules.procurement._dbutil import as_uid as _as_uid, rows_to_dicts as _rows_to_dicts

_SQL_DIR = os.path.join(os.path.dirname(__file__), "sql")
_DDL_FILE = os.path.join(_SQL_DIR, "0020_product_category.sql")
_schema_ready = False


def normalize_name(name):
    """Product name -> stable key: upper-cased, non-alphanumerics collapsed to
    single spaces, trimmed. Keeps digits (dose strengths distinguish products)."""
    if name is None:
        return ""
    return re.sub(r"[^A-Z0-9]+", " ", str(name).upper()).strip()


def ensure_schema():
    global _schema_ready
    if _schema_ready:
        return
    conn = get_connection()
    try:
        cur = conn.cursor()
        with open(_DDL_FILE, "r", encoding="utf-8") as fh:
            script = fh.read()
        for batch in (b.strip() for b in script.split("\nGO")):
            if batch:
                cur.execute(batch)
        conn.commit()
    finally:
        conn.close()
    _schema_ready = True


def get_many(tenant_id, names):
    """Learned categories for a set of (original) product names ->
    {normalized_name: {'category', 'source', 'confirmed'}}. Confirmed/manual
    entries are what the caller should trust most; suggestions are included so
    the review screen can show them."""
    ensure_schema()
    keys = sorted({normalize_name(n) for n in names if normalize_name(n)})
    out = {}
    if not keys:
        return out
    conn = get_connection()
    try:
        cur = conn.cursor()
        for i in range(0, len(keys), 1000):
            chunk = keys[i:i + 1000]
            placeholders = ", ".join("?" for _ in chunk)
            cur.execute(
                f"""
                SELECT product_key, category, source, confirmed
                FROM procurement.product_category
                WHERE tenant_id = ? AND product_key IN ({placeholders})
                """,
                (tenant_id, *chunk),
            )
            for r in _rows_to_dicts(cur):
                out[r["product_key"]] = {
                    "category": r["category"],
                    "source": r["source"],
                    "confirmed": bool(r["confirmed"]),
                }
        return out
    finally:
        conn.close()


def upsert(tenant_id, name, category, source="manual", confirmed=None, updated_by=None):
    """Insert/update one learned category. A manual confirmation always wins;
    a suggestion (llm/cross_store) never overwrites a confirmed manual entry."""
    ensure_schema()
    key = normalize_name(name)
    if not key or not category:
        return
    if confirmed is None:
        confirmed = 1 if source == "manual" else 0
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            MERGE procurement.product_category AS t
            USING (SELECT ? AS tenant_id, ? AS product_key) AS s
              ON t.tenant_id = s.tenant_id AND t.product_key = s.product_key
            WHEN MATCHED AND (t.confirmed = 0 OR ? = 1) THEN
              UPDATE SET category = ?, source = ?, confirmed = ?,
                         sample_name = ?, updated_by = ?, updated_at = GETDATE()
            WHEN NOT MATCHED THEN
              INSERT (tenant_id, product_key, category, source, confirmed, sample_name, updated_by)
              VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (
                tenant_id, key,
                confirmed,                                   # allow overwrite if this is a confirm
                category, source, confirmed, str(name), _as_uid(updated_by),
                tenant_id, key, category, source, confirmed, str(name), _as_uid(updated_by),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def upsert_many(tenant_id, entries, updated_by=None):
    """entries: [{name, category, source, confirmed}]."""
    for e in entries:
        upsert(tenant_id, e["name"], e["category"], e.get("source", "manual"),
               e.get("confirmed"), updated_by)


def cross_store_units(tenant_id, names):
    """Borrow a UnitDescription for each product NAME from any store in the
    tenant that has a non-blank one -> {normalized_name: unit_description}.
    Codes differ across stores, so we match on the normalised ProductName.
    Normalisation is done in Python (same rule as normalize_name) so it lines
    up exactly with the learned-table keys; the most-frequent unit wins."""
    keys = {normalize_name(n) for n in names if normalize_name(n)}
    if not keys:
        return {}
    conn = get_connection()
    try:
        cur = conn.cursor()
        # Guard: sync.Products must exist (it always does in a live store DB).
        cur.execute("SELECT OBJECT_ID('sync.Products')")
        if cur.fetchone()[0] is None:
            return {}
        cur.execute(
            """
            SELECT ProductName, RTRIM(UnitDescription) AS unit_description, COUNT(*) AS cnt
            FROM sync.Products
            WHERE tenant_id = ?
              AND UnitDescription IS NOT NULL AND RTRIM(UnitDescription) <> ''
            GROUP BY ProductName, RTRIM(UnitDescription)
            """,
            (tenant_id,),
        )
        best = {}  # normalized_name -> (unit, count)
        for r in _rows_to_dicts(cur):
            k = normalize_name(r["ProductName"])
            if k not in keys:
                continue
            cnt = r["cnt"] or 0
            if k not in best or cnt > best[k][1]:
                best[k] = (r["unit_description"], cnt)
        return {k: v[0] for k, v in best.items()}
    finally:
        conn.close()
