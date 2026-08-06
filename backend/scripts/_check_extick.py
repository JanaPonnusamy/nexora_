from modules.legacy_order import database, repository

store = repository.get_store("NMW")
conn = database.get_branch_connection(
    store["server_name"], store["database"], store["username"], store["password"]
)
cur = conn.cursor()
row = cur.execute(
    "SELECT ProductCode, ProductName, SubLocation FROM Products WHERE ProductCode = '5878372'"
).fetchone()
print(row.ProductCode, row.ProductName, "->", row.SubLocation)
