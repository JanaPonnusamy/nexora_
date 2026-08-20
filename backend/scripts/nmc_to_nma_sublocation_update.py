"""NMC -> NMA SubLocation fill-missing update.

Fills dbo.Products.SubLocation for StoreName='NMA' rows that are currently
NULL/blank, using NMC (StoreName='NMC') as the source of truth for OIN/topical
products. Source detection reuses the exact same two-level logic already
implemented in nmc_oin_sublocation_report.py (UnitDescription LIKE 'OIN%',
plus the ProductName OINTMENT/OINT/OIN/CREAM fallback) -- not a separate
implementation.

Cross-store identity is strictly SupplierCode + SupplierProductCode via
dbo.SupplierProductMatch, joined across StoreName. Stores.Ho_code is never
used as the join key (only to exclude each store's own self-referencing HO
code row, exactly as validated in the report). ProductCode is never assumed
equal across stores.

Safety rules (never violated):
  - NMA mapping missing                  -> excluded, not updated
  - Ambiguous NMA mapping (one NMC id ->
    >1 distinct NMA ProductCode)         -> excluded, not updated
  - Conflicting NMC source SubLocations
    (>1 NMC product -> same NMA code,
    disagreeing non-blank SubLocations)  -> excluded, not updated
  - NMA already has a non-blank
    SubLocation                          -> excluded (fill-missing only)
  - IsActive: explicit False = inactive,
    NULL = treated as active

Only dbo.Products.SubLocation for StoreName='NMA' rows is ever written.
SupplierProductMatch, NMC Products, and NMW Products are never modified.

Usage:
    backend/.venv/Scripts/python backend/scripts/nmc_to_nma_sublocation_update.py            # dry run only (default, no writes)
    backend/.venv/Scripts/python backend/scripts/nmc_to_nma_sublocation_update.py --execute   # dry run, then perform the guarded UPDATE inside a transaction
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.legacy_order.database import get_central_connection

# ------------------------------------------------------------------
# The single CTE pipeline, shared verbatim by the dry-run SELECT and the
# guarded UPDATE below -- SQL Server 2014-compatible syntax only.
# ------------------------------------------------------------------
_CTE_SQL = """
DECLARE @NmcHo varchar(50), @NmaHo varchar(50);
SELECT @NmcHo = Ho_code FROM dbo.Stores WHERE StoreName = 'NMC';
SELECT @NmaHo = Ho_code FROM dbo.Stores WHERE StoreName = 'NMA';

