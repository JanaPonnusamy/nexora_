"""Full backup of a store's OWN live Products table (direct connection to
the store's own SQL Server, not OrderNMC / not NEXORA_PLATFORM) to a
timestamped CSV, before writing to it.

Usage:
    backend/.venv/Scripts/python backend/scripts/_backup_live_store_products.py NMA
"""
import csv
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _live_store_conn as live

STORE_CODE = sys.argv[1] if len(sys.argv) > 1 else "NMA"
OUT_DIR = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(r"D:\VBDOTNET\nmw\Discount Update")
OUT_DIR.mkdir(parents=True, exist_ok=True)
stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
out_path = OUT_DIR / f"{STORE_CODE}_live_Products_backup_{stamp}.csv"

conn = live.connect(STORE_CODE)
cur = conn.cursor()
cur.execute("SELECT DB_NAME()")
db_name = cur.fetchone()[0]
print(f"Backing up dbo.Products from {STORE_CODE}'s live store DB: {db_name}")

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
