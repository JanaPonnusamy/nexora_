"""One-off: update Products.SubLocation on the NMW branch DB based on PurchaseTrans.SupplierCode.

- SupplierCode = 1388  -> SubLocation = 'EYRUS'
- SupplierCode IN (40, 35) -> SubLocation = 'Vet'

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

updates = [
    ("EYRUS", "pt.SupplierCode = '1388'"),
    ("Vet", "pt.SupplierCode IN ('40', '35')"),
]

for sublocation, condition in updates:
    count = cur.execute(
        f"""
        SELECT COUNT(DISTINCT p.ProductCode)
        FROM Products p
        INNER JOIN PurchaseTrans pt ON pt.ProductCode = p.ProductCode
        WHERE {condition}
        """
    ).fetchval()
    print(f"SubLocation='{sublocation}' ({condition}): {count} distinct products match")

    if APPLY:
        cur.execute(
            f"""
            UPDATE p
            SET p.SubLocation = ?
            FROM Products p
            INNER JOIN PurchaseTrans pt ON pt.ProductCode = p.ProductCode
            WHERE {condition}
            """,
            sublocation,
        )
        print(f"  -> updated {cur.rowcount} rows")

if APPLY:
    conn.commit()
    print("Committed.")
else:
    print("Preview only (no changes made). Re-run with --apply to commit.")

conn.close()
