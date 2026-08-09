"""Read/approve data access for the NMW Sales Report (Bill-wise) module.

NMW is the warehouse store. It raises sales bills TO the other stores (the
destination store is the "customer" on the bill). A bill is considered
*despatched* once `sync.SaleInformation.IssuedDate` is set. Despatched bills are
surfaced here; a super admin then approves the despatch before store devices
display it. The destination store is resolved by matching the bill's
`CustomerCode` to `dbo.stores.ho_cust_code` (the store's customer code inside
NMW — the sales-side mirror of the existing `Ho_code` supplier mapping).

Nexora owns the approval state (`dbo.nmw_sales_dispatch_approval`); everything
else is read from the already-synced `sync.*` tables.
"""

from config.database import get_connection

WAREHOUSE_STORE_CODE = "NMW"

_schema_ready = False


def _ensure_schema(cursor):
    """Idempotent, self-healing DDL so the report works before a formal
    migration runs: the approval table, the stores.ho_cust_code column, and the
    IssuedDate column + sync-column selection on sync.SaleInformation.

    Adding IssuedDate to sync.sync_column_mapping makes future syncs carry it;
    the physical column is added here too so existing rows/queries don't error
    while the next sync back-fills values. Commits so the DDL persists even when
    reached from a read path (connections open with autocommit off)."""
    global _schema_ready
    if _schema_ready:
        return
    cursor.execute(
        """
        IF OBJECT_ID('dbo.nmw_sales_dispatch_approval') IS NULL
        CREATE TABLE dbo.nmw_sales_dispatch_approval (
            tenant_id       uniqueidentifier NOT NULL,
            source_store_id uniqueidentifier NOT NULL,
            bill_date       datetime         NOT NULL,
            bnumber         varchar(50)      NOT NULL,
            status          varchar(20)      NOT NULL CONSTRAINT DF_nmw_dispatch_status DEFAULT('approved'),
            approved_by     varchar(200)     NULL,
            approved_at     datetime         NULL,
            remarks         varchar(500)     NULL,
            CONSTRAINT PK_nmw_sales_dispatch_approval
                PRIMARY KEY (tenant_id, source_store_id, bill_date, bnumber)
        );

        IF COL_LENGTH('dbo.stores', 'ho_cust_code') IS NULL
            ALTER TABLE dbo.stores ADD ho_cust_code varchar(50) NULL;

        IF COL_LENGTH('sync.SaleInformation', 'IssuedDate') IS NULL
            ALTER TABLE sync.SaleInformation ADD IssuedDate datetime NULL;

        -- Select IssuedDate for future syncs (derive sync_table_id from an
        -- existing SaleInformation mapping row; no-op if already present or if
        -- SaleInformation isn't configured on this HO yet).
        IF EXISTS (SELECT 1 FROM sync.sync_column_mapping WHERE table_name = 'SaleInformation')
           AND NOT EXISTS (
               SELECT 1 FROM sync.sync_column_mapping
               WHERE table_name = 'SaleInformation' AND column_name = 'IssuedDate')
        INSERT INTO sync.sync_column_mapping
            (mapping_id, sync_table_id, table_name, column_name, data_type,
             is_selected, is_pk, is_hash, is_watermark, column_order, created_at)
        SELECT NEWID(), MAX(sync_table_id), 'SaleInformation', 'IssuedDate', 'datetime',
               1, 0, 0, 0, ISNULL(MAX(column_order), 0) + 1, GETDATE()
        FROM sync.sync_column_mapping
        WHERE table_name = 'SaleInformation';
        """
    )
    try:
        cursor.connection.commit()
    except AttributeError:
        pass
    _schema_ready = True


def get_nmw_store_id(tenant_id):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT TOP 1 store_id FROM dbo.stores WHERE tenant_id = ? AND UPPER(LTRIM(RTRIM(store_code))) = ?",
            (tenant_id, WAREHOUSE_STORE_CODE),
        )
        row = cursor.fetchone()
        return str(row[0]) if row else None
    finally:
        cursor.close()
        conn.close()


