"""One-off: set Products.SubLocation = 'SUGR' (surgical) for walking sticks on NMW.

Run with --apply to actually commit; without it, only previews counts.
"""
import sys

from modules.legacy_order import database, repository

APPLY = "--apply" in sys.argv

store = repository.get_store("NMW")
if not store:
    raise SystemExit("Store 'NMW' not found in central Stores table")

conn = database.get_branch_connection(
    store["server_name"], store["database"], store["username"], store["password"]
)
cur = conn.cursor()

COND = "ProductName LIKE '%WALKING STICK%'"

count = cur.execute(f"SELECT COUNT(*) FROM Products WHERE {COND}").fetchval()
print(f"Products matching '%WALKING STICK%': {count}")

sample = cur.execute(
    f"SELECT ProductCode, ProductName, SubLocation FROM Products WHERE {COND}"
).fetchall()
for row in sample:
    print(f"  {row.ProductCode}  {row.ProductName!r}  {row.SubLocation} -> SUGR")

if APPLY:
    cur.execute(f"UPDATE Products SET SubLocation = 'SUGR' WHERE {COND}")
    print(f"Updated {cur.rowcount} rows.")
    conn.commit()
    print("Committed.")
else:
    print("Preview only (no changes made). Re-run with --apply to commit.")

conn.close()
