"""Mirror reconciliation for modified/deleted source bill lines.

Why this exists
---------------
The store POS (Shopaid) keeps only the CURRENT version of a bill in
``dbo.ProductSaleInformation``. When a bill is *modified*, it MOVES the previous
line rows into ``dbo.MProductSaleInformation`` (its modified-history table) and
writes fresh line rows with new ``ID`` values. The old ``ID`` values disappear
from the live table.

Our sync engine is insert/upsert-only (MERGE on PK = ``ID``, watermark =
``TransactionDate``) with NO delete propagation, so once an old line has been
mirrored into ``sync.ProductSaleInformation`` it stays there forever. A modified
bill therefore accumulates BOTH generations in the mirror, which doubled the
lines shown (and exported) by the NMW Sales Report.

Fix
---
Treat the store's live ``ProductSaleInformation`` as the source of truth and
delete any mirror row whose ``(Bnumber, ID)`` no longer exists there. A guard
never deletes below the current set: a bill is only reconciled when the mirror
already contains every current source ``ID`` (so a bill whose new rows have not
been synced yet is skipped, never emptied).

Source credentials are read per store from OrderNMC's ``dbo.Stores`` (exactly
where the legacy tooling keeps them); see modules.legacy_order.database.
"""

import logging

from config.database import get_connection
from modules.legacy_order import database as legacy_db

logger = logging.getLogger(__name__)


def _norm(value):
    return "".join(ch for ch in (value or "").upper() if ch.isalnum())


def resolve_source(tenant_id, store_id):
    """Return (server, database, username, password, store_code) for a platform
    store by matching it to its OrderNMC dbo.Stores row (by store code/name)."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT store_code, store_name FROM dbo.stores WHERE tenant_id = ? AND store_id = ?",
            (tenant_id, store_id),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError("platform store not found")
        store_code, store_name = row[0], row[1]
    finally:
        cur.close()
        conn.close()

    targets = {_norm(store_code), _norm(store_name)}
    targets.discard("")

    legacy = legacy_db.get_central_connection()
    lcur = legacy.cursor()
    try:
        lcur.execute(
            "SELECT StoreName, ServerName, [Database], UserName, Password "
            "FROM dbo.Stores WHERE IsActive = 1"
        )
        for r in lcur.fetchall():
            name, server, database, user, pwd = r
            if _norm(name) in targets and server and database:
                return server, database, user, pwd, store_code
    finally:
        lcur.close()
        legacy.close()
    raise ValueError(f"no OrderNMC source mapping for store '{store_code}'")


def _source_live_ids(server, database, username, password):
    """{Bnumber: set(ID)} of every current line in the store's live PSI."""
    conn = legacy_db.get_branch_connection(server, database, username, password, timeout=60)
    cur = conn.cursor()
    try:
        cur.execute("SELECT BNumber, ID FROM dbo.ProductSaleInformation")
        out = {}
        for bn, id_ in cur.fetchall():
            out.setdefault(bn, set()).add(id_)
        return out
    finally:
        cur.close()
        conn.close()


def _mirror_ids(tenant_id, store_id):
    """{Bnumber: set(ID)} of every mirrored line for the store."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT Bnumber, ID FROM sync.ProductSaleInformation WHERE tenant_id = ? AND store_id = ?",
            (tenant_id, store_id),
        )
        out = {}
        for bn, id_ in cur.fetchall():
            out.setdefault(bn, set()).add(id_)
        return out
    finally:
        cur.close()
        conn.close()


def reconcile_store(tenant_id, store_id, apply_changes=False):
    """Delete mirror ProductSaleInformation rows the source no longer has.

    apply_changes=False -> dry run (report only). Returns a summary dict.
    """
    server, database, username, password, store_code = resolve_source(tenant_id, store_id)
    source = _source_live_ids(server, database, username, password)
    mirror = _mirror_ids(tenant_id, store_id)

    orphans = {}          # bnumber -> [ids to delete]
    skipped_lag = []      # current rows not fully synced yet -> left untouched
    for bn, mids in mirror.items():
        live = source.get(bn)
        if not live:
            # Bill absent from source live entirely -> don't guess, leave it.
            continue
        if not live.issubset(mids):
            # Some current rows aren't mirrored yet: only note it if there are
            # ALSO stale extras (a genuine lag on a modified bill).
            if mids - live:
                skipped_lag.append(bn)
            continue
        extra = mids - live
        if extra:
            orphans[bn] = sorted(extra)

    orphan_rows = sum(len(v) for v in orphans.values())
    deleted = 0
    if apply_changes and orphans:
        conn = get_connection()
        cur = conn.cursor()
        try:
            for bn, ids in orphans.items():
                placeholders = ",".join("?" for _ in ids)
                cur.execute(
                    "DELETE FROM sync.ProductSaleInformation "
                    f"WHERE tenant_id = ? AND store_id = ? AND Bnumber = ? AND ID IN ({placeholders})",
                    (tenant_id, store_id, bn, *ids),
                )
                deleted += cur.rowcount
            conn.commit()
        finally:
            cur.close()
            conn.close()
        logger.info(
            "NMW reconcile store=%s: deleted %d orphan PSI rows across %d bills",
            store_code, deleted, len(orphans),
        )

    return {
        "store_code": store_code,
        "source_bills": len(source),
        "mirror_bills": len(mirror),
        "affected_bills": len(orphans),
        "orphan_rows": orphan_rows,
        "deleted": deleted,
        "skipped_lag_bills": skipped_lag,
        "applied": bool(apply_changes),
        "sample": {bn: len(ids) for bn, ids in list(orphans.items())[:15]},
    }
