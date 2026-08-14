from modules.legacy_order import database, repository

store = repository.get_store("NMW")
conn = database.get_branch_connection(
    store["server_name"], store["database"], store["username"], store["password"]
)
cur = conn.cursor()

row = cur.execute(
    "SELECT ProductCode, ProductName, UnitDescription, SubLocation, "
    "LEN(UnitDescription) AS UDLen, "
    "'[' + UnitDescription + ']' AS UDBracket "
    "FROM Products WHERE ProductCode = 5886205"
).fetchone()
print("ProductCode :", row.ProductCode)
print("ProductName :", repr(row.ProductName))
print("UnitDesc    :", repr(row.UnitDescription), "len=", row.UDLen, "bracket=", row.UDBracket)
print("SubLocation :", repr(row.SubLocation))
print("Would set to:", "TAB " + (row.ProductName or "")[:1])

# How many rows have a UnitDescription that CONTAINS tab but isn't exactly 'TAB'
print("\nDistinct UnitDescription values that look tablet-ish:")
for r in cur.execute(
    "SELECT UnitDescription, COUNT(*) c FROM Products "
    "WHERE UnitDescription LIKE '%TAB%' "
    "GROUP BY UnitDescription ORDER BY c DESC"
).fetchall():
    print(f"  [{r.UnitDescription}]  x{r.c}")

conn.close()
