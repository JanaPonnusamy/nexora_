"""Full backup of dbo.Products (the real, live central store DB -- OrderNMC,
NOT NEXORA_PLATFORM) to a timestamped CSV, before the NMC->NMA discount +
unit-description update.

All stores, all columns, all rows -- a straight dump, not filtered to NMA.
"""
import csv
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.legacy_order.database import get_central_connection

OUT_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(r"D:\VBDOTNET\nmw\Discount Update")
OUT_DIR.mkdir(parents=True, exist_ok=True)
stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
out_path = OUT_DIR / f"Products_backup_{stamp}.csv"

conn = get_central_connection()
cur = conn.cursor()
cur.execute("SELECT DB_NAME()")
print("Backing up dbo.Products from central DB:", cur.fetchone()[0])

cur.execute("SELECT * FROM dbo.Products")
cols = [c[0] for c in cur.description]

count = 0
with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(cols)
    while True:
        batch = cur.fetchmany(5000)
        if not batch:
            break
        w.writerows(batch)
        count += len(batch)

print(f"Wrote {count} rows, {len(cols)} columns to {out_path}")
