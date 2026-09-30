"""Export the NMC->NMW->NMA chain report: status per hop, codes, product name.

One-off report generator for reviewing the mapping chain used by
nmc_to_nma_discount_update.py -- not part of the update itself.
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

OUT_PATH = sys.argv[1] if len(sys.argv) > 1 else "nmw_chain_report.csv"

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

# Exclude NMW codes claimed by more than one NMA source (ambiguous)
nmw_candidates = defaultdict(set)
for nma_code, nmw_code, status, method in nma_to_nmw:
    nmw_candidates[nmw_code].add(nma_code)
ambiguous_nmw = {k for k, v in nmw_candidates.items() if len(v) > 1}

nmw_to_nma = {}
nma_info_by_nmw = {}
for nma_code, nmw_code, status, method in nma_to_nmw:
    if nmw_code in ambiguous_nmw:
        continue
    nmw_to_nma[nmw_code] = nma_code
    nma_info_by_nmw[nmw_code] = (status, method)

ccur = get_central_connection().cursor()
ccur.execute("SELECT ProductCode, ProductName FROM dbo.Products WHERE StoreName='NMW'")
nmw_names = {str(r[0]): r[1] for r in ccur.fetchall()}
ccur.execute("SELECT ProductCode, ProductName FROM dbo.Products WHERE StoreName='NMC'")
nmc_names = {str(r[0]): r[1] for r in ccur.fetchall()}

rows = []
for nmw_code, nmc_code, nmc_status, nmc_method in nmw_to_nmc:
    nma_code = nmw_to_nma.get(nmw_code)
    if not nma_code:
        continue
    nma_status, nma_method = nma_info_by_nmw[nmw_code]
    match_type = f"NMA-NMW:{nma_status}/{nma_method or '-'} | NMW-NMC:{nmc_status}/{nmc_method or '-'}"
    is_fuzzy = (nma_method or "").upper() == "FUZZY" or (nmc_method or "").upper() == "FUZZY"
    review_flag = "FUZZY - REVIEW" if is_fuzzy else "OK"
    rows.append([
        match_type,
        nmw_code,
        nmw_names.get(nmw_code, ""),
        nma_code,
        nmc_names.get(nmc_code, ""),
        review_flag,
    ])

with open(OUT_PATH, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["MatchType", "NMWProductCode", "ProductName", "NMAProductCode", "NMCProductName", "FuzzyCheck"])
    w.writerows(rows)

print(f"Wrote {len(rows)} rows to {OUT_PATH}")
