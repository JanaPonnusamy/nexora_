"""One-off: revert wrongly-guessed Products.SubLocation on NMW.

The blanket TAB fill set SubLocation = 'TAB ' + first letter for every product
that had a NULL SubLocation, regardless of actual dosage form. Keep that value
only where UnitDescription confirms it really is a tablet/capsule; everything
else currently stuck at 'TAB <letter>' is reset to NULL (no guessing) so it can
be re-classified deliberately later (SYP/OIN/etc.).

Run with --apply to actually commit; without it, only previews counts.
"""
import sys

from modules.legacy_order import database, repository

APPLY = "--apply" in sys.argv

TAB_CAP_UNITS = ("TAB", "CAP", "CAPS", "TABLETS", "INSTACAP")

store = repository.get_store("NMW")
if not store:
    raise SystemExit("Store 'NMW' not found in central Stores table")

conn = database.get_branch_connection(
    store["server_name"], store["database"], store["username"], store["password"]
)
cur = conn.cursor()

placeholders = ",".join("?" for _ in TAB_CAP_UNITS)

keep_count = cur.execute(
    f"SELECT COUNT(*) FROM Products WHERE SubLocation LIKE 'TAB %' "
    f"AND UnitDescription IN ({placeholders})",
    *TAB_CAP_UNITS,
).fetchval()
revert_count = cur.execute(
    f"SELECT COUNT(*) FROM Products WHERE SubLocation LIKE 'TAB %' "
    f"AND (UnitDescription IS NULL OR UnitDescription NOT IN ({placeholders}))",
    *TAB_CAP_UNITS,
).fetchval()
print(f"Keep as TAB <letter> (true tablet/capsule): {keep_count}")
print(f"Revert to NULL (not actually TAB/CAP): {revert_count}")

sample = cur.execute(
    f"SELECT TOP 10 ProductCode, ProductName, UnitDescription, SubLocation FROM Products "
    f"WHERE SubLocation LIKE 'TAB %' AND (UnitDescription IS NULL OR UnitDescription NOT IN ({placeholders}))",
    *TAB_CAP_UNITS,
).fetchall()
for row in sample:
    print(f"  {row.ProductCode}  {row.ProductName!r}  UnitDesc={row.UnitDescription}  {row.SubLocation} -> NULL")

if APPLY:
    cur.execute(
        f"UPDATE Products SET SubLocation = NULL WHERE SubLocation LIKE 'TAB %' "
        f"AND (UnitDescription IS NULL OR UnitDescription NOT IN ({placeholders}))",
        *TAB_CAP_UNITS,
    )
    print(f"Updated (reverted to NULL) {cur.rowcount} rows.")
    conn.commit()
    print("Committed.")
else:
    print("\nPreview only (no changes made). Re-run with --apply to commit.")

conn.close()
