"""One-off: for NMW products still SubLocation IS NULL, set SubLocation =
UnitDescription + ' ' + first letter of ProductName, wherever UnitDescription
is populated (mirrors the CREAM/LOT/POW/SYP treatment, generalized to every
remaining UnitDescription value).

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

COND = "SubLocation IS NULL AND UnitDescription IS NOT NULL AND LTRIM(RTRIM(UnitDescription)) <> ''"

print("Breakdown by UnitDescription for still-NULL products:")
for row in cur.execute(
    f"SELECT UnitDescription, COUNT(*) c FROM Products WHERE {COND} "
    f"GROUP BY UnitDescription ORDER BY c DESC"
).fetchall():
    print(" ", row.UnitDescription, row.c)

count = cur.execute(f"SELECT COUNT(*) FROM Products WHERE {COND}").fetchval()
print(f"\nTotal to update: {count}")

sample = cur.execute(
    f"SELECT TOP 20 ProductCode, ProductName, UnitDescription, "
    f"RTRIM(UnitDescription) + ' ' + LEFT(ProductName, 1) AS NewSubLocation "
    f"FROM Products WHERE {COND}"
).fetchall()
for row in sample:
    print(f"  {row.ProductCode}  {row.ProductName!r}  UnitDesc={row.UnitDescription} -> {row.NewSubLocation}")

remaining_still_null = cur.execute(
    "SELECT COUNT(*) FROM Products WHERE SubLocation IS NULL "
    "AND (UnitDescription IS NULL OR LTRIM(RTRIM(UnitDescription)) = '')"
).fetchval()
print(f"\nStill NULL after this (no UnitDescription at all): {remaining_still_null}")

if APPLY:
    cur.execute(
        f"UPDATE Products SET SubLocation = RTRIM(UnitDescription) + ' ' + LEFT(ProductName, 1) "
        f"WHERE {COND}"
    )
    print(f"Updated {cur.rowcount} rows.")
    conn.commit()
    print("Committed.")
else:
    print("\nPreview only (no changes made). Re-run with --apply to commit.")

conn.close()
