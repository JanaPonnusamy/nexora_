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
Mirror the source POS's OWN behaviour: treat the store's live
``ProductSaleInformation`` as the source of truth and, for any mirror row whose
``(Bnumber, ID)`` no longer exists there, MOVE it into
``sync.MProductSaleInformation`` (a platform-side clone of the modified-history
table) instead of the live mirror. The line stays queryable as history but no
longer doubles the report. Note the source's ``MProductSaleInformation`` re-keys
moved rows onto its own IDENTITY sequence, so it cannot be used as a tombstone
by ID — the disappearance from live PSI is the reliable signal.

A guard never moves below the current set: a bill is only reconciled when the
mirror already contains every current source ``ID`` (so a bill whose new rows
have not been synced yet is skipped, never emptied).

``maybe_auto_reconcile`` runs this as a throttled, best-effort self-heal on
report load so a freshly-modified bill never shows doubled lines even if nobody
clicks the Reconcile button.

Source credentials are read per store from OrderNMC's ``dbo.Stores`` (exactly
where the legacy tooling keeps them); see modules.legacy_order.database.
"""

import logging
import threading
from datetime import datetime, timedelta

from config.database import get_connection
from modules.legacy_order import database as legacy_db

logger = logging.getLogger(__name__)

# How often the throttled self-heal is allowed to run per store.
AUTO_INTERVAL_MINUTES = 10


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


def _ensure_archive(cur):
    """Create the platform-side modified-history table (a structural clone of
    ``sync.ProductSaleInformation``) plus a lookup index, once. Superseded lines
    are MOVED here instead of being hard-deleted, mirroring how the source POS
    keeps ``dbo.MProductSaleInformation``."""
    cur.execute(
        """
        IF OBJECT_ID('sync.MProductSaleInformation') IS NULL
            SELECT TOP (0) * INTO sync.MProductSaleInformation
            FROM sync.ProductSaleInformation;

        IF OBJECT_ID('sync.MProductSaleInformation') IS NOT NULL
           AND NOT EXISTS (
               SELECT 1 FROM sys.indexes
               WHERE name = 'IX_MProductSaleInformation_key'
                 AND object_id = OBJECT_ID('sync.MProductSaleInformation'))
            CREATE INDEX IX_MProductSaleInformation_key
                ON sync.MProductSaleInformation (tenant_id, store_id, Bnumber, ID);
        """
    )


def _shared_columns(cur):
    """Columns common to both tables, in source order — used to build an explicit
    INSERT..SELECT that survives either table gaining a column later."""
    cur.execute(
        """
        SELECT c.COLUMN_NAME
        FROM INFORMATION_SCHEMA.COLUMNS c
        WHERE c.TABLE_SCHEMA = 'sync' AND c.TABLE_NAME = 'ProductSaleInformation'
          AND EXISTS (
              SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS m
              WHERE m.TABLE_SCHEMA = 'sync' AND m.TABLE_NAME = 'MProductSaleInformation'
                AND m.COLUMN_NAME = c.COLUMN_NAME)
        ORDER BY c.ORDINAL_POSITION
        """
    )
    return [r[0] for r in cur.fetchall()]


def reconcile_store(tenant_id, store_id, apply_changes=False):
    """Move mirror ProductSaleInformation rows the source no longer has into the
    ``sync.MProductSaleInformation`` history table (they were superseded by a bill
    modification).

    apply_changes=False -> dry run (report only). Returns a summary dict.
    """
    server, database, username, password, store_code = resolve_source(tenant_id, store_id)
    source = _source_live_ids(server, database, username, password)
    mirror = _mirror_ids(tenant_id, store_id)

    orphans = {}          # bnumber -> [ids to move]
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
    archived = 0
    moved = 0
    if apply_changes and orphans:
        conn = get_connection()
        cur = conn.cursor()
        try:
            _ensure_archive(cur)
            conn.commit()
            cols = _shared_columns(cur)
            col_list = ", ".join(f"[{c}]" for c in cols)
            for bn, ids in orphans.items():
                placeholders = ",".join("?" for _ in ids)
                # Archive first (skip anything already archived), then remove the
                # superseded rows from the live mirror. One transaction per bill.
                cur.execute(
                    f"INSERT INTO sync.MProductSaleInformation ({col_list}) "
                    f"SELECT {col_list} FROM sync.ProductSaleInformation psi "
                    f"WHERE psi.tenant_id = ? AND psi.store_id = ? AND psi.Bnumber = ? "
                    f"AND psi.ID IN ({placeholders}) "
                    f"AND NOT EXISTS (SELECT 1 FROM sync.MProductSaleInformation m "
                    f"    WHERE m.tenant_id = psi.tenant_id AND m.store_id = psi.store_id "
                    f"      AND m.Bnumber = psi.Bnumber AND m.ID = psi.ID)",
                    (tenant_id, store_id, bn, *ids),
                )
                archived += cur.rowcount
                cur.execute(
                    "DELETE FROM sync.ProductSaleInformation "
                    f"WHERE tenant_id = ? AND store_id = ? AND Bnumber = ? AND ID IN ({placeholders})",
                    (tenant_id, store_id, bn, *ids),
                )
                moved += cur.rowcount
            conn.commit()
        finally:
            cur.close()
            conn.close()
        logger.info(
            "NMW reconcile store=%s: moved %d orphan PSI rows (%d archived) across %d bills",
            store_code, moved, archived, len(orphans),
        )

    return {
        "store_code": store_code,
        "source_bills": len(source),
        "mirror_bills": len(mirror),
        "affected_bills": len(orphans),
        "orphan_rows": orphan_rows,
        "archived": archived,
        "moved": moved,
        # Back-compat: existing UI reads `deleted` as "rows removed from the live
        # mirror" (now they are moved to history, not destroyed).
        "deleted": moved,
        "skipped_lag_bills": skipped_lag,
        "applied": bool(apply_changes),
        "sample": {bn: len(ids) for bn, ids in list(orphans.items())[:15]},
    }


def _ensure_state(cur):
    cur.execute(
        """
        IF OBJECT_ID('dbo.nmw_reconcile_state') IS NULL
        CREATE TABLE dbo.nmw_reconcile_state (
            tenant_id   uniqueidentifier NOT NULL,
            store_id    uniqueidentifier NOT NULL,
            last_run_at datetime         NOT NULL,
            CONSTRAINT PK_nmw_reconcile_state PRIMARY KEY (tenant_id, store_id)
        );
        """
    )


def maybe_auto_reconcile(tenant_id, store_id, interval_minutes=AUTO_INTERVAL_MINUTES):
    """Throttled, best-effort self-heal so a modified bill never shows doubled
    lines even if nobody clicks Reconcile.

    Claims the throttle slot synchronously (so concurrent report loads don't all
    fire), then runs the actual move on a background thread — the report must not
    block on, or fail because of, this cleanup (the source POS may be offline).
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        _ensure_state(cur)
        cur.execute(
            "SELECT last_run_at FROM dbo.nmw_reconcile_state WHERE tenant_id = ? AND store_id = ?",
            (tenant_id, store_id),
        )
        row = cur.fetchone()
        if row and row[0] and row[0] > datetime.now() - timedelta(minutes=interval_minutes):
            return False  # throttled
        cur.execute(
            """
            MERGE dbo.nmw_reconcile_state AS t
            USING (SELECT ? AS tenant_id, ? AS store_id) s
                ON t.tenant_id = s.tenant_id AND t.store_id = s.store_id
            WHEN MATCHED THEN UPDATE SET last_run_at = GETDATE()
            WHEN NOT MATCHED THEN INSERT (tenant_id, store_id, last_run_at)
                VALUES (s.tenant_id, s.store_id, GETDATE());
            """,
            (tenant_id, store_id),
        )
        conn.commit()
    except Exception:
        logger.warning("NMW auto-reconcile throttle check failed", exc_info=True)
        try:
            conn.rollback()
        except Exception:
            pass
        return False
    finally:
        cur.close()
        conn.close()

    def _run():
        try:
            reconcile_store(tenant_id, store_id, apply_changes=True)
        except Exception:
            logger.warning("NMW auto-reconcile skipped (source unavailable?)", exc_info=True)

    threading.Thread(target=_run, name="nmw-auto-reconcile", daemon=True).start()
    return True
