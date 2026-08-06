from modules.legacy_order import database, repository

store = repository.get_store("NMW")
conn = database.get_branch_connection(
    store["server_name"], store["database"], store["username"], store["password"]
)
cur = conn.cursor()

print("Products still SubLocation LIKE 'TAB %', broken down by UnitDescription:")
for row in cur.execute(
    "SELECT UnitDescription, COUNT(*) c FROM Products WHERE SubLocation LIKE 'TAB %' "
    "GROUP BY UnitDescription ORDER BY c DESC"
).fetchall():
    print(" ", row.UnitDescription, row.c)

total = cur.execute("SELECT COUNT(*) FROM Products WHERE SubLocation LIKE 'TAB %'").fetchval()
print("total TAB-prefixed:", total)
