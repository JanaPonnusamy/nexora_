"""Apply the NMC-fuzzy-matched discount values from
_nma_discount_range_margin_nmc_check.py onto NMA's LIVE store DB.

Rule: NMA_DefaultDiscount / NMA_MaxProductDiscount <- NMC's matched value;
if NMC has no match or a NULL discount ("NO MATCH" / "NMC DISCOUNT MISSING"),
treat the source value as 0.

Re-derives the same 1,111-row set fresh (same query/matching logic as the
report script) rather than trusting the CSV, then writes to dbo.Products on
NMA's live DB inside a single transaction, verifies the affected count, and
produces a before/after CSV report.

ALWAYS back up NMA's live Products table first (_backup_live_store_products.py NMA).
"""
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from rapidfuzz import fuzz

import _live_store_conn as live

REPORT_OUT = sys.argv[1] if len(sys.argv) > 1 else r"D:\VBDOTNET\nmw\Discount Update\NMA_discount_range_nmc_update_result.csv"


def normalize(name):
    name = (name or "").upper()
    name = re.sub(r"[^A-Z0-9 ]", " ", name)
    return re.sub(r"\s+", " ", name).strip()


def first_word(norm_name):
    return norm_name.split(" ", 1)[0] if norm_name else ""


nma_conn = live.connect("NMA")
nma_cur = nma_conn.cursor()
nma_cur.execute(
    """SELECT ProductCode, ProductName, DefaultDiscountPercentage, DiscountPerAllowInBill
       FROM dbo.Products
       WHERE DefaultDiscountPercentage BETWEEN 6 AND 7
          OR DefaultDiscountPercentage BETWEEN 11 AND 13"""
)
nma_rows = nma_cur.fetchall()

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

plan = []
for code, name, disc, maxdisc in nma_rows:
    disc_range = "11-13" if disc is not None and 11 <= float(disc) <= 13 else "6-7"
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
    else:
        nmc_code = nmc_name = nmc_disc = nmc_max = None

    new_disc = float(nmc_disc) if nmc_disc is not None else 0.0
    new_max = float(nmc_max) if nmc_max is not None else 0.0

    plan.append({
        "disc_range": disc_range, "code": code, "name": name,
        "old_discount": disc, "new_discount": new_disc,
        "old_max": maxdisc, "new_max": new_max,
        "nmc_code": nmc_code, "nmc_name": nmc_name, "fuzzy_score": best_score,
    })

print(f"Plan built: {len(plan)} rows")

cur = nma_conn.cursor()
updated = []
try:
    for r in plan:
        cur.execute(
            """UPDATE dbo.Products
               SET DefaultDiscountPercentage = ?, DiscountPerAllowInBill = ?
               OUTPUT inserted.ProductCode
               WHERE ProductCode = ?""",
            r["new_discount"], r["new_max"], r["code"],
        )
        row = cur.fetchone()
        if row:
            updated.append(r)

    print(f"UPDATE executed inside transaction: {len(updated)} row(s) affected")
    if len(updated) != len(plan):
        print(f"MISMATCH: planned {len(plan)} but affected {len(updated)}. Rolling back.")
        nma_conn.rollback()
        sys.exit(1)

    nma_conn.commit()
    print("COMMITTED.")
except Exception:
    nma_conn.rollback()
    raise

with open(REPORT_OUT, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow([
        "DiscountRange", "ProductCode", "ProductName",
        "OldDefaultDiscount", "NewDefaultDiscount",
        "OldMaxProductDiscount", "NewMaxProductDiscount",
        "NMC_MatchedCode", "NMC_MatchedName", "FuzzyScore",
    ])
    for r in updated:
        w.writerow([
            r["disc_range"], r["code"], r["name"],
            r["old_discount"], r["new_discount"],
            r["old_max"], r["new_max"],
            r["nmc_code"], r["nmc_name"], r["fuzzy_score"],
        ])

print(f"Wrote {len(updated)} rows to {REPORT_OUT}")
