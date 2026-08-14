"""Read-only diagnostic: for NMW products where UnitDescription = 'TAB',
report how many already have SubLocation = 'TAB ' + LEFT(ProductName,1)
and how many DON'T (the update candidates). No writes."""
from modules.legacy_order import database, repository

store = repository.get_store("NMW")
if not store:
    raise SystemExit("Store 'NMW' not found in central Stores table")

conn = database.get_branch_connection(
    store["server_name"], store["database"], store["username"], store["password"]
)
cur = conn.cursor()

total = cur.execute(
    "SELECT COUNT(*) FROM Products WHERE UnitDescription = 'TAB'"
).fetchval()
print("Total products with UnitDescription = 'TAB':", total)

expected = "'TAB ' + LEFT(ProductName, 1)"

already = cur.execute(
    f"SELECT COUNT(*) FROM Products WHERE UnitDescription = 'TAB' "
    f"AND SubLocation = {expected}"
).fetchval()
print("  already correct (SubLocation = 'TAB '+first letter):", already)

mismatch = cur.execute(
    f"SELECT COUNT(*) FROM Products WHERE UnitDescription = 'TAB' "
    f"AND (SubLocation IS NULL OR SubLocation <> {expected})"
).fetchval()
print("  NEEDS update (NULL or different):", mismatch)

print("\nSample of mismatches (up to 25):")
rows = cur.execute(
    f"SELECT TOP 25 ProductCode, ProductName, SubLocation AS CurrentSubLoc, "
    f"{expected} AS NewSubLoc "
    f"FROM Products WHERE UnitDescription = 'TAB' "
    f"AND (SubLocation IS NULL OR SubLocation <> {expected})"
).fetchall()
for r in rows:
    print(f"  {r.ProductCode}  {r.ProductName!r}  cur={r.CurrentSubLoc!r} -> {r.NewSubLoc!r}")

conn.close()
