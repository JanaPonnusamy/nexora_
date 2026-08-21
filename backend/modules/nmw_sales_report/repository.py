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

        -- Separate routing code for intra-GST TO (stock-transfer) bills, whose
        -- CustomerCode is a Store-master code, not a Customer code (the same
        -- numeric value means different stores in the two series).
        IF COL_LENGTH('dbo.stores', 'ho_transfer_code') IS NULL
            ALTER TABLE dbo.stores ADD ho_transfer_code varchar(50) NULL;

        IF COL_LENGTH('sync.SaleInformation', 'IssuedDate') IS NULL
            ALTER TABLE sync.SaleInformation ADD IssuedDate datetime NULL;

        IF COL_LENGTH('sync.SaleInformation', 'SeriesName') IS NULL
            ALTER TABLE sync.SaleInformation ADD SeriesName varchar(20) NULL;

        -- Cancellation signal: a bill is cancelled when Transactionvalidity <> 0
        -- (mirrors the line-level flag already used on ProductSaleInformation)
        -- or Cancelleddate is set.
        IF COL_LENGTH('sync.SaleInformation', 'Transactionvalidity') IS NULL
            ALTER TABLE sync.SaleInformation ADD Transactionvalidity int NULL;

        IF COL_LENGTH('sync.SaleInformation', 'Cancelleddate') IS NULL
            ALTER TABLE sync.SaleInformation ADD Cancelleddate datetime NULL;

        -- Select these for future syncs (derive sync_table_id from an existing
        -- SaleInformation mapping row; no-op if already present or if
        -- SaleInformation isn't configured on this HO yet).
        IF EXISTS (SELECT 1 FROM sync.sync_column_mapping WHERE table_name = 'SaleInformation')
        INSERT INTO sync.sync_column_mapping
            (mapping_id, sync_table_id, table_name, column_name, data_type,
             is_selected, is_pk, is_hash, is_watermark, column_order, created_at)
        SELECT NEWID(), t.sync_table_id, 'SaleInformation', c.column_name, c.data_type,
               1, 0, 0, 0, t.next_order + c.ord, GETDATE()
        FROM (SELECT MAX(sync_table_id) AS sync_table_id, ISNULL(MAX(column_order), 0) AS next_order
              FROM sync.sync_column_mapping WHERE table_name = 'SaleInformation') t
        CROSS JOIN (VALUES
            ('IssuedDate', 'datetime', 1), ('SeriesName', 'varchar', 2),
            ('Transactionvalidity', 'int', 3), ('Cancelleddate', 'datetime', 4)
        ) AS c(column_name, data_type, ord)
        WHERE NOT EXISTS (
            SELECT 1 FROM sync.sync_column_mapping m
            WHERE m.table_name = 'SaleInformation' AND m.column_name = c.column_name);

        -- Packing description for the item-export sheet (SubLocation is
        -- already synced/used by stock_check_report; PackageInformation is not).
        IF COL_LENGTH('sync.Products', 'PackageInformation') IS NULL
            ALTER TABLE sync.Products ADD PackageInformation varchar(200) NULL;

        IF EXISTS (SELECT 1 FROM sync.sync_column_mapping WHERE table_name = 'Products')
           AND NOT EXISTS (
               SELECT 1 FROM sync.sync_column_mapping
               WHERE table_name = 'Products' AND column_name = 'PackageInformation')
        INSERT INTO sync.sync_column_mapping
            (mapping_id, sync_table_id, table_name, column_name, data_type,
             is_selected, is_pk, is_hash, is_watermark, column_order, created_at)
        SELECT NEWID(), MAX(sync_table_id), 'Products', 'PackageInformation', 'varchar',
               1, 0, 0, 0, ISNULL(MAX(column_order), 0) + 1, GETDATE()
        FROM sync.sync_column_mapping
        WHERE table_name = 'Products';
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
        # Series decides how CustomerCode is interpreted: a 'TO' stock-transfer
        # bill's CustomerCode is a Store-master code (routed via ho_transfer_code);
        # any other series is a Customer code (routed via ho_cust_code). Same
        # numeric value can point at different stores across the two, so they must
        # not be mixed. SeriesName may lag behind a sync, so fall back to the
        # 'TO' prefix on BNumber which is always present.
        #
        # Visibility is gated on APPROVAL (is_shown), not IssuedDate: the despatch
        # date only syncs for rows inside SaleInformation's rolling window, so
        # historical bills would never surface. IssuedDate is kept as an info
        # column; the super admin's approval is the show/hide switch.
        where = ["1 = 1"]
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
            ;WITH src AS (
                SELECT si.*,
                    CASE WHEN LTRIM(RTRIM(ISNULL(si.SeriesName, ''))) = 'TO'
                              OR si.BNumber LIKE 'TO%' THEN 1 ELSE 0 END AS is_transfer
                FROM sync.SaleInformation si
                WHERE si.tenant_id = ? AND si.store_id = ?
            )
            SELECT
                si.BNumber                         AS bill_no,
                si.BillNumber                      AS bill_number,
                CAST(si.BillDate AS DATE)          AS bill_date,
                si.Billtime                        AS bill_time,
                si.IssuedDate                      AS issued_date,
                ISNULL(si.BillAmount, 0)           AS bill_amount,
                CAST(si.CustomerCode AS NVARCHAR(50)) AS customer_code,
                si.CustomerName                    AS customer_name,
                si.is_transfer                     AS is_transfer,
                CASE WHEN si.is_transfer = 1 THEN 'Transfer' ELSE 'Sale' END AS bill_type,
                CASE WHEN ISNULL(si.Transactionvalidity, 0) <> 0
                       OR si.Cancelleddate IS NOT NULL THEN 1 ELSE 0 END AS is_cancelled,
                CAST(dst.store_id AS VARCHAR(50))  AS dest_store_id,
                dst.store_code                     AS dest_store_code,
                dst.store_name                     AS dest_store_name,
                ISNULL(ap.status, 'pending')       AS status,
                CASE WHEN ap.status = 'approved' THEN 1 ELSE 0 END AS is_shown,
                ap.approved_by                     AS approved_by,
                ap.approved_at                     AS approved_at
            FROM src si
            INNER JOIN dbo.stores dst
                ON dst.tenant_id = si.tenant_id
               AND (
                   (si.is_transfer = 1
                    AND NULLIF(LTRIM(RTRIM(dst.ho_transfer_code)), '') = LTRIM(RTRIM(si.CustomerCode)))
                OR (si.is_transfer = 0
                    AND NULLIF(LTRIM(RTRIM(dst.ho_cust_code)), '') = LTRIM(RTRIM(si.CustomerCode)))
               )
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
        _ensure_schema(cursor)
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
                -- RATE column shows PTR (PurchasePrice = price-to-retailer), the
                -- store's purchase price, NOT psi.Rate (the net/after-discount
                -- charged figure). With the Dis% column below, the row reads
                -- PTR - Dis% = Amount, e.g. 471.60 - 10% = 424.44.
                ISNULL(psi.PurchasePrice, 0)           AS rate,
                -- Dis% derived from PTR (PurchasePrice) vs the actual charged
                -- Rate, NOT the raw DiscountPercentage column -- that field is
                -- always 0 on NMW dispatch bills (verified against live data).
                -- (PTR-Rate)/PTR*100 reproduces NMW's real discount tiers
                -- (10%, 12%, 14.5%) cleanly against a sample bill.
                ROUND(
                    CASE WHEN ISNULL(psi.PurchasePrice, 0) = 0 THEN 0
                         ELSE (psi.PurchasePrice - ISNULL(psi.Rate, 0)) / psi.PurchasePrice * 100
                    END, 2
                ) AS discount_percentage,
                ISNULL(psi.Transactionamount, 0)       AS amount,
                ISNULL(p.PackageInformation, '')       AS packing,
                ISNULL(p.SubLocation, '')               AS sublocation
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