def user_store_ids(user_id):
    """Stores this user is assigned to (via dbo.user_store_roles). Used to scope
    a store user to only their own inbound bills."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT DISTINCT CAST(store_id AS VARCHAR(50)) FROM dbo.user_store_roles "
            "WHERE user_id = TRY_CAST(? AS uniqueidentifier) AND is_active = 1",
            (str(user_id),),
        )
        return [row[0] for row in cursor.fetchall()]
    finally:
        cursor.close()
        conn.close()


def _rows(cursor):
    columns = [col[0] for col in cursor.description]
    out = []
    for row in cursor.fetchall():
        record = dict(zip(columns, row))
        for key, value in list(record.items()):
            if hasattr(value, "isoformat"):
                record[key] = value.isoformat()
        out.append(record)
    return out


def list_bills(tenant_id, nmw_store_id, dest_store_ids, status, date_from, date_to):
    """Despatched NMW bills whose CustomerCode resolves to a destination store.

    dest_store_ids: None = every mapped store; a list = restrict to those store
    ids (used to scope a store user to their own store).
    status: 'pending' | 'approved' | 'all'.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        _ensure_schema(cursor)
        where = [
            "si.tenant_id = ?",
            "si.store_id = ?",
            "si.IssuedDate IS NOT NULL",
            "LTRIM(RTRIM(ISNULL(dst.ho_cust_code, ''))) <> ''",
        ]
        params = [tenant_id, nmw_store_id]

        if dest_store_ids is not None:
            if not dest_store_ids:
                return []
            placeholders = ", ".join("?" for _ in dest_store_ids)
            where.append(f"CAST(dst.store_id AS VARCHAR(50)) IN ({placeholders})")
            params.extend(dest_store_ids)

        if status and status.lower() in ("pending", "approved"):
            where.append("ISNULL(ap.status, 'pending') = ?")
            params.append(status.lower())

        if date_from:
            where.append("CAST(si.BillDate AS DATE) >= CAST(? AS DATE)")
            params.append(date_from)
        if date_to:
            where.append("CAST(si.BillDate AS DATE) <= CAST(? AS DATE)")
            params.append(date_to)

        cursor.execute(
            f"""
            SELECT
                si.BNumber                         AS bill_no,
                si.BillNumber                      AS bill_number,
                CAST(si.BillDate AS DATE)          AS bill_date,
                si.Billtime                        AS bill_time,
                si.IssuedDate                      AS issued_date,
                ISNULL(si.BillAmount, 0)           AS bill_amount,
                CAST(si.CustomerCode AS NVARCHAR(50)) AS customer_code,
                si.CustomerName                    AS customer_name,
                CAST(dst.store_id AS VARCHAR(50))  AS dest_store_id,
                dst.store_code                     AS dest_store_code,
                dst.store_name                     AS dest_store_name,
                ISNULL(ap.status, 'pending')       AS status,
                ap.approved_by                     AS approved_by,
                ap.approved_at                     AS approved_at
            FROM sync.SaleInformation si
            INNER JOIN dbo.stores dst
                ON dst.tenant_id = si.tenant_id
               AND LTRIM(RTRIM(dst.ho_cust_code)) = LTRIM(RTRIM(si.CustomerCode))
            LEFT JOIN dbo.nmw_sales_dispatch_approval ap
                ON ap.tenant_id = si.tenant_id
               AND ap.source_store_id = si.store_id
               AND ap.bill_date = si.BillDate
               AND ap.bnumber = si.BNumber
            WHERE {' AND '.join(where)}
            ORDER BY si.IssuedDate DESC, si.BillNumber DESC
            """,
            tuple(params),
        )
        return _rows(cursor)
    finally:
        cursor.close()
        conn.close()


