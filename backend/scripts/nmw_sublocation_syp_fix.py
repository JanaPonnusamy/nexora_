"""One-off: correct Products.SubLocation on the NMW branch DB for syrups.

The blanket TAB fill (nmw_sublocation_tab_fill.py) set SubLocation = 'TAB ' + first
letter for every product with a NULL SubLocation, including syrups. This corrects
those: where ProductName LIKE '%SYP%', set SubLocation = 'SYP ' + first letter of
ProductName.

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
    "SELECT COUNT(*) FROM Products WHERE ProductName LIKE '%SYP%'"
).fetchval()
print(f"Products matching '%SYP%': {count}")

sample = cur.execute(
    "SELECT TOP 10 ProductCode, ProductName, SubLocation, 'SYP ' + LEFT(ProductName, 1) AS NewSubLocation "
    "FROM Products WHERE ProductName LIKE '%SYP%'"
).fetchall()
for row in sample:
    print(f"  {row.ProductCode}  {row.ProductName!r}  {row.SubLocation} -> {row.NewSubLocation}")

if APPLY:
    cur.execute(
        "UPDATE Products SET SubLocation = 'SYP ' + LEFT(ProductName, 1) "
        "WHERE ProductName LIKE '%SYP%'"
    )
    print(f"Updated {cur.rowcount} rows.")
    conn.commit()
    print("Committed.")
else:
    print("Preview only (no changes made). Re-run with --apply to commit.")

conn.close()
