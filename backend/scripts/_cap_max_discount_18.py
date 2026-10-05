"""Cap NMA's DiscountPerAllowInBill (max discount) at 18 for every product
currently above it. DefaultDiscountPercentage is untouched.
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _live_store_conn as live

conn = live.connect("NMA")
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM dbo.Products WHERE DiscountPerAllowInBill > 18")
expected = cur.fetchone()[0]
print("Rows to update:", expected)

cur.execute(
    """UPDATE dbo.Products SET DiscountPerAllowInBill = 18
       OUTPUT deleted.ProductCode, deleted.ProductName, deleted.DiscountPerAllowInBill, inserted.DiscountPerAllowInBill
       WHERE DiscountPerAllowInBill > 18"""
)
updated = cur.fetchall()

if len(updated) != expected:
    print(f"MISMATCH: expected {expected}, affected {len(updated)}. Rolling back.")
    conn.rollback()
    sys.exit(1)

conn.commit()
print(f"COMMITTED: {len(updated)} rows updated")

out_path = r"D:\VBDOTNET\nmw\Discount Update\NMA_max_discount_capped_18_result.csv"
with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["ProductCode", "ProductName", "OldMaxProductDiscount", "NewMaxProductDiscount"])
    w.writerows(updated)
print(f"Wrote {len(updated)} rows to {out_path}")
