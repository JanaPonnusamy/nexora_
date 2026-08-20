from modules.legacy_order import database, repository

store = repository.get_store("NMW")
conn = database.get_branch_connection(
    store["server_name"], store["database"], store["username"], store["password"]
)
cur = conn.cursor()
rows = cur.execute(
    "SELECT TOP 15 ProductCode, ProductName, SubLocation FROM Products WHERE ProductName LIKE '%SYP%'"
).fetchall()
for r in rows:
    print(r.ProductCode, r.ProductName, "->", r.SubLocation)
print("count:", cur.execute("SELECT COUNT(*) FROM Products WHERE ProductName LIKE '%SYP%'").fetchval())