_CODE_COLUMN = {"cust": "ho_cust_code", "transfer": "ho_transfer_code"}


def set_store_cust_code(tenant_id, store_id, cust_code, code_type="cust"):
    """Manually set a store's NMW code on the platform stores row. code_type
    'cust' -> ho_cust_code (sales bills), 'transfer' -> ho_transfer_code (TO)."""
    column = _CODE_COLUMN.get(code_type, "ho_cust_code")
    conn = get_connection()
    cursor = conn.cursor()
    try:
        _ensure_schema(cursor)
        cursor.execute(
            f"UPDATE dbo.stores SET {column} = ? WHERE tenant_id = ? AND store_id = ?",
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
            "SELECT CAST(store_id AS VARCHAR(50)) AS store_id, store_code, store_name, "
            "ho_cust_code, ho_transfer_code "
            "FROM dbo.stores WHERE tenant_id = ? ORDER BY store_code",
            (tenant_id,),
        )
        return _rows(cursor)
    finally:
        cursor.close()
        conn.close()


def _nmw_customers(cursor, tenant_id, nmw_store_id, transfer=None):
    """Distinct (CustomerCode, CustomerName) seen on NMW's bills — the de-facto
    customer master, since NMW's stores appear as its bill customers.

    transfer: None = all bills; True = only 'TO' stock-transfer bills (CustomerCode
    is a Store-master code); False = only sales bills (CustomerCode is a Customer
    code). The two are disjoint code spaces, matched into separate columns."""
    series = ""
    if transfer is True:
        series = "AND (LTRIM(RTRIM(ISNULL(SeriesName, ''))) = 'TO' OR BNumber LIKE 'TO%')"
    elif transfer is False:
        series = "AND NOT (LTRIM(RTRIM(ISNULL(SeriesName, ''))) = 'TO' OR BNumber LIKE 'TO%')"
    cursor.execute(
        f"""
        SELECT CAST(CustomerCode AS NVARCHAR(50)) AS code, MAX(CustomerName) AS name
        FROM sync.SaleInformation
        WHERE tenant_id = ? AND store_id = ?
          AND CustomerCode IS NOT NULL AND LTRIM(RTRIM(CustomerCode)) <> ''
          {series}
        GROUP BY CAST(CustomerCode AS NVARCHAR(50))
        """,
        (tenant_id, nmw_store_id),
    )
    return [{"code": (r[0] or "").strip(), "name": (r[1] or "").strip()} for r in cursor.fetchall()]