;WITH NmcSource AS (
    SELECT ProductCode, ProductName, UnitDescription, SubLocation
    FROM dbo.Products
    WHERE StoreName = 'NMC'
      AND LTRIM(RTRIM(ISNULL(SubLocation, ''))) <> ''
      AND UPPER(LTRIM(RTRIM(SubLocation))) <> 'NULL'
      AND (
            UPPER(LTRIM(RTRIM(UnitDescription))) LIKE 'OIN%'
         OR (
              (
                    UPPER(ProductName) LIKE '%OINTMENT%'
                 OR UPPER(ProductName) LIKE '%OINT%'
                 OR UPPER(ProductName) LIKE '%OIN%'
                 OR UPPER(ProductName) LIKE '%CREAM%'
              )
              -- Level-2 fallback is only trustworthy when NMC's own SubLocation
              -- actually confirms an OIN bin -- otherwise "OIN" is just a
              -- substring of the name (EPTOIN, ISOTROIN, JOINTACE, GERIJOINT,
              -- LUBRIJOINT, CELETOIN...) or a real ointment stored in a non-OIN
              -- bin (lotions filed under LOT), neither of which should be
              -- pushed into NMA as an "OIN" location.
              AND UPPER(LTRIM(RTRIM(SubLocation))) LIKE 'OIN%'
            )
      )
),
NmcLinks AS (
    SELECT ProductCode, SupplierCode, SupplierProductCode
    FROM dbo.SupplierProductMatch
    WHERE StoreName = 'NMC' AND ISNULL(IsActive, 1) = 1
      AND (@NmcHo IS NULL OR SupplierCode <> @NmcHo)
),
NmaLinks AS (
    SELECT ProductCode, SupplierCode, SupplierProductCode
    FROM dbo.SupplierProductMatch
    WHERE StoreName = 'NMA' AND ISNULL(IsActive, 1) = 1
      AND (@NmaHo IS NULL OR SupplierCode <> @NmaHo)
),
Candidate AS (
    SELECT DISTINCT
        s.ProductCode  AS NmcProductCode,
        s.SubLocation  AS NmcSubLocation,
        nl.ProductCode AS NmaProductCode
    FROM NmcSource s
    JOIN NmcLinks cl ON cl.ProductCode = s.ProductCode
    JOIN NmaLinks nl ON nl.SupplierCode = cl.SupplierCode
                     AND nl.SupplierProductCode = cl.SupplierProductCode
),
NmcAmbiguous AS (
    -- one NMC product resolving to more than one distinct NMA ProductCode
    SELECT NmcProductCode
    FROM Candidate
    GROUP BY NmcProductCode
    HAVING COUNT(DISTINCT NmaProductCode) > 1
),
CandidateClean AS (
    SELECT * FROM Candidate
    WHERE NmcProductCode NOT IN (SELECT NmcProductCode FROM NmcAmbiguous)
),
NmaConflicting AS (
    -- one NMA ProductCode reachable from multiple NMC products with
    -- disagreeing non-blank source SubLocations
    SELECT NmaProductCode
    FROM CandidateClean
    GROUP BY NmaProductCode
    HAVING COUNT(DISTINCT NmcSubLocation) > 1
),
FinalCandidate AS (
    SELECT
        NmaProductCode,
        MIN(NmcProductCode) AS NmcProductCode,
        MAX(NmcSubLocation) AS NmcSubLocation
    FROM CandidateClean
    WHERE NmaProductCode NOT IN (SELECT NmaProductCode FROM NmaConflicting)
    GROUP BY NmaProductCode
)
"""

_DRY_RUN_SELECT = _CTE_SQL + """
SELECT
    fc.NmcProductCode                   AS NmcProductCode,
    ncp.ProductName                     AS NmcProductName,
    fc.NmcSubLocation                   AS NmcSubLocation,
    fc.NmaProductCode                   AS NmaProductCode,
    nap.ProductName                     AS NmaProductName,
    nap.SubLocation                     AS CurrentNmaSubLocation,
    fc.NmcSubLocation                   AS ProposedNmaSubLocation
FROM FinalCandidate fc
JOIN dbo.Products nap ON nap.StoreName = 'NMA' AND nap.ProductCode = fc.NmaProductCode
JOIN dbo.Products ncp ON ncp.StoreName = 'NMC' AND ncp.ProductCode = fc.NmcProductCode
WHERE LTRIM(RTRIM(ISNULL(nap.SubLocation, ''))) IN ('', 'NULL')
ORDER BY fc.NmaProductCode;
"""

_COUNTS_SQL = _CTE_SQL + """
SELECT
    (SELECT COUNT(*) FROM NmcSource) AS NmcSourceTotal,
    (SELECT COUNT(DISTINCT NmcProductCode) FROM NmcAmbiguous) AS AmbiguousNmcExcluded,
    (SELECT COUNT(DISTINCT NmaProductCode) FROM NmaConflicting) AS ConflictingNmaExcluded,
    (SELECT COUNT(*)
       FROM FinalCandidate fc
       JOIN dbo.Products nap ON nap.StoreName = 'NMA' AND nap.ProductCode = fc.NmaProductCode
      WHERE LTRIM(RTRIM(ISNULL(nap.SubLocation, ''))) NOT IN ('', 'NULL')) AS AlreadyPopulatedSkipped,
    (SELECT COUNT(*)
       FROM FinalCandidate fc
       JOIN dbo.Products nap ON nap.StoreName = 'NMA' AND nap.ProductCode = fc.NmaProductCode
      WHERE LTRIM(RTRIM(ISNULL(nap.SubLocation, ''))) IN ('', 'NULL')) AS EligibleForUpdate,
    (SELECT COUNT(*) FROM NmcSource s
      WHERE NOT EXISTS (SELECT 1 FROM Candidate c WHERE c.NmcProductCode = s.ProductCode)
    ) AS MissingNmaMapping;
"""

_UPDATE_SQL = _CTE_SQL + """
UPDATE nap
SET nap.SubLocation = fc.NmcSubLocation
OUTPUT inserted.ProductCode, inserted.ProductName, deleted.SubLocation AS OldSubLocation, inserted.SubLocation AS NewSubLocation
FROM dbo.Products nap
JOIN FinalCandidate fc ON fc.NmaProductCode = nap.ProductCode
WHERE nap.StoreName = 'NMA'
  AND LTRIM(RTRIM(ISNULL(nap.SubLocation, ''))) IN ('', 'NULL');
