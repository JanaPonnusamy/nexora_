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

import re
from datetime import date, datetime, timedelta

from config.database import get_connection


def _normalize_name(name):
    """Collapse a product name to bare alnum-uppercase so cosmetic differences
    (spacing, brackets, punctuation) don't defeat a same-item comparison --
    e.g. NMW's 'COTTON 25GM [BOT CARE]' and a store's 'COTTON 25GM[BOTCARE]'
    both normalize to 'COTTON25GMBOTCARE'. Used as a fallback when NMW and a
    store disagree on ProductCode for the same physical item (verified live;
    see nmw-purchase-entry-matching memory)."""
    return re.sub(r"[^A-Z0-9]", "", (name or "").upper())

WAREHOUSE_STORE_CODE = "NMW"

# A bill with no matching PurchaseTrans receipt yet reads as 'pending' while it
# is younger than this many days (store staff may simply not have keyed the
# GRN in yet) and 'not_found' once older (see get_purchase_status_map).
PURCHASE_GRACE_DAYS = 3

# How many days after the bill date to look for a matching store-side receipt.
# Generous on purpose: staff key GRNs in late sometimes, and a wide window
# costs nothing extra once the covering index below is in place.
PURCHASE_MATCH_WINDOW_DAYS = 30

_schema_ready = False

# Per-store local code for "goods received from NMW", read from
# procurement.store_supplier_map (mirrors the legacy dbo.Stores.Ho_code
# column -- see that module's 0022_store_supplier_map.sql). A code prefixed
# 'ST_' means the store receives NMW's stock as an internal stock TRANSFER
# (InvoiceSeries='TI'), not a normal purchase invoice ('IV'); the prefix
# exists in the legacy data specifically because the bare numeric code can
# collide with an unrelated real supplier at that store (verified live: NMC's
# code '2' is also a real supplier, PENTACARE ENTERPRISES -- InvoiceSeries is
# what actually disambiguates a transfer receipt from a real purchase there).
_SMAP_SELECT = """
    SELECT store_id,
           CASE WHEN local_supplier_code LIKE 'ST[_]%'
                THEN LTRIM(RTRIM(SUBSTRING(local_supplier_code, 4, 100)))
                ELSE LTRIM(RTRIM(local_supplier_code)) END AS raw_code,
           CASE WHEN local_supplier_code LIKE 'ST[_]%' THEN 'TI' ELSE 'IV' END AS series
    FROM procurement.store_supplier_map
    WHERE tenant_id = ? AND source_store_code = 'NMW'
"""


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

        -- Header amount breakdown so the bill-detail footer reconciles the line
        -- items to the header total: GrossAmount = sum of line amounts (pre-tax);
        -- CGSTAmount = one half of the GST (SGST equals it intra-state); the
        -- header BillAmount = GrossAmount + 2*CGSTAmount, rounded.
        IF COL_LENGTH('sync.SaleInformation', 'GrossAmount') IS NULL
            ALTER TABLE sync.SaleInformation ADD GrossAmount decimal(18,4) NULL;

        IF COL_LENGTH('sync.SaleInformation', 'CGSTAmount') IS NULL
            ALTER TABLE sync.SaleInformation ADD CGSTAmount decimal(18,4) NULL;

        IF COL_LENGTH('sync.SaleInformation', 'TaxAmount') IS NULL
            ALTER TABLE sync.SaleInformation ADD TaxAmount decimal(18,4) NULL;

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
            ('Transactionvalidity', 'int', 3), ('Cancelleddate', 'datetime', 4),
            ('GrossAmount', 'decimal', 5), ('CGSTAmount', 'decimal', 6),
            ('TaxAmount', 'decimal', 7)
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

        -- Purchase-entry status lookup (Task: PURCHASE ENTRY column) filters
        -- PurchaseTrans by (tenant, store, SupplierCode, InvoiceSeries,
        -- ProductCode) for every bill line on the report -- the existing
        -- IX_PurchaseTrans_Supplier index doesn't cover InvoiceSeries/ProductCode
        -- together, so this is a dedicated covering index for that access path.
        IF NOT EXISTS (
            SELECT 1 FROM sys.indexes
            WHERE object_id = OBJECT_ID('sync.PurchaseTrans') AND name = 'IX_PurchaseTrans_Supplier_Series_Product'
        )
            CREATE NONCLUSTERED INDEX IX_PurchaseTrans_Supplier_Series_Product
                ON sync.PurchaseTrans (tenant_id, store_id, SupplierCode, InvoiceSeries, ProductCode)
                INCLUDE (stockreceived, grndate, Grnnumber);

        -- Bill-number match (see _SMAP_SELECT / get_purchase_status_map docstring):
        -- for a normal purchase-invoice store, staff key NMW's own bill number
        -- into Batches.InvoiceNumber when they GRN it, so that is a far more
        -- reliable completion signal than per-product code matching (NMW and
        -- each store keep independent product masters -- verified live: the
        -- same physical item can have two different ProductCodes). Covers the
        -- (tenant, store, SupplierCode, GrnDate) scan this lookup does.
        IF NOT EXISTS (
            SELECT 1 FROM sys.indexes
            WHERE object_id = OBJECT_ID('sync.Batches') AND name = 'IX_Batches_Supplier_GrnDate'
        )
            CREATE NONCLUSTERED INDEX IX_Batches_Supplier_GrnDate
                ON sync.Batches (tenant_id, store_id, SupplierCode, GrnDate)
                INCLUDE (InvoiceNumber, GrnNumber);
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
            -- on Bnumber directly. Duplicate/orphan lines from *modified* bills
            -- (the source moves superseded rows to MProductSaleInformation but our
            -- insert-only sync never removed the mirror copy) are moved out of this
            -- live mirror into sync.MProductSaleInformation by
            -- modules.nmw_sales_report.reconcile (auto-run on report load), NOT
            -- dedup'd here -- so genuinely repeated product+batch lines survive.
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


