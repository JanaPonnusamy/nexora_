"""Second pass for NMA's remaining blank-OIN products.

The first pass (nma_sublocation_source_from_report.py) only considered NMC
products that NMC itself classified as OIN (UnitDescription LIKE 'OIN%' or a
name-keyword fallback). That missed real matches where NMC's own
UnitDescription isn't 'OIN' or the product name uses a word outside the
fallback keyword list (JELLY, SOLUTION, ...) even though NMC's SubLocation is
a perfectly valid 'OIN <letter>' value.

This pass drops that gate entirely: for every NMA product that is currently
UnitDescription='OIN' with a blank SubLocation, match it to NMC directly
(SupplierProductMatch first, then unique normalized-name match) and propose
NMC's SubLocation only if it is itself the canonical 'OIN <letter>' pattern.
Anything where NMC's own location isn't OIN-shaped (LOT/CON/SURG/N0xx/etc.),
or where no NMC match exists at all, is left alone -- never invented.

Read-only against dbo.Products / dbo.SupplierProductMatch / dbo.Stores in the
central OrderNMC database. Writes nothing -- only the output Excel file, in
the same 4-column shape (ProductCode, ProductName, SubLocation,
UnitDescription) consumed by nma_branch_sublocation_update_from_excel.py.

Usage:
    backend/.venv/Scripts/python backend/scripts/nma_remaining_oin_direct_match.py [output.xlsx]
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.legacy_order.database import get_central_connection
from modules.time_report.excel_export import table_xlsx
from scripts.nma_sublocation_source_from_report import normalize_name

_CANONICAL_RE = re.compile(r"^OIN [A-Z]$")


def is_canonical(subloc):
    return bool(_CANONICAL_RE.match((subloc or "").strip().upper()))


def fetch_nma_blank_oin(cur):
    cur.execute("""
        SELECT ProductCode, ProductName, UnitDescription
        FROM dbo.Products
        WHERE StoreName = 'NMA'
          AND UPPER(LTRIM(RTRIM(ISNULL(UnitDescription, '')))) = 'OIN'
          AND LTRIM(RTRIM(ISNULL(SubLocation, ''))) IN ('', 'NULL')
    """)
    return [{"ProductCode": pc, "ProductName": name, "UnitDescription": unit} for pc, name, unit in cur.fetchall()]


def fetch_own_ho_code(cur, store_name):
    cur.execute("SELECT Ho_code FROM dbo.Stores WHERE StoreName = ?", store_name)
    row = cur.fetchone()
    return row[0] if row else None


def fetch_links(cur, store_name, own_ho_code):
    cur.execute(
        """
        SELECT SupplierCode, SupplierProductCode, ProductCode
        FROM dbo.SupplierProductMatch
        WHERE StoreName = ? AND ISNULL(IsActive, 1) = 1
          AND (? IS NULL OR SupplierCode <> ?)
        """,
        store_name, own_ho_code, own_ho_code,
    )
    links = {}
    for supplier_code, supplier_product_code, product_code in cur.fetchall():
        links.setdefault((supplier_code, supplier_product_code), set()).add(product_code)
    return links


def build(conn):
    cur = conn.cursor()
    nma_products = fetch_nma_blank_oin(cur)
    nma_codes = [p["ProductCode"] for p in nma_products]

    nma_ho = fetch_own_ho_code(cur, "NMA")
    nmc_ho = fetch_own_ho_code(cur, "NMC")
    nma_links = fetch_links(cur, "NMA", nma_ho)
    nmc_links = fetch_links(cur, "NMC", nmc_ho)

    # NMA ProductCode -> its own SupplierProductMatch (SupplierCode, SupplierProductCode) pairs
    nma_own_links = {}
    for (sc, spc), codes in nma_links.items():
        for pc in codes:
            nma_own_links.setdefault(pc, []).append((sc, spc))

    cur.execute("SELECT ProductCode, ProductName, SubLocation FROM dbo.Products WHERE StoreName = 'NMC'")
    nmc_by_code = {}
    nmc_name_index = {}
    for pc, name, subloc in cur.fetchall():
        nmc_by_code[pc] = (name, subloc)
        key = normalize_name(name)
        if key:
            nmc_name_index.setdefault(key, []).append((pc, name, subloc))

    results = []
    stats = {"total_considered": len(nma_products), "supplier_match": 0, "name_match": 0,
              "nmc_not_oin": 0, "no_nmc_match": 0, "ambiguous_name": 0}

    for p in nma_products:
        pc = p["ProductCode"]
        matched_nmc_codes = set()
        for key in nma_own_links.get(pc, []):
            codes = nmc_links.get(key)
            if codes:
                matched_nmc_codes |= codes

        source = None
        if len(matched_nmc_codes) == 1:
            source = "SUPPLIER_MATCH"
            nmc_pc = next(iter(matched_nmc_codes))
        elif len(matched_nmc_codes) > 1:
            stats["ambiguous_name"] += 1
            continue
        else:
            cands = nmc_name_index.get(normalize_name(p["ProductName"]), [])
            if len(cands) == 1:
                source = "NAME_MATCH"
                nmc_pc = cands[0][0]
            elif len(cands) > 1:
                stats["ambiguous_name"] += 1
                continue
            else:
                stats["no_nmc_match"] += 1
                continue

        nmc_name, nmc_subloc = nmc_by_code.get(nmc_pc, (None, None))
        if not is_canonical(nmc_subloc):
            stats["nmc_not_oin"] += 1
            continue

        stats[source.lower()] += 1
        results.append((pc, p["ProductName"], nmc_subloc.strip().upper(), p["UnitDescription"], source, nmc_pc, nmc_name))

    return results, stats


def export(results, out_path):
    headers = ["ProductCode", "ProductName", "SubLocation", "UnitDescription"]
    xlsx_rows = []
    for pc, name, subloc, unit, source, nmc_pc, nmc_name in results:
        hex_ = "FFEB9C" if source == "NAME_MATCH" else "C6EFCE"
        xlsx_rows.append(([pc, name, subloc, unit or ""], hex_))
    buf = table_xlsx("NMA Remaining OIN -- Direct NMC Match (pass 2)", headers, xlsx_rows)
    Path(out_path).write_bytes(buf.getvalue())


if __name__ == "__main__":
    out_path = sys.argv[1] if len(sys.argv) > 1 else "nma_sublocation_update_source_v3.xlsx"

    conn = get_central_connection()
    try:
        results, stats = build(conn)
    finally:
        conn.close()

    print(f"NMA blank-OIN products considered: {stats['total_considered']}")
    print(f"Matched via SupplierProductMatch, NMC SubLocation canonical: {stats['supplier_match']}")
    print(f"Matched via normalized name, NMC SubLocation canonical:     {stats['name_match']}")
    print(f"NMC match found but NMC's own SubLocation isn't OIN-shaped: {stats['nmc_not_oin']}")
    print(f"No NMC match at all:                                       {stats['no_nmc_match']}")
    print(f"Ambiguous (>1 NMC candidate), skipped:                     {stats['ambiguous_name']}")
    print(f"\nTotal proposed rows: {len(results)}")

    print("\n--- Sample (first 30) ---")
    for pc, name, subloc, unit, source, nmc_pc, nmc_name in results[:30]:
        print(f"  {pc} | {name} | -> {subloc}  [{source}: NMC {nmc_pc} {nmc_name!r}]")

    export(results, out_path)
    print(f"\nWritten: {out_path}")
