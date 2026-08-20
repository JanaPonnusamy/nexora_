"""One-off: correct Products.SubLocation on the NMW branch DB for CREAM products.

The blanket TAB fill wrongly set SubLocation = 'TAB ' + first letter for creams.
Creams have a UnitDescription (OIN/LOT/CON/POW/etc.) that is the real category --
use that + first letter instead. Where UnitDescription is NULL/blank (no reliable
signal), set SubLocation back to NULL rather than guessing.

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

print("Breakdown by UnitDescription for '%CREAM%' products:")
for row in cur.execute(
    "SELECT UnitDescription, COUNT(*) c FROM Products WHERE ProductName LIKE '%CREAM%' "
    "GROUP BY UnitDescription ORDER BY c DESC"
).fetchall():
    print(" ", row.UnitDescription, row.c)

known_count = cur.execute(
    "SELECT COUNT(*) FROM Products WHERE ProductName LIKE '%CREAM%' "
    "AND UnitDescription IS NOT NULL AND LTRIM(RTRIM(UnitDescription)) <> ''"
).fetchval()
unknown_count = cur.execute(
    "SELECT COUNT(*) FROM Products WHERE ProductName LIKE '%CREAM%' "
    "AND (UnitDescription IS NULL OR LTRIM(RTRIM(UnitDescription)) = '')"
).fetchval()
print(f"\nKnown UnitDescription -> will set SubLocation = UnitDescription + letter: {known_count}")
print(f"Unknown UnitDescription -> will set SubLocation = NULL: {unknown_count}")

sample = cur.execute(
    "SELECT TOP 10 ProductCode, ProductName, UnitDescription, SubLocation, "
    "RTRIM(UnitDescription) + ' ' + LEFT(ProductName, 1) AS NewSubLocation "
    "FROM Products WHERE ProductName LIKE '%CREAM%' "
    "AND UnitDescription IS NOT NULL AND LTRIM(RTRIM(UnitDescription)) <> ''"
).fetchall()
for row in sample:
    print(f"  {row.ProductCode}  {row.ProductName!r}  {row.SubLocation} -> {row.NewSubLocation}")

if APPLY:
    cur.execute(
        "UPDATE Products SET SubLocation = RTRIM(UnitDescription) + ' ' + LEFT(ProductName, 1) "
        "WHERE ProductName LIKE '%CREAM%' "
        "AND UnitDescription IS NOT NULL AND LTRIM(RTRIM(UnitDescription)) <> ''"
    )
    print(f"Updated (known) {cur.rowcount} rows.")
    cur.execute(
        "UPDATE Products SET SubLocation = NULL "
        "WHERE ProductName LIKE '%CREAM%' "
        "AND (UnitDescription IS NULL OR LTRIM(RTRIM(UnitDescription)) = '')"
    )
    print(f"Updated (unknown -> NULL) {cur.rowcount} rows.")
    conn.commit()
    print("Committed.")
else:
    print("\nPreview only (no changes made). Re-run with --apply to commit.")

conn.close()
