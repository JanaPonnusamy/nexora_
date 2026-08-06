from modules.legacy_order import database, repository

store = repository.get_store("NMW")
conn = database.get_branch_connection(
    store["server_name"], store["database"], store["username"], store["password"]
)
cur = conn.cursor()
for pat in ["%[[]VET[]]%", "%[VET]%"]:
    n = cur.execute(
        "SELECT COUNT(*) FROM Products WHERE ProductName LIKE ?", pat
    ).fetchval()
    print(repr(pat), "->", n)

rows = cur.execute(
    "SELECT ProductCode, ProductName FROM Products WHERE ProductCode = '5884236'"
).fetchall()
for r in rows:
    print(repr(r.ProductName))