def _normalize_name(value):
    return "".join(ch for ch in (value or "").upper() if ch.isalnum())


def _greedy_match(stores, customers, threshold):
    """Greedy global assignment of stores to customers by name similarity, best
    score first, never reusing a store or a customer code."""
    from difflib import SequenceMatcher

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
    return assignments, used_stores


def auto_match_cust_codes(tenant_id, threshold=0.86, apply_changes=True):
    """Match stores to NMW customers by name and set the routing codes. Runs
    twice over disjoint code spaces: sales bills -> ho_cust_code, and 'TO'
    stock-transfer bills -> ho_transfer_code. Returns proposed/applied rows so
    the admin can review/correct ambiguous matches in the panel.

    NMW and NMC are one GST entity (NMW is the C-branch warehouse): NMC is not an
    NMW sales *customer* (bare 'NATHAN MEDICALS' is NMA), it receives stock via
    intra-GST 'TO' transfers, so it is matched only on the transfer side."""
    nmw_store_id = get_nmw_store_id(tenant_id)
    if not nmw_store_id:
        return {"matched": 0, "assignments": [], "reason": "warehouse store (NMW) not found"}

    conn = get_connection()
    cursor = conn.cursor()
    try:
        _ensure_schema(cursor)
        cursor.execute(
            "SELECT CAST(store_id AS VARCHAR(50)), store_code, store_name FROM dbo.stores "
            "WHERE tenant_id = ? AND store_id <> ?",
            (tenant_id, nmw_store_id),
        )
        stores = [{"store_id": r[0], "store_code": r[1], "store_name": r[2] or ""} for r in cursor.fetchall()]

        sales_assign, sales_used = _greedy_match(stores, _nmw_customers(cursor, tenant_id, nmw_store_id, transfer=False), threshold)
        transfer_assign, transfer_used = _greedy_match(stores, _nmw_customers(cursor, tenant_id, nmw_store_id, transfer=True), threshold)
        for a in sales_assign:
            a["code_type"] = "cust"
        for a in transfer_assign:
            a["code_type"] = "transfer"

        if apply_changes:
            for a in sales_assign:
                cursor.execute(
                    "UPDATE dbo.stores SET ho_cust_code = ? WHERE tenant_id = ? AND store_id = ?",
                    (a["customer_code"], tenant_id, a["store_id"]),
                )
            for a in transfer_assign:
                cursor.execute(
                    "UPDATE dbo.stores SET ho_transfer_code = ? WHERE tenant_id = ? AND store_id = ?",
                    (a["customer_code"], tenant_id, a["store_id"]),
                )
            conn.commit()

        matched_ids = sales_used | transfer_used
        unmatched = [s["store_code"] for s in stores if s["store_id"] not in matched_ids]
        return {
            "matched": len(sales_assign) + len(transfer_assign),
            "assignments": sales_assign + transfer_assign,
            "unmatched": unmatched,
            "applied": apply_changes,
        }
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


