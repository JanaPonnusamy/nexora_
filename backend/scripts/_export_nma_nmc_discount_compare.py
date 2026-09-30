"""Final NMA vs NMC discount comparison, chained through NMW as the join key.

NMW is used only as middleware to link NMA and NMC product identities
(NMA<->NMW and NMW<->NMC are both matched, so NMC<->NMA can be resolved
through it) -- NMW itself carries no discount data (confirmed: 0 of 31,665
NMW products have DefaultDiscountPercentage/DiscountPerAllowInBill set), so
none of its columns appear in the output.

Ambiguity safety (same as nmc_to_nma_discount_update.py):
  - NMW codes claimed by more than one NMA source are excluded.
  - NMC codes that would resolve to more than one distinct NMA code through
    the chain are excluded.

One-off report generator -- not part of the discount update script.
"""
import csv
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.database import get_connection as get_platform_connection
from modules.legacy_order.database import get_central_connection

NMW = "DEB4780E-CA8D-4CCD-9942-3ACE1CC88EE0"
NMA = "109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1"
NMC = "FCBE8B35-B1A1-463E-80C6-73161CDC8F32"

OUT_PATH = sys.argv[1] if len(sys.argv) > 1 else "nma_nmc_discount_compare.csv"

pconn = get_platform_connection()
pcur = pconn.cursor()

pcur.execute(
    """SELECT source_product_code, target_product_code, status, match_method
       FROM dbo.product_mapping
       WHERE source_store_id=? AND target_store_id=? AND is_deleted=0
         AND status IN ('APPROVED','AUTO')""",
    NMA, NMW,
)
nma_to_nmw = pcur.fetchall()  # (NmaCode, NmwCode, Status, MatchMethod)

pcur.execute(
    """SELECT source_product_code, target_product_code, status, match_method
       FROM dbo.product_mapping
       WHERE source_store_id=? AND target_store_id=? AND is_deleted=0
         AND status IN ('APPROVED','AUTO')""",
    NMW, NMC,
)
nmw_to_nmc = pcur.fetchall()  # (NmwCode, NmcCode, Status, MatchMethod)

# NMW codes claimed by more than one NMA source -> ambiguous, exclude
nmw_candidates = defaultdict(set)
for nma_code, nmw_code, status, method in nma_to_nmw:
    nmw_candidates[nmw_code].add(nma_code)
ambiguous_nmw = {k for k, v in nmw_candidates.items() if len(v) > 1}

nmw_to_nma_info = {}
for nma_code, nmw_code, status, method in nma_to_nmw:
    if nmw_code in ambiguous_nmw:
        continue
    nmw_to_nma_info[nmw_code] = (nma_code, status, method)

# Build NMC -> NMA candidates through NMW, keep only unambiguous chains
chain_candidates = defaultdict(set)
chain_info = {}
for nmw_code, nmc_code, nmc_status, nmc_method in nmw_to_nmc:
    info = nmw_to_nma_info.get(nmw_code)
    if not info:
        continue
    nma_code, nma_status, nma_method = info
    chain_candidates[nmc_code].add(nma_code)
    chain_info[(nmc_code, nma_code)] = (nma_status, nma_method, nmc_status, nmc_method, nmw_code)

ambiguous_nmc = {k for k, v in chain_candidates.items() if len(v) > 1}

ccur = get_central_connection().cursor()
ccur.execute(
    """SELECT ProductCode, ProductName, DefaultDiscountPercentage, DiscountPerAllowInBill
       FROM dbo.Products WHERE StoreName='NMA'"""
)
nma_products = {str(r[0]): (r[1], r[2], r[3]) for r in ccur.fetchall()}
ccur.execute(
    """SELECT ProductCode, ProductName, DefaultDiscountPercentage, DiscountPerAllowInBill
       FROM dbo.Products WHERE StoreName='NMC'"""
)
nmc_products = {str(r[0]): (r[1], r[2], r[3]) for r in ccur.fetchall()}

rows = []
for nmc_code, nma_codes in chain_candidates.items():
    if nmc_code in ambiguous_nmc:
        continue
    nma_code = next(iter(nma_codes))
    nma_status, nma_method, nmc_status, nmc_method, nmw_code = chain_info[(nmc_code, nma_code)]

    na = nma_products.get(nma_code)
    nc = nmc_products.get(nmc_code)
    if na is None or nc is None:
        continue
    na_name, na_default, na_max = na
    nc_name, nc_default, nc_max = nc

    match_type = f"NMA-NMW:{nma_status}/{nma_method or '-'} | NMW-NMC:{nmc_status}/{nmc_method or '-'}"
    is_fuzzy = (nma_method or "").upper() == "FUZZY" or (nmc_method or "").upper() == "FUZZY"
    fuzzy_check = "FUZZY - REVIEW" if is_fuzzy else "OK"

    nc_default_v = float(nc_default) if nc_default is not None else None
    na_default_v = float(na_default) if na_default is not None else None
    if nc_default_v is None or na_default_v is None:
        discount_status = "MISSING DATA"
    elif abs(nc_default_v - na_default_v) < 0.0001:
        discount_status = "SAME"
    else:
        discount_status = "DIFFERS"

    rows.append([
        match_type,
        nmw_code,
        nmc_code, nc_name,
        nma_code, na_name,
        nc_default, nc_max,
        na_default, na_max,
        discount_status,
        fuzzy_check,
    ])

with open(OUT_PATH, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow([
        "MatchType", "NMWProductCode (bridge)",
        "NMCProductCode", "NMCProductName",
        "NMAProductCode", "NMAProductName",
        "NMC_DefaultDiscount", "NMC_MaxProductDiscount",
        "NMA_DefaultDiscount", "NMA_MaxProductDiscount",
        "DiscountStatus", "FuzzyCheck",
    ])
    w.writerows(rows)

print(f"Wrote {len(rows)} rows to {OUT_PATH}")
