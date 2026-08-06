"""One-off: normalize SubLocation 'Vet' -> 'VET' (uppercase) on NMW.

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
    "SELECT COUNT(*) FROM Products WHERE SubLocation = 'Vet' COLLATE Latin1_General_CS_AS"
).fetchval()
print(f"Products with SubLocation exactly 'Vet' (mixed case): {count}")

if APPLY:
    cur.execute(
        "UPDATE Products SET SubLocation = 'VET' "
        "WHERE SubLocation = 'Vet' COLLATE Latin1_General_CS_AS"
    )
    print(f"Updated {cur.rowcount} rows.")
    conn.commit()
    print("Committed.")
else:
    print("Preview only (no changes made). Re-run with --apply to commit.")

conn.close()