def get_bill_items(tenant_id, nmw_store_id, bill_no, bill_date):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            ;WITH bill_match AS (
                SELECT TOP (1)
                    si.tenant_id, si.store_id, si.BNumber, si.BillNumber,
                    CAST(si.BillDate AS DATE) AS BillDate
                FROM sync.SaleInformation si
                WHERE si.tenant_id = ?
                  AND si.store_id = ?
                  AND si.BNumber = ?
                  AND (? IS NULL OR CAST(si.BillDate AS DATE) = CAST(? AS DATE))
                ORDER BY si.BillDate DESC, si.BillNumber DESC
            )
            SELECT
                CAST(psi.ProductCode AS NVARCHAR(100)) AS product_code,
                ISNULL(p.ProductName, CAST(psi.ProductCode AS NVARCHAR(100))) AS product_name,
                ISNULL(psi.Batchdescription, '')       AS batch_no,
                CAST(psi.Expirydate AS DATE)           AS expiry_date,
                ISNULL(psi.Quantity, 0)                AS qty,
                ISNULL(psi.Freequantity, 0)            AS free_qty,
                ISNULL(psi.MRP, 0)                     AS mrp,
                ISNULL(psi.Rate, 0)                    AS rate,
                ISNULL(psi.DiscountPercentage, 0)      AS discount_percentage,
                ISNULL(psi.Transactionamount, 0)       AS amount
            FROM bill_match bm
            -- Join on the full bill number (Bnumber) rather than the retail
            -- SeriesName = LEFT(BNumber,1) heuristic: NMW dispatch bills use a
            -- multi-char series (e.g. 'D' in '26-27D1920'), so the line rows key
            -- on Bnumber directly.
            INNER JOIN sync.ProductSaleInformation psi
                ON psi.tenant_id = bm.tenant_id
               AND psi.store_id = bm.store_id
               AND psi.BillNumber = bm.BillNumber
               AND psi.Bnumber = bm.BNumber
               AND CAST(psi.TransactionDate AS DATE) = bm.BillDate
            LEFT JOIN sync.Products p
                ON p.tenant_id = psi.tenant_id
               AND p.store_id = psi.store_id
               AND p.ProductCode = psi.ProductCode
            WHERE ISNULL(psi.TransactionValidity, 0) = 0
            ORDER BY ISNULL(p.ProductName, CAST(psi.ProductCode AS NVARCHAR(100))), ISNULL(psi.Batchdescription, '')
            """,
            (tenant_id, nmw_store_id, bill_no, bill_date, bill_date),
        )
        return _rows(cursor)
    finally:
        cursor.close()
        conn.close()


def set_store_cust_code(tenant_id, store_id, cust_code):
    """Manually set a store's NMW customer code on the platform stores row."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        _ensure_schema(cursor)
        cursor.execute(
            "UPDATE dbo.stores SET ho_cust_code = ? WHERE tenant_id = ? AND store_id = ?",
            ((cust_code or "").strip() or None, tenant_id, store_id),
        )
        conn.commit()
        return cursor.rowcount
    finally:
        cursor.close()
        conn.close()


def list_store_cust_codes(tenant_id):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        _ensure_schema(cursor)
        cursor.execute(
            "SELECT CAST(store_id AS VARCHAR(50)) AS store_id, store_code, store_name, ho_cust_code "
            "FROM dbo.stores WHERE tenant_id = ? ORDER BY store_code",
            (tenant_id,),
        )
        return _rows(cursor)
    finally:
        cursor.close()
        conn.close()


def _nmw_customers(cursor, tenant_id, nmw_store_id):
    """Distinct (CustomerCode, CustomerName) seen on NMW's bills — the de-facto
    customer master, since NMW's stores appear as its bill customers."""
    cursor.execute(
        """
        SELECT CAST(CustomerCode AS NVARCHAR(50)) AS code, MAX(CustomerName) AS name
        FROM sync.SaleInformation
        WHERE tenant_id = ? AND store_id = ?
          AND CustomerCode IS NOT NULL AND LTRIM(RTRIM(CustomerCode)) <> ''
        GROUP BY CAST(CustomerCode AS NVARCHAR(50))
        """,
        (tenant_id, nmw_store_id),
    )
    return [{"code": (r[0] or "").strip(), "name": (r[1] or "").strip()} for r in cursor.fetchall()]


def _normalize_name(value):
    return "".join(ch for ch in (value or "").upper() if ch.isalnum())


