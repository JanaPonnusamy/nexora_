"""NMC OIN/topical SubLocation validation report.

NMC's dbo.Products.SubLocation is treated as the source of truth for
ointment/cream/topical products. The source set is built from two detection
levels:

  Level 1 (UNIT_OIN)      -- UnitDescription LIKE 'OIN%' (trimmed, case-insensitive)
  Level 2 (NAME_* fallback) -- ProductName contains OINTMENT/OINT/OIN/CREAM,
                               for products Level 1 did not already catch.

For every source product this resolves the matching NMW / NMA product via the
real cross-store identity in dbo.SupplierProductMatch -- SupplierCode +
SupplierProductCode, joined across StoreName -- NOT Stores.Ho_code and NOT
ProductCode equality across stores (NMC/NMW/NMA ProductCodes are independent).

Read-only. Connects only to the central OrderNMC database via the existing
modules.legacy_order.database.get_central_connection() helper -- no branch/
store databases are touched, and no rows are written anywhere.

Usage:
    backend/.venv/Scripts/python backend/scripts/nmc_oin_sublocation_report.py [output.xlsx]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.legacy_order.database import get_central_connection
from modules.time_report.excel_export import table_xlsx

TARGET_STORES = ("NMW", "NMA")

RED = "FFC7CE"
YELLOW = "FFEB9C"
GREEN = "C6EFCE"

_BATCH = 1000

# Most specific / strongest reason wins when a product matches more than one
# ProductName keyword.
_NAME_DETECTION_PRIORITY = ["NAME_OINTMENT", "NAME_OINT", "NAME_OIN", "NAME_CREAM"]


def _blank(s):
    return s is None or not str(s).strip()


def _chunks(seq, size):
    seq = list(seq)
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


# ------------------------------------------------------------------
# Source product discovery (NMC)
# ------------------------------------------------------------------
def fetch_nmc_unit_oin_products(cur):
    """Level 1: UnitDescription LIKE 'OIN%', trimmed/case-insensitive."""
    cur.execute(
        """
        SELECT ProductCode, ProductName, UnitDescription, SubLocation
        FROM dbo.Products
        WHERE StoreName = 'NMC'
          AND UPPER(LTRIM(RTRIM(UnitDescription))) LIKE 'OIN%'
          AND LTRIM(RTRIM(ISNULL(SubLocation, ''))) <> ''
          AND UPPER(LTRIM(RTRIM(SubLocation))) <> 'NULL'
        ORDER BY ProductCode
        """
    )
    cols = [c[0] for c in cur.description]
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    for r in rows:
        r["SourceDetection"] = "UNIT_OIN"
    return rows


def fetch_nmc_name_fallback_products(cur, exclude_codes):
    """Level 2: ProductName keyword fallback for products Level 1 missed."""
    cur.execute(
        """
        SELECT ProductCode, ProductName, UnitDescription, SubLocation
        FROM dbo.Products
        WHERE StoreName = 'NMC'
          AND LTRIM(RTRIM(ISNULL(SubLocation, ''))) <> ''
          AND UPPER(LTRIM(RTRIM(SubLocation))) <> 'NULL'
          -- Level-2 fallback is only trustworthy when NMC's own SubLocation
          -- actually confirms an OIN bin -- otherwise "OIN" is just a
          -- substring of the name (EPTOIN, ISOTROIN, JOINTACE, GERIJOINT,
          -- LUBRIJOINT, CELETOIN...) or a real ointment stored in a non-OIN
          -- bin (lotions filed under LOT), neither of which belongs here.
          AND UPPER(LTRIM(RTRIM(SubLocation))) LIKE 'OIN%'
          AND (
                UPPER(ProductName) LIKE '%OINTMENT%'
             OR UPPER(ProductName) LIKE '%OINT%'
             OR UPPER(ProductName) LIKE '%OIN%'
             OR UPPER(ProductName) LIKE '%CREAM%'
          )
        ORDER BY ProductCode
        """
    )
    cols = [c[0] for c in cur.description]
    rows = []
    for row in cur.fetchall():
        r = dict(zip(cols, row))
        if r["ProductCode"] in exclude_codes:
            continue  # already caught by Level 1 -- never duplicate
        name_upper = (r["ProductName"] or "").upper()
        reasons = []
        if "OINTMENT" in name_upper:
            reasons.append("NAME_OINTMENT")
        if "OINT" in name_upper:
            reasons.append("NAME_OINT")
        if "OIN" in name_upper:
            reasons.append("NAME_OIN")
        if "CREAM" in name_upper:
            reasons.append("NAME_CREAM")
        # Strongest/most specific reason only -- do not duplicate the row.
        r["SourceDetection"] = next(
            (reason for reason in _NAME_DETECTION_PRIORITY if reason in reasons),
            reasons[0] if reasons else "NAME_UNKNOWN",
        )
        rows.append(r)
    return rows


# ------------------------------------------------------------------
# Cross-store mapping (dbo.SupplierProductMatch)
# ------------------------------------------------------------------
def fetch_supplier_links(cur, store_name):
    """SupplierCode/SupplierProductCode -> {ProductCode,...} for one store,
    excluding the store's own self-referencing HO code (SupplierProductCode
    always equals ProductCode for that code and never appears in other
    stores, so it can never be used as a cross-store join key)."""
    cur.execute("SELECT Ho_code FROM dbo.Stores WHERE StoreName = ?", store_name)
    row = cur.fetchone()
    own_ho_code = row[0] if row else None

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
    dupes = {k: v for k, v in links.items() if len(v) > 1}
    return links, dupes


def fetch_nmc_links_for_products(cur, product_codes):
    """NMC's own SupplierCode/SupplierProductCode rows, keyed by ProductCode
    (excluding NMC's own self-referencing HO code, same reasoning as above)."""
    cur.execute("SELECT Ho_code FROM dbo.Stores WHERE StoreName = 'NMC'")
    row = cur.fetchone()
    own_ho_code = row[0] if row else None

    out = {}
    for batch in _chunks(product_codes, _BATCH):
        if not batch:
            continue
        placeholders = ",".join("?" for _ in batch)
        cur.execute(
            f"""
            SELECT ProductCode, SupplierCode, SupplierProductCode
            FROM dbo.SupplierProductMatch
            WHERE StoreName = 'NMC' AND ISNULL(IsActive, 1) = 1
              AND (? IS NULL OR SupplierCode <> ?)
              AND ProductCode IN ({placeholders})
            """,
            own_ho_code, own_ho_code, *batch,
        )
        for pc, supplier_code, supplier_product_code in cur.fetchall():
            out.setdefault(pc, []).append((supplier_code, supplier_product_code))
    return out


def fetch_products_detail(cur, store_name, product_codes):
    """ProductName/UnitDescription/SubLocation for a set of ProductCodes."""
    result = {}
    for batch in _chunks(product_codes, _BATCH):
        if not batch:
            continue
        placeholders = ",".join("?" for _ in batch)
        cur.execute(
            f"""
            SELECT ProductCode, ProductName, UnitDescription, SubLocation
            FROM dbo.Products
            WHERE StoreName = ? AND ProductCode IN ({placeholders})
            """,
            store_name, *batch,
        )
        for pc, name, unit_desc, subloc in cur.fetchall():
            result[pc] = {"ProductName": name, "UnitDescription": unit_desc, "SubLocation": subloc}
    return result


def resolve_store_match(nmc_links, target_links_map, target_detail_map):
    """Given NMC's (SupplierCode, SupplierProductCode) pairs for one product,
    find the corresponding target-store ProductCode(s).

    Returns a dict: mapping_status (MAPPED/MISSING), ambiguous (bool),
    product_code (only set when unambiguous), product_name, unit_description,
    subloc, subloc_status.
    """
    matched_codes = set()
    for key in nmc_links:
        codes = target_links_map.get(key)
        if codes:
            matched_codes |= codes

    if not matched_codes:
        return {
            "mapping_status": "MISSING", "ambiguous": False, "product_code": None,
            "product_name": "", "unit_description": "", "subloc": "", "subloc_status": "N/A",
        }

    if len(matched_codes) > 1:
        # Multiple distinct target ProductCodes -- do not silently pick one.
        return {
            "mapping_status": "MAPPED", "ambiguous": True,
            "product_code": ", ".join(str(c) for c in sorted(matched_codes)),
            "product_name": "<AMBIGUOUS>", "unit_description": "<AMBIGUOUS>",
            "subloc": "<AMBIGUOUS>", "subloc_status": "AMBIGUOUS",
        }

    pc = next(iter(matched_codes))
    detail = target_detail_map.get(pc, {})
    subloc = detail.get("SubLocation")
    return {
        "mapping_status": "MAPPED", "ambiguous": False, "product_code": pc,
        "product_name": detail.get("ProductName") or "",
        "unit_description": detail.get("UnitDescription") or "",
        "subloc": subloc or "",
        "subloc_status": "MISSING" if _blank(subloc) else "OK",
    }


# ------------------------------------------------------------------
# Report assembly
# ------------------------------------------------------------------
def build_report():
    conn = get_central_connection()
    cur = conn.cursor()
    try:
        unit_rows = fetch_nmc_unit_oin_products(cur)
        unit_codes = {r["ProductCode"] for r in unit_rows}
        fallback_rows = fetch_nmc_name_fallback_products(cur, unit_codes)
        nmc_products = unit_rows + fallback_rows

        product_codes = [p["ProductCode"] for p in nmc_products]
        nmc_links_by_product = fetch_nmc_links_for_products(cur, product_codes)

        target_links, target_dupes = {}, {}
        for store in TARGET_STORES:
            links, dupes = fetch_supplier_links(cur, store)
            target_links[store] = links
            if dupes:
                target_dupes[store] = dupes

        all_target_codes = {store: set() for store in TARGET_STORES}
        for store in TARGET_STORES:
            for codes in target_links[store].values():
                all_target_codes[store] |= codes
        target_detail = {
            store: fetch_products_detail(cur, store, all_target_codes[store])
            for store in TARGET_STORES
        }

        rows = []
        summary = {
            "total": len(nmc_products),
            "via_unit": len(unit_rows),
            "via_name_fallback": len(fallback_rows),
            "nmw": {"mapping_found": 0, "mapping_missing": 0, "subloc_present": 0,
                    "subloc_missing": 0, "ambiguous": 0},
            "nma": {"mapping_found": 0, "mapping_missing": 0, "subloc_present": 0,
                    "subloc_missing": 0, "ambiguous": 0},
            "fully_ok": 0,
        }

        for p in nmc_products:
            pc = p["ProductCode"]
            nmc_links = nmc_links_by_product.get(pc, [])

            per_store = {}
            for store, key in (("NMW", "nmw"), ("NMA", "nma")):
                m = resolve_store_match(nmc_links, target_links[store], target_detail[store])
                per_store[store] = m
                s = summary[key]
                if m["ambiguous"]:
                    s["ambiguous"] += 1
                elif m["mapping_status"] == "MISSING":
                    s["mapping_missing"] += 1
                else:
                    s["mapping_found"] += 1
                    if m["subloc_status"] == "OK":
                        s["subloc_present"] += 1
                    else:
                        s["subloc_missing"] += 1

            nmw, nma = per_store["NMW"], per_store["NMA"]

            def _issue(m, store_label):
                if m["ambiguous"]:
                    return f"AMBIGUOUS {store_label} MAPPING"
                if m["mapping_status"] == "MISSING":
                    return f"{store_label} MAPPING MISSING"
                if m["subloc_status"] == "MISSING":
                    return f"{store_label} SUBLOCATION MISSING"
                return None

            nmw_issue = _issue(nmw, "NMW")
            nma_issue = _issue(nma, "NMA")

            if nmw_issue is None and nma_issue is None:
                overall_flag = "OK"
                summary["fully_ok"] += 1
            elif nmw_issue and nma_issue and nmw_issue.endswith("MAPPING MISSING") and nma_issue.endswith("MAPPING MISSING"):
                overall_flag = "BOTH MAPPING MISSING"
            elif nmw_issue and nma_issue and nmw_issue.endswith("SUBLOCATION MISSING") and nma_issue.endswith("SUBLOCATION MISSING"):
                overall_flag = "BOTH SUBLOCATION MISSING"
            elif nmw_issue and nma_issue:
                overall_flag = f"{nmw_issue} + {nma_issue}"
            else:
                overall_flag = nmw_issue or nma_issue

            rows.append({
                "NMC_ProductCode": pc,
                "NMC_ProductName": p["ProductName"],
                "NMC_UnitDescription": p["UnitDescription"],
                "NMC_SubLocation": p["SubLocation"],
                "SourceDetection": p["SourceDetection"],
                "NMW_ProductCode": nmw["product_code"] or "",
                "NMW_ProductName": nmw["product_name"],
                "NMW_UnitDescription": nmw["unit_description"],
                "NMW_SubLocation": nmw["subloc"],
                "NMW_MappingStatus": "AMBIGUOUS" if nmw["ambiguous"] else nmw["mapping_status"],
                "NMA_ProductCode": nma["product_code"] or "",
                "NMA_ProductName": nma["product_name"],
                "NMA_UnitDescription": nma["unit_description"],
                "NMA_SubLocation": nma["subloc"],
                "NMA_MappingStatus": "AMBIGUOUS" if nma["ambiguous"] else nma["mapping_status"],
                "OverallFlag": overall_flag,
            })

        return rows, summary, target_dupes
    finally:
        conn.close()


# ------------------------------------------------------------------
# Output
# ------------------------------------------------------------------
def print_report(rows, summary, target_dupes):
    print("=== NMC OIN/Topical SubLocation Validation Report ===\n")
    print(f"Total NMC source products:            {summary['total']}")
    print(f"  Detected via UnitDescription:       {summary['via_unit']}")
    print(f"  Detected via ProductName fallback:  {summary['via_name_fallback']}")
    for store, key in (("NMW", "nmw"), ("NMA", "nma")):
        s = summary[key]
        print(f"\n{store}:")
        print(f"  Mapping found:      {s['mapping_found']}")
        print(f"  Mapping missing:    {s['mapping_missing']}")
        print(f"  SubLocation present:{s['subloc_present']}")
        print(f"  SubLocation missing:{s['subloc_missing']}")
        print(f"  Ambiguous mapping:  {s['ambiguous']}")
    print(f"\nFully OK (both stores): {summary['fully_ok']}")

    for store, dupes in target_dupes.items():
        print(f"\nWARNING: {len(dupes)} duplicate SupplierCode/SupplierProductCode "
              f"pairs in {store}'s SupplierProductMatch resolve to >1 ProductCode.")

    print("\n--- ProductName fallback samples (first 10) ---")
    fb = [r for r in rows if r["SourceDetection"] != "UNIT_OIN"][:10]
    for r in fb:
        print(f"  {r['NMC_ProductCode']} | {r['NMC_ProductName'][:35]:35s} | "
              f"UnitDesc={r['NMC_UnitDescription']!r} | {r['SourceDetection']}")

    print("\n--- NMC -> NMW sample mappings (first 10 MAPPED) ---")
    for r in [x for x in rows if x["NMW_MappingStatus"] == "MAPPED"][:10]:
        print(f"  NMC {r['NMC_ProductCode']} ({r['NMC_ProductName'][:24]}) -> "
              f"NMW {r['NMW_ProductCode']} loc={r['NMW_SubLocation']!r}")

    print("\n--- NMC -> NMA sample mappings (first 10 MAPPED) ---")
    for r in [x for x in rows if x["NMA_MappingStatus"] == "MAPPED"][:10]:
        print(f"  NMC {r['NMC_ProductCode']} ({r['NMC_ProductName'][:24]}) -> "
              f"NMA {r['NMA_ProductCode']} loc={r['NMA_SubLocation']!r}")

    print("\n--- Sample rows (first 15) ---")
    header = ["NMC Code", "Name", "Detect", "NMC Loc", "NMW Map", "NMW Loc", "NMA Map", "NMA Loc", "Flag"]
    print(" | ".join(header))
    for r in rows[:15]:
        print(" | ".join(str(v) for v in [
            r["NMC_ProductCode"], r["NMC_ProductName"][:22], r["SourceDetection"],
            r["NMC_SubLocation"], r["NMW_MappingStatus"], r["NMW_SubLocation"],
            r["NMA_MappingStatus"], r["NMA_SubLocation"], r["OverallFlag"],
        ]))


def export_xlsx(rows, summary, out_path):
    headers = [
        "NMC ProductCode", "NMC ProductName", "NMC UnitDescription", "NMC SubLocation", "SourceDetection",
        "NMW ProductCode", "NMW ProductName", "NMW UnitDescription", "NMW SubLocation", "NMW MappingStatus",
        "NMA ProductCode", "NMA ProductName", "NMA UnitDescription", "NMA SubLocation", "NMA MappingStatus",
        "Overall Flag",
    ]
    xlsx_rows = []
    for r in rows:
        if r["OverallFlag"] == "OK":
            hex_ = GREEN
        elif "MAPPING MISSING" in r["OverallFlag"] or "AMBIGUOUS" in r["OverallFlag"]:
            hex_ = RED
        else:
            hex_ = YELLOW
        values = [
            r["NMC_ProductCode"], r["NMC_ProductName"], r["NMC_UnitDescription"], r["NMC_SubLocation"], r["SourceDetection"],
            r["NMW_ProductCode"], r["NMW_ProductName"], r["NMW_UnitDescription"], r["NMW_SubLocation"], r["NMW_MappingStatus"],
            r["NMA_ProductCode"], r["NMA_ProductName"], r["NMA_UnitDescription"], r["NMA_SubLocation"], r["NMA_MappingStatus"],
            r["OverallFlag"],
        ]
        xlsx_rows.append((values, hex_))

    ncol = len(headers)
    summary_lines = [
        f"Total={summary['total']} (UnitDesc={summary['via_unit']}, NameFallback={summary['via_name_fallback']})",
        f"NMW: found={summary['nmw']['mapping_found']} missing={summary['nmw']['mapping_missing']} "
        f"loc_present={summary['nmw']['subloc_present']} loc_missing={summary['nmw']['subloc_missing']} "
        f"ambiguous={summary['nmw']['ambiguous']}",
        f"NMA: found={summary['nma']['mapping_found']} missing={summary['nma']['mapping_missing']} "
        f"loc_present={summary['nma']['subloc_present']} loc_missing={summary['nma']['subloc_missing']} "
        f"ambiguous={summary['nma']['ambiguous']}",
        f"Fully OK={summary['fully_ok']}",
    ]
    summary_rows = [
        ([line] + [""] * (ncol - 1), None) for line in summary_lines
    ]

    buf = table_xlsx(
        "NMC OIN/Topical SubLocation Validation Report",
        headers,
        summary_rows + xlsx_rows,
    )
    Path(out_path).write_bytes(buf.getvalue())
    print(f"\nWritten: {out_path}")


if __name__ == "__main__":
    rows, summary, target_dupes = build_report()
    print_report(rows, summary, target_dupes)
    out_path = sys.argv[1] if len(sys.argv) > 1 else "nmc_oin_sublocation_report.xlsx"
    export_xlsx(rows, summary, out_path)