def get_bill_summary(tenant_id, nmw_store_id, bill_no, bill_date):
    """Totals footer for a bill: the line sub-total (identical to the sum of the
    items get_bill_items returns) plus the GST and round-off from the header, so
    Sub-total + CGST + SGST + Round-off = header BillAmount exactly.

    CGST is taken from the header CGSTAmount (one half of the GST); SGST equals it
    for intra-state bills. Round-off absorbs any residual so the total always ties
    to BillAmount even if a column has not been back-filled yet."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        _ensure_schema(cursor)
        cursor.execute(
            """
            ;WITH bill_match AS (
                SELECT TOP (1)
                    si.tenant_id, si.store_id, si.BNumber, si.BillNumber,
                    CAST(si.BillDate AS DATE) AS BillDate,
                    ISNULL(si.BillAmount, 0) AS bill_amount,
                    ISNULL(si.CGSTAmount, 0) AS cgst,
                    CASE WHEN LTRIM(RTRIM(ISNULL(si.SeriesName, ''))) = 'TO'
                              OR si.BNumber LIKE 'TO%' THEN 1 ELSE 0 END AS is_transfer
                FROM sync.SaleInformation si
                WHERE si.tenant_id = ?
                  AND si.store_id = ?
                  AND si.BNumber = ?
                  AND (? IS NULL OR CAST(si.BillDate AS DATE) = CAST(? AS DATE))
                ORDER BY si.BillDate DESC, si.BillNumber DESC
            )
            SELECT
                bm.bill_amount,
                bm.cgst,
                bm.is_transfer,
                ISNULL((
                    SELECT SUM(ISNULL(psi.Transactionamount, 0))
                    FROM sync.ProductSaleInformation psi
                    WHERE psi.tenant_id = bm.tenant_id
                      AND psi.store_id = bm.store_id
                      AND psi.BillNumber = bm.BillNumber
                      AND psi.Bnumber = bm.BNumber
                      AND CAST(psi.TransactionDate AS DATE) = bm.BillDate
                      AND ISNULL(psi.TransactionValidity, 0) = 0
                ), 0) AS subtotal
            FROM bill_match bm
            """,
            (tenant_id, nmw_store_id, bill_no, bill_date, bill_date),
        )
        row = cursor.fetchone()
        if not row:
            return None
        bill_amount = float(row[0] or 0)
        cgst = float(row[1] or 0)
        is_transfer = int(row[2] or 0)
        subtotal = float(row[3] or 0)
        sgst = cgst
        tax_total = cgst + sgst
        roundoff = round(bill_amount - subtotal - tax_total, 2)
        return {
            "subtotal": round(subtotal, 2),
            "cgst": round(cgst, 2),
            "sgst": round(sgst, 2),
            "tax_total": round(tax_total, 2),
            "roundoff": roundoff,
            "bill_amount": round(bill_amount, 2),
            "is_transfer": is_transfer,
        }
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


def _classify_purchase_status(total_products, matched_products, unmapped, bill_date, grace_days=PURCHASE_GRACE_DAYS):
    """completed: every product on the bill has a covering receipt.
    pending: some/none matched yet, but still within the grace window (or a
    partial match exists -- staff may still be entering the rest).
    not_found: no receipt at all, past the grace window, or the destination
    store has no HO supplier-code mapping configured (nothing to check)."""
    if unmapped or total_products == 0:
        return "not_found"
    if matched_products >= total_products:
        return "completed"
    if matched_products > 0:
        return "pending"
    try:
        bd = bill_date if isinstance(bill_date, date) else datetime.strptime(str(bill_date)[:10], "%Y-%m-%d").date()
        age_days = (date.today() - bd).days
    except (ValueError, TypeError):
        age_days = 0
    return "pending" if age_days <= grace_days else "not_found"


def _name_fallback_completes(cursor, tenant_id, nmw_store_id, dest_store_id, raw_code, series, bnumber, bill_date):
    """True if every product on this bill that missed the ProductCode match
    can be accounted for by NAME instead (see _normalize_name). Two small,
    tightly-scoped queries -- cheap enough to run per-bill for the small
    residual set get_purchase_status_map calls this on."""
    cursor.execute(
        """
        SELECT psi.ProductCode, MAX(p.ProductName) AS product_name, SUM(psi.Quantity) AS req_qty
        FROM sync.ProductSaleInformation psi
        LEFT JOIN sync.Products p
            ON p.tenant_id = psi.tenant_id AND p.store_id = psi.store_id AND p.ProductCode = psi.ProductCode
        WHERE psi.tenant_id = ? AND psi.store_id = ? AND psi.Bnumber = ?
          AND CAST(psi.TransactionDate AS DATE) = ? AND ISNULL(psi.TransactionValidity, 0) = 0
        GROUP BY psi.ProductCode
        """,
        (tenant_id, nmw_store_id, bnumber, bill_date),
    )
    products = cursor.fetchall()
    if not products:
        return False
    codes = [p[0] for p in products]
    cph = ", ".join("?" for _ in codes)
    cursor.execute(
        f"""
        SELECT ProductCode, SUM(stockreceived)
        FROM sync.PurchaseTrans
        WHERE tenant_id = ? AND store_id = ? AND SupplierCode = ? AND LTRIM(RTRIM(InvoiceSeries)) = ?
          AND ProductCode IN ({cph})
          AND CAST(grndate AS DATE) BETWEEN ? AND DATEADD(DAY, {PURCHASE_MATCH_WINDOW_DAYS}, ?)
        GROUP BY ProductCode
        """,
        (tenant_id, dest_store_id, raw_code, series, *codes, bill_date, bill_date),
    )
    got_by_code = {code: float(qty or 0) for code, qty in cursor.fetchall()}

    still_short = [(code, name, float(req or 0)) for code, name, req in products
                   if got_by_code.get(code, 0.0) < float(req or 0) - 0.01]
    if not still_short:
        return True

    cursor.execute(
        f"""
        SELECT p.ProductName, pt.stockreceived
        FROM sync.PurchaseTrans pt
        LEFT JOIN sync.Products p
            ON p.tenant_id = pt.tenant_id AND p.store_id = pt.store_id AND p.ProductCode = pt.ProductCode
        WHERE pt.tenant_id = ? AND pt.store_id = ? AND pt.SupplierCode = ? AND LTRIM(RTRIM(pt.InvoiceSeries)) = ?
          AND CAST(pt.grndate AS DATE) BETWEEN ? AND DATEADD(DAY, {PURCHASE_MATCH_WINDOW_DAYS}, ?)
        """,
        (tenant_id, dest_store_id, raw_code, series, bill_date, bill_date),
    )
    name_qty = {}
    for pname, recv in cursor.fetchall():
        key = _normalize_name(pname)
        if key:
            name_qty[key] = name_qty.get(key, 0.0) + float(recv or 0)

    return all(name_qty.get(_normalize_name(name), 0.0) >= req - 0.01 for _code, name, req in still_short)


def get_purchase_status_map(tenant_id, nmw_store_id, dest_store_ids, date_from, date_to):
    """Batched purchase-entry classification for every bill in range -- ONE
    query for the whole report, not one per bill (see module docstring below
    for why there is no bill-number key in sync.PurchaseTrans to join on).

    Primary signal (IV-series/normal-purchase stores only): staff key NMW's
    own bill number into sync.Batches.InvoiceNumber when they GRN it (verified
    live -- e.g. bill 26-27D2628 -> InvoiceNumber 'D2628'). That is scoped by
    (store, SupplierCode) and a match makes the bill 'completed' outright,
    regardless of per-product code agreement -- NMW and each store keep
    independent product masters, so a per-product code match can under-report
    (verified: GLIPTAGREAT M 500MG TAB is ProductCode 5881728 at NMW but
    5880916 at store NMA for the same physical item).

    Fallback signal (used when no bill-number match, and always for
    ST_-prefixed/internal-transfer stores, which record their own transfer-doc
    number instead of NMW's bill number): for each distinct product on the
    bill, the destination store must show at least that quantity received from
    NMW's resolved local supplier code (procurement.store_supplier_map, i.e.
    the legacy Ho_code) within PURCHASE_MATCH_WINDOW_DAYS after the bill date.
    'completed' requires every product to clear that bar; see
    _classify_purchase_status for the pending/not_found split.

    Returns {(bill_no, bill_date_iso): {"purchase_status", "matched_products",
    "total_products", "entry_no"}}. entry_no is the store's *completing* GRN
    number -- the bill-number-matched GRN when available, else the latest GRN
    among the bill's per-product-matched lines.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        _ensure_schema(cursor)
        where = ["1 = 1"]
        resolved_params = []
        if dest_store_ids is not None:
            if not dest_store_ids:
                return {}
            placeholders = ", ".join("?" for _ in dest_store_ids)
            where.append(f"CAST(dst.store_id AS VARCHAR(50)) IN ({placeholders})")
            resolved_params.extend(dest_store_ids)
        if date_from:
            where.append("CAST(src.BillDate AS DATE) >= CAST(? AS DATE)")
            resolved_params.append(date_from)
        if date_to:
            where.append("CAST(src.BillDate AS DATE) <= CAST(? AS DATE)")
            resolved_params.append(date_to)

        params = (
            [tenant_id, nmw_store_id]
            + resolved_params
            + [tenant_id, nmw_store_id]
            + [tenant_id]
            + [tenant_id]
        )

        cursor.execute(
            f"""
            ;WITH src AS (
                SELECT si.tenant_id, si.store_id, si.BNumber, si.BillNumber,
                       CAST(si.BillDate AS DATE) AS BillDate, si.CustomerCode,
                       CASE WHEN LTRIM(RTRIM(ISNULL(si.SeriesName, ''))) = 'TO'
                                 OR si.BNumber LIKE 'TO%' THEN 1 ELSE 0 END AS is_transfer
                FROM sync.SaleInformation si
                WHERE si.tenant_id = ? AND si.store_id = ?
            ),
            resolved AS (
                SELECT src.BNumber, src.BillNumber, src.BillDate,
                       CAST(dst.store_id AS VARCHAR(50)) AS dest_store_id
                FROM src
                INNER JOIN dbo.stores dst
                    ON dst.tenant_id = src.tenant_id
                   AND (
                       (src.is_transfer = 1 AND NULLIF(LTRIM(RTRIM(dst.ho_transfer_code)), '') = LTRIM(RTRIM(src.CustomerCode)))
                    OR (src.is_transfer = 0 AND NULLIF(LTRIM(RTRIM(dst.ho_cust_code)), '') = LTRIM(RTRIM(src.CustomerCode)))
                   )
                WHERE {' AND '.join(where)}
            ),
            bill_products AS (
                SELECT r.BNumber, r.BillDate, r.dest_store_id, psi.ProductCode,
                       SUM(psi.Quantity) AS req_qty
                FROM resolved r
                JOIN sync.ProductSaleInformation psi
                    ON psi.tenant_id = ? AND psi.store_id = ?
                   AND psi.BillNumber = r.BillNumber AND psi.Bnumber = r.BNumber
                   AND CAST(psi.TransactionDate AS DATE) = r.BillDate
                WHERE ISNULL(psi.TransactionValidity, 0) = 0
                GROUP BY r.BNumber, r.BillDate, r.dest_store_id, psi.ProductCode
            ),
            smap AS (
                {_SMAP_SELECT}
            )
            SELECT bp.BNumber, bp.BillDate, bp.dest_store_id,
                   MAX(sm.raw_code) AS raw_code, MAX(sm.series) AS series,
                   COUNT(*) AS total_products,
                   SUM(CASE WHEN sm.store_id IS NOT NULL AND ISNULL(got.got_qty, 0) >= bp.req_qty - 0.01
                            THEN 1 ELSE 0 END) AS matched_products,
                   MAX(CASE WHEN sm.store_id IS NULL THEN 1 ELSE 0 END) AS unmapped,
                   -- Completing GRN: the latest GRN among the products that DID
                   -- match (one clean number for the list column) -- overridden
                   -- in Python below when a bill-number match is found.
                   MAX(CASE WHEN sm.store_id IS NOT NULL AND ISNULL(got.got_qty, 0) >= bp.req_qty - 0.01
                            THEN got.max_grn END) AS completing_grn
            FROM bill_products bp
            LEFT JOIN smap sm ON sm.store_id = bp.dest_store_id
            OUTER APPLY (
                SELECT SUM(pt.stockreceived) AS got_qty, MAX(pt.Grnnumber) AS max_grn
                FROM sync.PurchaseTrans pt
                WHERE pt.tenant_id = ?
                  AND pt.store_id = bp.dest_store_id
                  AND sm.store_id IS NOT NULL
                  AND pt.SupplierCode = sm.raw_code
                  AND LTRIM(RTRIM(pt.InvoiceSeries)) = sm.series
                  AND pt.ProductCode = bp.ProductCode
                  AND CAST(pt.grndate AS DATE) BETWEEN bp.BillDate AND DATEADD(DAY, {PURCHASE_MATCH_WINDOW_DAYS}, bp.BillDate)
            ) got
            GROUP BY bp.BNumber, bp.BillDate, bp.dest_store_id
            """,
            tuple(params),
        )
        rows = cursor.fetchall()

        # Bill-number match (IV-series stores only): pull every candidate
        # (store, SupplierCode, InvoiceNumber, GrnNumber, GrnDate) ONE bulk read,
        # scoped by plain equality + a date-range (sargable -- uses
        # IX_Batches_Supplier_GrnDate), then do the "is this a suffix of the
        # bill number" test in Python. Doing that test as a per-row SQL LIKE
        # instead (LIKE '%' + column) is non-sargable and was ~160x slower on
        # a 6-week range (162s vs <1s) -- see nmw-purchase-entry-matching memory.
        iv_pairs = {(r[2], r[3]) for r in rows if r[4] == "IV" and r[2] and r[3]}
        invoice_lookup = {}
        if iv_pairs:
            bill_dates = [r[1] for r in rows if r[4] == "IV"]
            window_start = min(bill_dates)
            window_end = max(bill_dates) + timedelta(days=PURCHASE_MATCH_WINDOW_DAYS)
            store_ids = sorted({p[0] for p in iv_pairs})
            codes = sorted({p[1] for p in iv_pairs})
            sph = ", ".join("?" for _ in store_ids)
            cph = ", ".join("?" for _ in codes)
            cursor.execute(
                f"""
                SELECT store_id, SupplierCode, InvoiceNumber, GrnNumber, CAST(GrnDate AS DATE)
                FROM sync.Batches
                WHERE tenant_id = ? AND store_id IN ({sph}) AND SupplierCode IN ({cph})
                  AND GrnDate BETWEEN ? AND ? AND LEN(InvoiceNumber) >= 4
                """,
                (tenant_id, *store_ids, *codes, window_start, window_end),
            )
            for store_id, supplier_code, invoice_number, grn_number, grn_date in cursor.fetchall():
                invoice_lookup.setdefault((store_id, supplier_code), []).append(
                    (invoice_number, grn_number, grn_date)
                )

        out = {}
        for bnumber, bill_date, dest_store_id, raw_code, series, total_products, matched_products, unmapped, completing_grn in rows:
            bd_iso = bill_date.isoformat() if hasattr(bill_date, "isoformat") else str(bill_date)
            matched_products = int(matched_products or 0)
            invoice_grn = None
            if series == "IV" and dest_store_id and raw_code:
                window_end = bill_date + timedelta(days=PURCHASE_MATCH_WINDOW_DAYS)
                candidates = [
                    grn_number
                    for invoice_number, grn_number, grn_date in invoice_lookup.get((dest_store_id, raw_code), [])
                    if bnumber.endswith(invoice_number) and bill_date <= grn_date <= window_end
                ]
                if candidates:
                    invoice_grn = min(candidates)
            if invoice_grn is not None:
                matched_products = total_products
                completing_grn = invoice_grn
            status = _classify_purchase_status(total_products, matched_products, unmapped, bill_date)
            out[(bnumber, bd_iso)] = {
                "purchase_status": status,
                "matched_products": matched_products,
                "total_products": int(total_products or 0),
                "entry_no": str(int(completing_grn)) if completing_grn is not None else None,
            }

        # Name-fallback pass (small residual set only -- see
        # nmw-purchase-entry-matching memory): a bill can still read short on
        # ProductCode even though every item physically arrived, because NMW
        # and the store disagree on the code for that item. Re-checked here by
        # product NAME instead, one cheap per-bill lookup, for whatever the
        # passes above left short -- typically a few percent of the range, so
        # this stays fast even though it isn't batched into the main query.
        for bnumber, bill_date, dest_store_id, raw_code, series, total_products, matched_products, unmapped, completing_grn in rows:
            bd_iso = bill_date.isoformat() if hasattr(bill_date, "isoformat") else str(bill_date)
            entry = out.get((bnumber, bd_iso))
            if not entry or entry["purchase_status"] == "completed" or not dest_store_id or not raw_code:
                continue
            if _name_fallback_completes(cursor, tenant_id, nmw_store_id, dest_store_id, raw_code, series, bnumber, bill_date):
                entry["purchase_status"] = "completed"
                entry["matched_products"] = entry["total_products"]

        return out
    finally:
        cursor.close()
        conn.close()


