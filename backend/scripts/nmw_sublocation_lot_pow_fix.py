"""One-off: set Products.SubLocation on NMW for products still NULL whose
UnitDescription is 'LOT' (lotion) or 'POW' (powder) -> SubLocation = UnitDescription
+ ' ' + first letter of ProductName (e.g. 'LOT C', 'POW C').

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

COND = "SubLocation IS NULL AND UnitDescription IN ('LOT', 'POW')"

count = cur.execute(f"SELECT COUNT(*) FROM Products WHERE {COND}").fetchval()
print(f"NULL-SubLocation products with UnitDescription LOT/POW: {count}")

sample = cur.execute(
    f"SELECT TOP 20 ProductCode, ProductName, UnitDescription, "
    f"RTRIM(UnitDescription) + ' ' + LEFT(ProductName, 1) AS NewSubLocation "
    f"FROM Products WHERE {COND}"
).fetchall()
for row in sample:
    print(f"  {row.ProductCode}  {row.ProductName!r}  UnitDesc={row.UnitDescription} -> {row.NewSubLocation}")

if APPLY:
    cur.execute(
        f"UPDATE Products SET SubLocation = RTRIM(UnitDescription) + ' ' + LEFT(ProductName, 1) "
        f"WHERE {COND}"
    )
    print(f"Updated {cur.rowcount} rows.")
    conn.commit()
    print("Committed.")
else:
    print("Preview only (no changes made). Re-run with --apply to commit.")

conn.close()
