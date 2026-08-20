"""One-off: set Products.SubLocation = 'SOAP' for all soap products on NMW.

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
    "SELECT COUNT(*) FROM Products WHERE ProductName LIKE '%SOAP%'"
).fetchval()
print(f"Products matching '%SOAP%': {count}")

sample = cur.execute(
    "SELECT TOP 15 ProductCode, ProductName, SubLocation FROM Products WHERE ProductName LIKE '%SOAP%'"
).fetchall()
for row in sample:
    print(f"  {row.ProductCode}  {row.ProductName!r}  {row.SubLocation} -> SOAP")

if APPLY:
    cur.execute(
        "UPDATE Products SET SubLocation = 'SOAP' WHERE ProductName LIKE '%SOAP%'"
    )
    print(f"Updated {cur.rowcount} rows.")
    conn.commit()
    print("Committed.")
else:
    print("Preview only (no changes made). Re-run with --apply to commit.")

conn.close()
