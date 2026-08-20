from modules.legacy_order import database, repository

store = repository.get_store("NMW")
conn = database.get_branch_connection(
    store["server_name"], store["database"], store["username"], store["password"]
)
cur = conn.cursor()
print("Breakdown by UnitDescription for '%GEL%' products (excluding already-fixed CREAM/GEL combos):")
for row in cur.execute(
    "SELECT UnitDescription, COUNT(*) c FROM Products WHERE ProductName LIKE '%GEL%' "
    "AND ProductName NOT LIKE '%CREAM%' GROUP BY UnitDescription ORDER BY c DESC"
).fetchall():
    print(" ", row.UnitDescription, row.c)

print("\nsample:")
for row in cur.execute(
    "SELECT TOP 15 ProductCode, ProductName, UnitDescription, SubLocation FROM Products "
    "WHERE ProductName LIKE '%GEL%' AND ProductName NOT LIKE '%CREAM%'"
).fetchall():
    print(" ", row.ProductCode, row.ProductName, "|", row.UnitDescription, "->", row.SubLocation)
