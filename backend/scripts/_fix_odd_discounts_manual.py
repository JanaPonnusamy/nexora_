"""Manual discount correction for the 7 odd-value NMA products (1, 6, 7.81, 8)
per explicit user-supplied target values.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _live_store_conn as live

conn = live.connect("NMA")
cur = conn.cursor()

plan = [
    (5885371, 10, 18),
    (5882049, 10, 18),
    (5872431, 0, 0),
    (5875197, 0, 0),
    (5867411, 10, 18),
    (22114, 0, 0),
    (5870554, 0, 0),
]

updated = []
try:
    for code, new_disc, new_max in plan:
        cur.execute(
            """UPDATE dbo.Products SET DefaultDiscountPercentage=?, DiscountPerAllowInBill=?
               OUTPUT deleted.ProductCode, deleted.ProductName, deleted.DefaultDiscountPercentage, deleted.DiscountPerAllowInBill,
                      inserted.DefaultDiscountPercentage, inserted.DiscountPerAllowInBill
               WHERE ProductCode=?""",
            new_disc, new_max, code,
        )
        row = cur.fetchone()
        if row:
            updated.append(row)

    if len(updated) != len(plan):
        print(f"MISMATCH: expected {len(plan)}, affected {len(updated)}. Rolling back.")
        conn.rollback()
        sys.exit(1)

    conn.commit()
    print(f"COMMITTED: {len(updated)} rows updated")
    for r in updated:
        print(r)
except Exception:
    conn.rollback()
    raise
