"""NMA discount-range report (11-13 and 6-7) enriched with current stock,
latest-batch margin, and an independent NMC cross-check via first-word +
rapidfuzz name matching (NOT the reviewed product_mapping table -- this is a
separate ad-hoc verification pass to catch anything the mapping-based chain
might have missed).

Margin% = (LatestBatchMRP - LatestBatchPurchasePrice) / LatestBatchMRP * 100,
using dbo.dvw_LatestBatchInfo (one row per ProductCode = latest batch).

Both NMA and NMC connections are direct to the LIVE per-store SQL Servers
(via _live_store_conn); NMC is read-only here.
"""
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from rapidfuzz import fuzz

import _live_store_conn as live

OUT_PATH = sys.argv[1] if len(sys.argv) > 1 else r"D:\VBDOTNET\nmw\Discount Update\NMA_discount_range_margin_nmc_check.csv"
LOW1, HIGH1 = (float(sys.argv[2]), float(sys.argv[3])) if len(sys.argv) > 3 else (6.5, 7)
LOW2, HIGH2 = (float(sys.argv[4]), float(sys.argv[5])) if len(sys.argv) > 5 else (11.25, 13)


def normalize(name):
    name = (name or "").upper()
    name = re.sub(r"[^A-Z0-9 ]", " ", name)
    return re.sub(r"\s+", " ", name).strip()


def first_word(norm_name):
    return norm_name.split(" ", 1)[0] if norm_name else ""


nma_conn = live.connect("NMA")
nma_cur = nma_conn.cursor()
nma_cur.execute(
    """SELECT ProductCode, ProductName, TotalStock, DefaultDiscountPercentage,
              DiscountPerAllowInBill, UnitDescription
       FROM dbo.Products
       WHERE DefaultDiscountPercentage BETWEEN ? AND ?
          OR DefaultDiscountPercentage BETWEEN ? AND ?""",
    LOW1, HIGH1, LOW2, HIGH2,
)
nma_rows = nma_cur.fetchall()

nma_cur.execute("SELECT ProductCode, MRP, PurchasePrice FROM dbo.dvw_LatestBatchInfo")
latest_batch = {r[0]: (r[1], r[2]) for r in nma_cur.fetchall()}

nmc_conn = live.connect("NMC")
nmc_cur = nmc_conn.cursor()
nmc_cur.execute(
    """SELECT ProductCode, ProductName, DefaultDiscountPercentage, DiscountPerAllowInBill
       FROM dbo.Products WHERE ISNULL(isActive, 1) = 1"""
)
nmc_products = nmc_cur.fetchall()

nmc_buckets = {}
for code, name, disc, maxdisc in nmc_products:
    norm = normalize(name)
    fw = first_word(norm)
    nmc_buckets.setdefault(fw, []).append((code, name, norm, disc, maxdisc))

rows_out = []
for code, name, stock, disc, maxdisc, unit in nma_rows:
    disc_range = f"{LOW2}-{HIGH2}" if disc is not None and LOW2 <= float(disc) <= HIGH2 else f"{LOW1}-{HIGH1}"

    mrp, ptr = latest_batch.get(code, (None, None))
    if mrp and ptr is not None and mrp != 0:
        margin_pct = round((float(mrp) - float(ptr)) / float(mrp) * 100, 2)
    else:
        margin_pct = None

    norm_name = normalize(name)
    fw = first_word(norm_name)
    candidates = nmc_buckets.get(fw, [])
    best = None
    best_score = 0
    for c_code, c_name, c_norm, c_disc, c_max in candidates:
        score = fuzz.token_sort_ratio(norm_name, c_norm)
        if score > best_score:
            best_score = score
            best = (c_code, c_name, c_disc, c_max)

    if best and best_score >= 60:
        nmc_code, nmc_name, nmc_disc, nmc_max = best
        if nmc_disc is None:
            check = "NMC DISCOUNT MISSING"
        elif float(nmc_disc) == float(disc or 0):
            check = "SAME"
        else:
            check = "DIFFERS"
    else:
        nmc_code = nmc_name = nmc_disc = nmc_max = None
        best_score = 0
        check = "NO MATCH"

    rows_out.append([
        disc_range, code, name, stock, disc, maxdisc, unit,
        mrp, ptr, margin_pct,
        nmc_code, nmc_name, nmc_disc, nmc_max, best_score, check,
    ])

with open(OUT_PATH, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow([
        "DiscountRange", "ProductCode", "ProductName", "CurrentStock",
        "NMA_DefaultDiscount", "NMA_MaxProductDiscount", "UnitDescription",
        "LatestBatchMRP", "LatestBatchPTR", "MarginPercent",
        "NMC_MatchedCode", "NMC_MatchedName", "NMC_DefaultDiscount", "NMC_MaxProductDiscount",
        "FuzzyScore", "DiscountCheck",
    ])
    w.writerows(rows_out)

print(f"Wrote {len(rows_out)} rows to {OUT_PATH}")
from collections import Counter
print("DiscountCheck breakdown:", Counter(r[-1] for r in rows_out))
