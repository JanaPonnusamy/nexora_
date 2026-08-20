"""One-off: set Products.SubLocation = 'SYP ' + first letter for NMW products
whose UnitDescription = 'SYP', wherever the SubLocation doesn't already reflect it
(NULL from the TAB revert, or wrongly something else like 'DROPS'/'TAB x').

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
    "SELECT COUNT(*) FROM Products WHERE UnitDescription = 'SYP'"
).fetchval()
print(f"Products with UnitDescription = 'SYP': {count}")

sample = cur.execute(
    "SELECT TOP 15 ProductCode, ProductName, SubLocation, "
    "'SYP ' + LEFT(ProductName, 1) AS NewSubLocation "
    "FROM Products WHERE UnitDescription = 'SYP'"
).fetchall()
for row in sample:
    print(f"  {row.ProductCode}  {row.ProductName!r}  {row.SubLocation} -> {row.NewSubLocation}")

if APPLY:
    cur.execute(
        "UPDATE Products SET SubLocation = 'SYP ' + LEFT(ProductName, 1) "
        "WHERE UnitDescription = 'SYP'"
    )
    print(f"Updated {cur.rowcount} rows.")
    conn.commit()
    print("Committed.")
else:
    print("Preview only (no changes made). Re-run with --apply to commit.")

conn.close()