def get_purchase_entry_detail(tenant_id, nmw_store_id, bill_no, bill_date):
    """Detailed purchase-entry lookup for ONE bill (used by the detail panel,
    called only when a bill is opened -- not part of the list/batch path).

    Unlike get_purchase_status_map this also resolves which specific
    PurchaseTrans GRN(s) contributed, so a bill whose products landed across
    several store GRNs shows all of them rather than picking one arbitrarily
    (see module note on why there is no single reference key to join on)."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        _ensure_schema(cursor)
        cursor.execute(
            """
            ;WITH bill_match AS (
                SELECT TOP (1) si.tenant_id, si.store_id, si.BNumber, si.BillNumber,
                       CAST(si.BillDate AS DATE) AS BillDate, si.CustomerCode,
                       CASE WHEN LTRIM(RTRIM(ISNULL(si.SeriesName, ''))) = 'TO'
                                 OR si.BNumber LIKE 'TO%' THEN 1 ELSE 0 END AS is_transfer
                FROM sync.SaleInformation si
                WHERE si.tenant_id = ? AND si.store_id = ? AND si.BNumber = ?
                  AND (? IS NULL OR CAST(si.BillDate AS DATE) = CAST(? AS DATE))
                ORDER BY si.BillDate DESC, si.BillNumber DESC
            )
            SELECT bm.BillNumber, bm.BNumber, bm.BillDate,
                   CAST(dst.store_id AS VARCHAR(50)) AS dest_store_id,
                   dst.store_code, dst.store_name
            FROM bill_match bm
            INNER JOIN dbo.stores dst
                ON dst.tenant_id = bm.tenant_id
               AND (
                   (bm.is_transfer = 1 AND NULLIF(LTRIM(RTRIM(dst.ho_transfer_code)), '') = LTRIM(RTRIM(bm.CustomerCode)))
                OR (bm.is_transfer = 0 AND NULLIF(LTRIM(RTRIM(dst.ho_cust_code)), '') = LTRIM(RTRIM(bm.CustomerCode)))
               )
            """,
            (tenant_id, nmw_store_id, bill_no, bill_date, bill_date),
        )
        row = cursor.fetchone()
        if not row:
            return {
                "purchase_status": "not_found", "matched_products": 0, "total_products": 0,
                "entry_no": None, "entry_date": None, "reason": "bill_not_routed_to_a_store",
            }
        billnumber, bnumber, bdate, dest_store_id, dest_store_code, dest_store_name = row

        cursor.execute(
            """
            SELECT psi.ProductCode,
                   ISNULL(MAX(p.ProductName), CAST(psi.ProductCode AS NVARCHAR(100))) AS product_name,
                   SUM(psi.Quantity) AS req_qty
            FROM sync.ProductSaleInformation psi
            LEFT JOIN sync.Products p
                ON p.tenant_id = psi.tenant_id AND p.store_id = psi.store_id AND p.ProductCode = psi.ProductCode
            WHERE psi.tenant_id = ? AND psi.store_id = ? AND psi.BillNumber = ? AND psi.Bnumber = ?
              AND CAST(psi.TransactionDate AS DATE) = ? AND ISNULL(psi.TransactionValidity, 0) = 0
            GROUP BY psi.ProductCode
            """,
            (tenant_id, nmw_store_id, billnumber, bnumber, bdate),
        )
        # (product_code, product_name, req_qty)
        products = [(r[0], r[1], float(r[2] or 0)) for r in cursor.fetchall()]
        name_by_product = {r[0]: r[1] for r in products}
        if not products:
            return {
                "purchase_status": "not_found", "matched_products": 0, "total_products": 0,
                "entry_no": None, "entry_date": None, "dest_store_id": dest_store_id,
                "dest_store_code": dest_store_code, "dest_store_name": dest_store_name,
                "reason": "no_line_items",
            }

        cursor.execute(
            "SELECT local_supplier_code FROM procurement.store_supplier_map "
            "WHERE tenant_id = ? AND store_id = ? AND source_store_code = 'NMW'",
            (tenant_id, dest_store_id),
        )
        smap_row = cursor.fetchone()
        if not smap_row or not (smap_row[0] or "").strip():
            return {
                "purchase_status": "not_found", "matched_products": 0, "total_products": len(products),
                "entry_no": None, "entry_date": None, "dest_store_id": dest_store_id,
                "dest_store_code": dest_store_code, "dest_store_name": dest_store_name,
                "reason": "store_not_mapped",
            }
        local_code = smap_row[0].strip()
        if local_code.upper().startswith("ST_"):
            raw_code, series = local_code[3:].strip(), "TI"
        else:
            raw_code, series = local_code, "IV"

        product_codes = [p[0] for p in products]
        placeholders = ", ".join("?" for _ in product_codes)
        cursor.execute(
            f"""
            SELECT ProductCode, Grnnumber, CAST(grndate AS DATE), stockreceived
            FROM sync.PurchaseTrans
            WHERE tenant_id = ? AND store_id = ? AND SupplierCode = ? AND LTRIM(RTRIM(InvoiceSeries)) = ?
              AND ProductCode IN ({placeholders})
              AND CAST(grndate AS DATE) BETWEEN ? AND DATEADD(DAY, {PURCHASE_MATCH_WINDOW_DAYS}, ?)
            ORDER BY grndate
            """,
            (tenant_id, dest_store_id, raw_code, series, *product_codes, bdate, bdate),
        )
        purchase_rows = cursor.fetchall()

        req_by_product = {code: req for code, _name, req in products}
        got_by_product = {}
        grns_seen = {}
        for product_code, grnnumber, grndate, stockreceived in purchase_rows:
            got_by_product[product_code] = got_by_product.get(product_code, 0.0) + float(stockreceived or 0)
            grns_seen[(grnnumber, grndate)] = True

        # Name-fallback pass: for products the code-based read above still
        # shows short, check whether the store received something with the
        # SAME (normalized) product name under a DIFFERENT ProductCode --
        # NMW and each store keep independent product masters (verified
        # live: COTTON 25GM [BOT CARE] is 5893623 at NMW, 5893906 at NMC for
        # the same physical item). This is the only signal available for
        # ST_-prefixed/internal-transfer stores, which have no bill-number
        # link either. Scoped to the same store+SupplierCode+series+window,
        # just without the ProductCode filter.
        still_short = [code for code, req_qty in req_by_product.items()
                       if got_by_product.get(code, 0.0) < req_qty - 0.01]
        name_qty = {}
        grns_by_name = {}
        if still_short:
            cursor.execute(
                f"""
                SELECT p.ProductName, pt.stockreceived, pt.Grnnumber, CAST(pt.grndate AS DATE)
                FROM sync.PurchaseTrans pt
                LEFT JOIN sync.Products p
                    ON p.tenant_id = pt.tenant_id AND p.store_id = pt.store_id AND p.ProductCode = pt.ProductCode
                WHERE pt.tenant_id = ? AND pt.store_id = ? AND pt.SupplierCode = ? AND LTRIM(RTRIM(pt.InvoiceSeries)) = ?
                  AND CAST(pt.grndate AS DATE) BETWEEN ? AND DATEADD(DAY, {PURCHASE_MATCH_WINDOW_DAYS}, ?)
                """,
                (tenant_id, dest_store_id, raw_code, series, bdate, bdate),
            )
            for pname, stockreceived, grnnumber, grndate in cursor.fetchall():
                key = _normalize_name(pname)
                if not key:
                    continue
                name_qty[key] = name_qty.get(key, 0.0) + float(stockreceived or 0)
                grns_by_name.setdefault(key, set()).add((grnnumber, grndate))

        matched_by_name = set()
        for code in still_short:
            key = _normalize_name(name_by_product.get(code))
            if key and name_qty.get(key, 0.0) >= req_by_product[code] - 0.01:
                matched_by_name.add(code)
                grns_seen.update({g: True for g in grns_by_name.get(key, ())})

        matched_products = sum(
            1 for code, req_qty in req_by_product.items()
            if got_by_product.get(code, 0.0) >= req_qty - 0.01 or code in matched_by_name
        )
        total_products = len(req_by_product)
        # The specific items the store has NOT yet received a purchase-entry for
        # (so a "Pending" bill with GRN numbers is self-explanatory -- these are
        # the products still missing from the receipt).
        pending_products = [
            {"product_code": str(code), "product_name": name_by_product.get(code) or str(code),
             "required_qty": req_qty, "received_qty": got_by_product.get(code, 0.0)}
            for code, req_qty in req_by_product.items()
            if got_by_product.get(code, 0.0) < req_qty - 0.01 and code not in matched_by_name
        ]
        distinct_grns = sorted(grns_seen.keys(), key=lambda g: (g[1], g[0]))
        entry_no = ", ".join(str(g[0]) for g in distinct_grns) if distinct_grns else None
        # The completing GRN (latest) matches the single number shown in the list.
        completing_grn = str(max(g[0] for g in distinct_grns)) if distinct_grns else None
        entry_date = distinct_grns[0][1].isoformat() if distinct_grns else None

        status = _classify_purchase_status(total_products, matched_products, False, bdate)
        match_basis = "product_qty" if matched_products else "none"
        grn_amount = None

        # Bill-number match (IV-series stores only -- see get_purchase_status_map):
        # staff key NMW's own bill number into Batches.InvoiceNumber. A hit here
        # is authoritative and overrides the per-product read above, which can
        # under-report when NMW and the store disagree on a product's code for
        # the same physical item.
        if series == "IV":
            cursor.execute(
                f"""
                SELECT TOP (1) GrnNumber, MAX(GrnDate)
                FROM sync.Batches
                WHERE tenant_id = ? AND store_id = ? AND SupplierCode = ?
                  AND LEN(InvoiceNumber) >= 4 AND ? LIKE '%' + InvoiceNumber
                  AND CAST(GrnDate AS DATE) BETWEEN ? AND DATEADD(DAY, {PURCHASE_MATCH_WINDOW_DAYS}, ?)
                GROUP BY GrnNumber
                ORDER BY MAX(GrnDate)
                """,
                (tenant_id, dest_store_id, raw_code, bnumber, bdate, bdate),
            )
            inv_row = cursor.fetchone()
            if inv_row:
                inv_grn, inv_grn_date = inv_row
                status = "completed"
                matched_products = total_products
                pending_products = []
                completing_grn = str(int(inv_grn))
                entry_no = completing_grn
                entry_date = inv_grn_date.isoformat() if hasattr(inv_grn_date, "isoformat") else str(inv_grn_date)
                match_basis = "bill_number"
                cursor.execute(
                    "SELECT SUM(stockreceived * itemcost) FROM sync.PurchaseTrans "
                    "WHERE tenant_id = ? AND store_id = ? AND SupplierCode = ? AND Grnnumber = ?",
                    (tenant_id, dest_store_id, raw_code, inv_grn),
                )
                amt_row = cursor.fetchone()
                grn_amount = float(amt_row[0]) if amt_row and amt_row[0] is not None else None

        return {
            "purchase_status": status,
            "matched_products": matched_products,
            "total_products": total_products,
            "entry_no": entry_no,
            "completing_grn": completing_grn,
            "entry_date": entry_date,
            "pending_products": pending_products,
            "match_basis": match_basis,
            "grn_amount": grn_amount,
            "dest_store_id": dest_store_id,
            "dest_store_code": dest_store_code,
            "dest_store_name": dest_store_name,
        }
    finally:
        cursor.close()
        conn.close()
