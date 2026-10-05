"""Export NMW<->NMC common matches with product name, match check, and discount fields.

Discount fields: DefaultDiscountPercentage ("DefaultDiscount") and
DiscountPerAllowInBill ("MaxProductDiscount") -- confirmed via sample data
that DiscountPerAllowInBill is consistently >= DefaultDiscountPercentage
(e.g. 18 vs 10), i.e. it is the max discount allowed per bill while
DefaultDiscountPercentage is the default applied discount.

One-off report generator -- not part of the discount update script.
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.database import get_connection as get_platform_connection
from modules.legacy_order.database import get_central_connection

NMW = "DEB4780E-CA8D-4CCD-9942-3ACE1CC88EE0"
NMC = "FCBE8B35-B1A1-463E-80C6-73161CDC8F32"

OUT_PATH = sys.argv[1] if len(sys.argv) > 1 else "nmw_nmc_discount_check.csv"

pconn = get_platform_connection()
pcur = pconn.cursor()
pcur.execute(
    """SELECT source_product_code, target_product_code, status, match_method
       FROM dbo.product_mapping
       WHERE source_store_id=? AND target_store_id=? AND is_deleted=0
         AND status IN ('APPROVED','AUTO')""",
    NMW, NMC,
)
nmw_to_nmc = pcur.fetchall()  # (NmwCode, NmcCode, Status, MatchMethod)

ccur = get_central_connection().cursor()
ccur.execute(
    """SELECT ProductCode, ProductName, DefaultDiscountPercentage, DiscountPerAllowInBill
       FROM dbo.Products WHERE StoreName='NMW'"""
)
nmw_products = {str(r[0]): (r[1], r[2], r[3]) for r in ccur.fetchall()}
ccur.execute(
    """SELECT ProductCode, ProductName, DefaultDiscountPercentage, DiscountPerAllowInBill
       FROM dbo.Products WHERE StoreName='NMC'"""
)
nmc_products = {str(r[0]): (r[1], r[2], r[3]) for r in ccur.fetchall()}

rows = []
for nmw_code, nmc_code, status, method in nmw_to_nmc:
    nw = nmw_products.get(nmw_code)
    nc = nmc_products.get(nmc_code)
    if nw is None or nc is None:
        continue
    nw_name, nw_default, nw_max = nw
    nc_name, nc_default, nc_max = nc
    match_type = f"{status}/{method or '-'}"
    fuzzy_check = "FUZZY - REVIEW" if (method or "").upper() == "FUZZY" else "OK"
    rows.append([
        match_type,
        nmw_code, nw_name,
        nmc_code, nc_name,
        nw_default, nw_max,
        nc_default, nc_max,
        fuzzy_check,
    ])

with open(OUT_PATH, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow([
        "MatchType",
        "NMWProductCode", "NMWProductName",
        "NMCProductCode", "NMCProductName",
        "NMW_DefaultDiscount", "NMW_MaxProductDiscount",
        "NMC_DefaultDiscount", "NMC_MaxProductDiscount",
        "FuzzyCheck",
    ])
    w.writerows(rows)

print(f"Wrote {len(rows)} rows to {OUT_PATH}")
