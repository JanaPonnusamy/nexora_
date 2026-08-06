"""One-off: set Products.SubLocation = 'TAB ' + first letter on NMW for products
whose name contains TAB/TABS/TABLET/TABLETS/CAP/CAPS/CAPSULES as a whole word
(not a substring like 'METABOLIC' or 'CAPTOPRIL').

Only touches rows where SubLocation IS NULL, so it doesn't clobber the SOAP/RC/
INH/SYP/NS/Vet/EYRUS fixes already applied.

Run with --apply to actually commit; without it, only previews counts.
"""
import sys

from modules.legacy_order import database, repository

APPLY = "--apply" in sys.argv

WORDS = ["TAB", "TABS", "TABLET", "TABLETS", "CAP", "CAPS", "CAPSULES"]

store = repository.get_store("NMW")
if not store:
    raise SystemExit("Store 'NMW' not found in central Stores table")

conn = database.get_branch_connection(
    store["server_name"], store["database"], store["username"], store["password"]
)
cur = conn.cursor()


def word_cond(word):
    padded = "' ' + ProductName + ' '"
    return f"{padded} LIKE '% {word} %'"


WORD_COND = " OR ".join(word_cond(w) for w in WORDS)
COND = f"SubLocation IS NULL AND ({WORD_COND})"

count = cur.execute(f"SELECT COUNT(*) FROM Products WHERE {COND}").fetchval()
print(f"NULL-SubLocation products matching TAB/CAP word list: {count}")

sample = cur.execute(
    f"SELECT TOP 20 ProductCode, ProductName, UnitDescription, "
    f"'TAB ' + LEFT(ProductName, 1) AS NewSubLocation "
    f"FROM Products WHERE {COND}"
).fetchall()
for row in sample:
    print(f"  {row.ProductCode}  {row.ProductName!r}  UnitDesc={row.UnitDescription} -> {row.NewSubLocation}")

if APPLY:
    cur.execute(
        f"UPDATE Products SET SubLocation = 'TAB ' + LEFT(ProductName, 1) WHERE {COND}"
    )
    print(f"Updated {cur.rowcount} rows.")
    conn.commit()
    print("Committed.")
else:
    print("Preview only (no changes made). Re-run with --apply to commit.")

conn.close()
