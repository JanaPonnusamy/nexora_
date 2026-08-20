"""One-off: set Products.SubLocation for shampoos on NMW.

- ProductName LIKE '%SHAMPOO%' AND actually tagged VET (contains '[VET]', '(VET)',
  or the standalone word VET -- excluding false positives like VETIVER/VETTIVER)
  -> SubLocation = 'Vet'
- All other SHAMPOO products -> SubLocation = 'SHAMP'

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

VET_COND = (
    "ProductName LIKE '%SHAMPOO%' AND ("
    "CHARINDEX('[VET]', ProductName) > 0 OR CHARINDEX('(VET)', ProductName) > 0 "
    "OR ProductName LIKE '% VET' OR ProductName LIKE '% VET %'"
    ") AND ProductName NOT LIKE '%VETIVER%' AND ProductName NOT LIKE '%VETTIVER%'"
)
OTHER_COND = (
    "ProductName LIKE '%SHAMPOO%' AND NOT ("
    + VET_COND.split("AND (", 1)[1]
)

vet_rows = cur.execute(f"SELECT ProductCode, ProductName, SubLocation FROM Products WHERE {VET_COND}").fetchall()
print(f"VET shampoo -> 'Vet': {len(vet_rows)}")
for r in vet_rows:
    print(f"  {r.ProductCode}  {r.ProductName!r}  {r.SubLocation} -> Vet")

other_count = cur.execute(
    f"SELECT COUNT(*) FROM Products WHERE ProductName LIKE '%SHAMPOO%' AND ProductCode NOT IN "
    f"(SELECT ProductCode FROM Products WHERE {VET_COND})"
).fetchval()
print(f"\nOther shampoo -> 'SHAMP': {other_count}")

if APPLY:
    cur.execute(f"UPDATE Products SET SubLocation = 'Vet' WHERE {VET_COND}")
    print(f"Updated (Vet) {cur.rowcount} rows.")
    cur.execute(
        f"UPDATE Products SET SubLocation = 'SHAMP' WHERE ProductName LIKE '%SHAMPOO%' "
        f"AND ProductCode NOT IN (SELECT ProductCode FROM Products WHERE {VET_COND})"
    )
    print(f"Updated (SHAMP) {cur.rowcount} rows.")
    conn.commit()
    print("Committed.")
else:
    print("\nPreview only (no changes made). Re-run with --apply to commit.")

conn.close()
