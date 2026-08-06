"""One-off: set Products.SubLocation = 'NS' for all NASAL SPRAY products on NMW.

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

count = cur.execute(
    "SELECT COUNT(*) FROM Products WHERE ProductName LIKE '%NASAL SPRAY%'"
).fetchval()
print(f"Products matching '%NASAL SPRAY%': {count}")

sample = cur.execute(
    "SELECT ProductCode, ProductName, SubLocation FROM Products WHERE ProductName LIKE '%NASAL SPRAY%'"
).fetchall()
for row in sample:
    print(f"  {row.ProductCode}  {row.ProductName!r}  {row.SubLocation} -> NS")

if APPLY:
    cur.execute(
        "UPDATE Products SET SubLocation = 'NS' WHERE ProductName LIKE '%NASAL SPRAY%'"
    )
    print(f"Updated {cur.rowcount} rows.")
    conn.commit()
    print("Committed.")
else:
    print("Preview only (no changes made). Re-run with --apply to commit.")

conn.close()
