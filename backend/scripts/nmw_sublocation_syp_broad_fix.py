"""One-off: set Products.SubLocation = 'SYP ' + first letter on NMW for any
product where ProductName contains 'SYP' or 'SUS' (substring, anywhere) OR
UnitDescription = 'SYP'.

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

COND = (
    "(ProductName LIKE '%SYP%' OR ProductName LIKE '%SUS%' OR UnitDescription = 'SYP')"
)

count = cur.execute(f"SELECT COUNT(*) FROM Products WHERE {COND}").fetchval()
print(f"Products matching SYP/SUS rule: {count}")

sample = cur.execute(
    f"SELECT TOP 20 ProductCode, ProductName, UnitDescription, SubLocation, "
    f"'SYP ' + LEFT(ProductName, 1) AS NewSubLocation FROM Products WHERE {COND}"
).fetchall()
for row in sample:
    print(f"  {row.ProductCode}  {row.ProductName!r}  UnitDesc={row.UnitDescription}  {row.SubLocation} -> {row.NewSubLocation}")

if APPLY:
    cur.execute(
        f"UPDATE Products SET SubLocation = 'SYP ' + LEFT(ProductName, 1) WHERE {COND}"
    )
    print(f"Updated {cur.rowcount} rows.")
    conn.commit()
    print("Committed.")
else:
    print("Preview only (no changes made). Re-run with --apply to commit.")

conn.close()
