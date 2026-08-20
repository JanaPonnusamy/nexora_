"""Exports the NMC -> NMA SubLocation candidate list to Excel.

This is the hand-off file for nma_branch_sublocation_update_from_excel.py:
it contains only what that script is allowed to touch -- ProductCode and the
proposed SubLocation -- for NMA products resolved through the validated
NMC -> NMA mapping (dbo.SupplierProductMatch, SupplierCode+SupplierProductCode,
never Stores.Ho_code, never ProductCode equality across stores), restricted to
the canonical "OIN <first letter of product name>" pattern.

Read-only against the central OrderNMC database. Writes nothing anywhere.

Usage:
    backend/.venv/Scripts/python backend/scripts/nmc_to_nma_sublocation_source.py [output.xlsx]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.legacy_order.database import get_central_connection
from modules.time_report.excel_export import table_xlsx
from scripts.nmc_to_nma_sublocation_update import _CTE_SQL

_CANONICAL_SELECT = _CTE_SQL + """
SELECT
    fc.NmaProductCode                  AS NmaProductCode,
    nap.ProductName                    AS NmaProductName,
    nap.UnitDescription                AS NmaUnitDescription,
    nap.SubLocation                    AS CurrentNmaSubLocation,
    fc.NmcProductCode                  AS NmcProductCode,
    ncp.ProductName                    AS NmcProductName,
    fc.NmcSubLocation                  AS ProposedSubLocation
FROM FinalCandidate fc
JOIN dbo.Products nap ON nap.StoreName = 'NMA' AND nap.ProductCode = fc.NmaProductCode
JOIN dbo.Products ncp ON ncp.StoreName = 'NMC' AND ncp.ProductCode = fc.NmcProductCode
WHERE UPPER(LTRIM(RTRIM(fc.NmcSubLocation))) LIKE 'OIN _'
  AND LEN(LTRIM(RTRIM(fc.NmcSubLocation))) = 5
  -- Letter need not match the product name's first letter -- legacy stores
  -- bin by brand/active-ingredient family (e.g. BETNOVATE-C sits under
  -- 'OIN H'), not by the product name's initial.
ORDER BY fc.NmaProductCode;
"""


def fetch_candidates(conn):
    cur = conn.cursor()
    cur.execute(_CANONICAL_SELECT)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def export(rows, out_path):
    # Columns kept exactly to what the branch updater is allowed to read/write:
    # NMA ProductCode, NMA ProductName, SubLocation (proposed value to write),
    # UnitDescription (NMA's own, for context only -- never written).
    headers = ["ProductCode", "ProductName", "SubLocation", "UnitDescription"]
    xlsx_rows = []
    for r in rows:
        current = (r["CurrentNmaSubLocation"] or "").strip()
        hex_ = "C6EFCE" if current else "FFEB9C"
        xlsx_rows.append(([
            r["NmaProductCode"], r["NmaProductName"], r["ProposedSubLocation"], r["NmaUnitDescription"] or "",
        ], hex_))

    buf = table_xlsx("NMA SubLocation Update Source", headers, xlsx_rows)
    Path(out_path).write_bytes(buf.getvalue())
    return out_path


if __name__ == "__main__":
    conn = get_central_connection()
    try:
        rows = fetch_candidates(conn)
    finally:
        conn.close()

    out_path = sys.argv[1] if len(sys.argv) > 1 else "nma_sublocation_update_source.xlsx"
    export(rows, out_path)

    needs_update = [r for r in rows if not (r["CurrentNmaSubLocation"] or "").strip()]
    print(f"Total canonical candidates: {len(rows)}")
    print(f"Needs update (blank in central mirror): {len(needs_update)}")
    for r in needs_update:
        print(f"  {r['NmaProductCode']} | {r['NmaProductName']} | -> {r['ProposedSubLocation']}")
    print(f"\nWritten: {out_path}")