def auto_match_cust_codes(tenant_id, threshold=0.86, apply_changes=True):
    """Match each store to its most-similar NMW customer by name and set
    stores.ho_cust_code. Greedy global assignment (best score first, each
    customer used once) above `threshold`. Returns the proposed/applied rows so
    the admin can review and correct ambiguous matches in the panel.

    Note: NMW and NMC are one GST entity here (NMW is the C-branch warehouse),
    so NMC is not an NMW *customer* — stock moving to it is an intra-GST transfer,
    not a customer sale — and correctly stays unmatched. The bare chain-name
    customer ('NATHAN MEDICALS') is NMA, matched by similarity like the rest."""
    from difflib import SequenceMatcher

    nmw_store_id = get_nmw_store_id(tenant_id)
    if not nmw_store_id:
        return {"matched": 0, "assignments": [], "reason": "warehouse store (NMW) not found"}

    conn = get_connection()
    cursor = conn.cursor()
    try:
        _ensure_schema(cursor)
        customers = _nmw_customers(cursor, tenant_id, nmw_store_id)
        cursor.execute(
            "SELECT CAST(store_id AS VARCHAR(50)), store_code, store_name FROM dbo.stores "
            "WHERE tenant_id = ? AND store_id <> ?",
            (tenant_id, nmw_store_id),
        )
        stores = [{"store_id": r[0], "store_code": r[1], "store_name": r[2] or ""} for r in cursor.fetchall()]

        # Score every store×customer pair, then assign greedily (highest first),
        # never reusing a store or a customer code.
        pairs = []
        for store in stores:
            s_norm = _normalize_name(store["store_name"])
            for cust in customers:
                score = SequenceMatcher(None, s_norm, _normalize_name(cust["name"])).ratio()
                pairs.append((score, store, cust))
        pairs.sort(key=lambda p: p[0], reverse=True)

        used_stores, used_codes, assignments = set(), set(), []
        for score, store, cust in pairs:
            if store["store_id"] in used_stores or cust["code"] in used_codes:
                continue
            if score < threshold:
                continue
            used_stores.add(store["store_id"])
            used_codes.add(cust["code"])
            assignments.append({
                "store_id": store["store_id"],
                "store_code": store["store_code"],
                "store_name": store["store_name"],
                "customer_code": cust["code"],
                "customer_name": cust["name"],
                "score": round(score, 3),
            })

        if apply_changes:
            for a in assignments:
                cursor.execute(
                    "UPDATE dbo.stores SET ho_cust_code = ? WHERE tenant_id = ? AND store_id = ?",
                    (a["customer_code"], tenant_id, a["store_id"]),
                )
            conn.commit()

        unmatched = [s["store_code"] for s in stores if s["store_id"] not in used_stores]
        return {"matched": len(assignments), "assignments": assignments, "unmatched": unmatched, "applied": apply_changes}
    finally:
        cursor.close()
        conn.close()


def import_cust_codes_from_legacy(tenant_id):
    """One-shot copy of legacy dbo.Stores.ho_cust_code into platform
    dbo.stores.ho_cust_code, matched by store name. Mirrors the Ho_code import
    path (procurement.distribution_service.import_legacy_supplier_map). Skips
    silently if the legacy column has not been added yet."""
    from modules.legacy_order import database

    legacy_map = {}
    with database.get_central_connection() as legacy_conn:
        cur = legacy_conn.cursor()
        # Guard: the legacy column may not exist yet on this store's DB.
        if not cur.execute("SELECT COL_LENGTH('dbo.Stores', 'ho_cust_code')").fetchone()[0]:
            return {"imported": 0, "skipped": [], "reason": "legacy dbo.Stores.ho_cust_code not present"}
        for row in cur.execute("SELECT StoreName, ho_cust_code FROM Stores WHERE ho_cust_code IS NOT NULL"):
            name = (row.StoreName or "").strip()
            code = (row.ho_cust_code or "").strip()
            if name and code:
                legacy_map[name] = code

    imported, skipped = [], []
    conn = get_connection()
    cursor = conn.cursor()
    try:
        _ensure_schema(cursor)
        for store_name, cust_code in legacy_map.items():
            cursor.execute(
                "UPDATE dbo.stores SET ho_cust_code = ? "
                "WHERE tenant_id = ? AND LTRIM(RTRIM(store_name)) = ?",
                (cust_code, tenant_id, store_name),
            )
            (imported if cursor.rowcount else skipped).append(store_name)
        conn.commit()
        return {"imported": len(imported), "skipped": skipped}
    finally:
        cursor.close()
        conn.close()


def approve(tenant_id, nmw_store_id, bills, status, approved_by, remarks):
    """Upsert approval rows for (bill_date, bnumber) pairs. Returns count."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        _ensure_schema(cursor)
        affected = 0
        for bill in bills:
            cursor.execute(
                """
                MERGE dbo.nmw_sales_dispatch_approval AS target
                USING (SELECT ? AS tenant_id, ? AS source_store_id,
                              CAST(? AS DATETIME) AS bill_date, ? AS bnumber) AS src
                    ON  target.tenant_id = src.tenant_id
                    AND target.source_store_id = src.source_store_id
                    AND target.bill_date = src.bill_date
                    AND target.bnumber = src.bnumber
                WHEN MATCHED THEN UPDATE SET
                    status = ?, approved_by = ?, approved_at = GETDATE(), remarks = ?
                WHEN NOT MATCHED THEN INSERT
                    (tenant_id, source_store_id, bill_date, bnumber, status, approved_by, approved_at, remarks)
                    VALUES (src.tenant_id, src.source_store_id, src.bill_date, src.bnumber, ?, ?, GETDATE(), ?);
                """,
                (
                    tenant_id, nmw_store_id, bill.bill_date, bill.bill_no,
                    status, approved_by, remarks,
                    status, approved_by, remarks,
                ),
            )
            affected += 1
        conn.commit()
        return affected
    finally:
        cursor.close()
        conn.close()
