from modules.legacy_order import database, repository

store = repository.get_store("NMW")
conn = database.get_branch_connection(
    store["server_name"], store["database"], store["username"], store["password"]
)
cur = conn.cursor()
rows = cur.execute(
    "SELECT ProductCode, ProductName, SubLocation, UnitDescription, "
    "DATALENGTH(UnitDescription) AS len_ud FROM Products "
    "WHERE ProductCode IN ('5878775', '5876948')"
).fetchall()
for r in rows:
    print(r.ProductCode, r.ProductName, "| SubLocation=", repr(r.SubLocation), "| UnitDescription=", repr(r.UnitDescription), "| len=", r.len_ud)