def approve_before(tenant_id, nmw_store_id, cutoff_date, approved_by):
    """Bulk-approve every routable NMW bill with BillDate < cutoff_date (one-shot
    for historical bills). Only routable bills (matching a store via ho_cust_code
    or ho_transfer_code, series-aware) are inserted; already-approved rows are
    skipped. Returns the number newly approved."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        _ensure_schema(cursor)
        cursor.execute(
            """
            INSERT INTO dbo.nmw_sales_dispatch_approval
                (tenant_id, source_store_id, bill_date, bnumber, status, approved_by, approved_at)
            SELECT DISTINCT si.tenant_id, si.store_id, si.BillDate, si.BNumber, 'approved', ?, GETDATE()
            FROM sync.SaleInformation si
            WHERE si.tenant_id = ? AND si.store_id = ?
              AND CAST(si.BillDate AS DATE) < CAST(? AS DATE)
              AND EXISTS (
                  SELECT 1 FROM dbo.stores dst
                  WHERE dst.tenant_id = si.tenant_id
                    AND (
                        ((LTRIM(RTRIM(ISNULL(si.SeriesName, ''))) = 'TO' OR si.BNumber LIKE 'TO%')
                         AND NULLIF(LTRIM(RTRIM(dst.ho_transfer_code)), '') = LTRIM(RTRIM(si.CustomerCode)))
                     OR (NOT (LTRIM(RTRIM(ISNULL(si.SeriesName, ''))) = 'TO' OR si.BNumber LIKE 'TO%')
                         AND NULLIF(LTRIM(RTRIM(dst.ho_cust_code)), '') = LTRIM(RTRIM(si.CustomerCode)))
                    )
              )
              AND NOT EXISTS (
                  SELECT 1 FROM dbo.nmw_sales_dispatch_approval a
                  WHERE a.tenant_id = si.tenant_id AND a.source_store_id = si.store_id
                    AND a.bill_date = si.BillDate AND a.bnumber = si.BNumber
              )
            """,
            (approved_by, tenant_id, nmw_store_id, cutoff_date),
        )
        count = cursor.rowcount
        conn.commit()
        return count
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
