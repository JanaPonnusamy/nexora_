from modules.legacy_order import database, repository

store = repository.get_store("NMW")
conn = database.get_branch_connection(
    store["server_name"], store["database"], store["username"], store["password"]
)
cur = conn.cursor()
tests = [
    r"%$[VET$]%",  # ESCAPE '$'
]
for pat in tests:
    n = cur.execute(
        "SELECT COUNT(*) FROM Products WHERE ProductName LIKE ? ESCAPE '$'", pat
    ).fetchval()
    print(repr(pat), "->", n)

# Direct check on the known row using CHARINDEX instead of LIKE
n2 = cur.execute(
    "SELECT COUNT(*) FROM Products WHERE CHARINDEX('[VET]', ProductName) > 0"
).fetchval()
print("CHARINDEX count:", n2)
