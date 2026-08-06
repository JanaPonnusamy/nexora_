from modules.legacy_order import database, repository

store = repository.get_store("NMW")
conn = database.get_branch_connection(
    store["server_name"], store["database"], store["username"], store["password"]
)
cur = conn.cursor()
rows = cur.execute(
    "SELECT TOP 30 ProductCode, ProductName, UnitDescription, SubLocation "
    "FROM Products WHERE ProductName LIKE '%CREAM%'"
).fetchall()
for r in rows:
    print(r.ProductCode, r.ProductName, "|", r.UnitDescription, "->", r.SubLocation)
print("count:", cur.execute("SELECT COUNT(*) FROM Products WHERE ProductName LIKE '%CREAM%'").fetchval())

print("\ndistinct UnitDescription for CREAM products:")
for r in cur.execute(
    "SELECT DISTINCT UnitDescription, COUNT(*) c FROM Products WHERE ProductName LIKE '%CREAM%' "
    "GROUP BY UnitDescription ORDER BY c DESC"
).fetchall():
    print(" ", r.UnitDescription, r.c)
