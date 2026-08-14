from modules.legacy_order import database, repository

store = repository.get_store("NMW")
conn = database.get_branch_connection(
    store["server_name"], store["database"], store["username"], store["password"]
)
cur = conn.cursor()

n = cur.execute(
    "SELECT COUNT(*) FROM Products WHERE LTRIM(RTRIM(SubLocation)) = 'TAB'"
).fetchval()
print("Rows with SubLocation = bare 'TAB':", n)

blank = cur.execute(
    "SELECT COUNT(*) FROM Products WHERE LTRIM(RTRIM(SubLocation)) = 'TAB' "
    "AND LTRIM(ProductName) = ''"
).fetchval()
print("  of those with blank/empty ProductName (would yield 'TAB '):", blank)

print("\nSample:")
for r in cur.execute(
    "SELECT TOP 20 ProductCode, ProductName, UnitDescription, SubLocation, "
    "'TAB ' + LEFT(LTRIM(ProductName), 1) AS NewSubLoc "
    "FROM Products WHERE LTRIM(RTRIM(SubLocation)) = 'TAB'"
).fetchall():
    print(f"  {r.ProductCode}  {r.ProductName!r}  UD={r.UnitDescription!r} -> {r.NewSubLoc!r}")

conn.close()