"""


def _fetch_all(cur, sql):
    cur.execute(sql)
    cols = [c[0] for c in cur.description]
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    return rows


def dry_run(conn):
    cur = conn.cursor()
    counts = _fetch_all(cur, _COUNTS_SQL)[0]
    rows = _fetch_all(cur, _DRY_RUN_SELECT)

    print("=== DRY RUN: NMC -> NMA SubLocation fill-missing ===\n")
    print(f"NMC source products (qualifying, non-blank SubLocation): {counts['NmcSourceTotal']}")
    print(f"Ambiguous NMC->NMA mappings excluded:                     {counts['AmbiguousNmcExcluded']}")
    print(f"Conflicting source SubLocations excluded:                 {counts['ConflictingNmaExcluded']}")
    print(f"Already-populated NMA rows skipped:                       {counts['AlreadyPopulatedSkipped']}")
    print(f"Missing NMA mapping (no SupplierProductMatch link found): {counts['MissingNmaMapping']}")
    print(f"\n>>> Total rows ELIGIBLE for update: {counts['EligibleForUpdate']} <<<\n")

    print("--- Sample eligible rows (first 20) ---")
    header = ["NMC Code", "NMC Name", "NMC Loc", "NMA Code", "NMA Name", "Current NMA Loc", "Proposed NMA Loc"]
    print(" | ".join(header))
    for r in rows[:20]:
        print(" | ".join(str(v) for v in [
            r["NmcProductCode"], (r["NmcProductName"] or "")[:22], r["NmcSubLocation"],
            r["NmaProductCode"], (r["NmaProductName"] or "")[:22],
            r["CurrentNmaSubLocation"], r["ProposedNmaSubLocation"],
        ]))

    return counts, rows


def execute_update(conn, expected_eligible):
    # pyodbc connections default to autocommit=False, so pyodbc itself already
    # wraps everything up to the next commit()/rollback() in one transaction.
    # Raw "BEGIN/COMMIT TRANSACTION" SQL text on top of that only opens/closes
    # a NESTED SQL Server transaction -- the outer pyodbc-level transaction is
    # untouched and, if never explicitly committed via conn.commit(), gets
    # silently rolled back when the connection closes. Use conn.commit()/
    # conn.rollback(), not SQL text.
    cur = conn.cursor()
    try:
        updated_rows = _fetch_all(cur, _UPDATE_SQL)
        rowcount = len(updated_rows)

        print(f"\n=== UPDATE executed inside transaction: {rowcount} row(s) affected ===")

        if rowcount != expected_eligible:
            print(f"MISMATCH: dry-run counted {expected_eligible} eligible rows but UPDATE "
                  f"affected {rowcount}. Rolling back -- no changes committed.")
            conn.rollback()
            return None

        # Post-update verification, still inside the open transaction.
        cur.execute(
            """
            SELECT COUNT(*) FROM dbo.Products
            WHERE StoreName = 'NMA'
              AND LTRIM(RTRIM(ISNULL(SubLocation, ''))) = ''
              AND ProductCode IN ({})
            """.format(",".join(str(r["ProductCode"]) for r in updated_rows) or "-1")
        )
        still_blank = cur.fetchone()[0]
        if still_blank != 0:
            print(f"VERIFICATION FAILED: {still_blank} of the updated rows are still blank. "
                  "Rolling back -- no changes committed.")
            conn.rollback()
            return None

        print("Verification passed: all updated rows now have a non-blank SubLocation.")
        conn.commit()
        print("COMMITTED.")

        print("\n--- Updated NMA rows ---")
        print("ProductCode | ProductName | OldSubLocation -> NewSubLocation")
        for r in updated_rows:
            print(f"{r['ProductCode']} | {(r['ProductName'] or '')[:30]} | "
                  f"{r['OldSubLocation']!r} -> {r['NewSubLocation']!r}")

        return updated_rows
    except Exception:
        conn.rollback()
        raise


if __name__ == "__main__":
    execute = "--execute" in sys.argv
    conn = get_central_connection()
    try:
        counts, rows = dry_run(conn)
        if execute:
            execute_update(conn, counts["EligibleForUpdate"])
        else:
            print("\n(dry run only -- pass --execute to perform the guarded UPDATE)")
    finally:
        conn.close()
