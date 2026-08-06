"""One-off: fill blank Products.SubLocation on the NMW branch DB.

Where SubLocation IS NULL, set SubLocation = 'TAB ' + first letter of ProductName
(e.g. a product named "Amoxicillin" -> 'TAB A').

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
    "SELECT COUNT(*) FROM Products WHERE SubLocation IS NULL AND LEFT(ProductName, 1) IS NOT NULL"
).fetchval()
print(f"Products with SubLocation IS NULL: {count}")

sample = cur.execute(
    "SELECT TOP 10 ProductCode, ProductName, 'TAB ' + LEFT(ProductName, 1) AS NewSubLocation "
    "FROM Products WHERE SubLocation IS NULL"
).fetchall()
for row in sample:
    print(f"  {row.ProductCode}  {row.ProductName!r} -> {row.NewSubLocation}")

if APPLY:
    cur.execute(
        "UPDATE Products SET SubLocation = 'TAB ' + LEFT(ProductName, 1) "
        "WHERE SubLocation IS NULL"
    )
    print(f"Updated {cur.rowcount} rows.")
    conn.commit()
    print("Committed.")
else:
    print("Preview only (no changes made). Re-run with --apply to commit.")

conn.close()
