import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _live_store_conn as live

for code in ("NMW", "NMC"):
    conn = live.connect(code)
    cur = conn.cursor()
    cur.execute(
        "SELECT TABLE_NAME, COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE COLUMN_NAME LIKE '%Pack%' ORDER BY TABLE_NAME"
    )
    print(code, "Pack-like columns:", cur.fetchall())

nmw = live.connect("NMW")
cur = nmw.cursor()
cur.execute("SELECT TOP 5 ProductCode, ProductName, PackingCode, PackageInformation, SaleUnit, UnitDescription FROM dbo.Products WHERE PackingCode IS NOT NULL")
for r in cur.fetchall():
    print(r)
cur.execute("SELECT COUNT(*) FROM dbo.Products WHERE PackingCode IS NOT NULL AND PackingCode <> 0")
print("NMW rows with PackingCode set:", cur.fetchone()[0])
cur.execute("SELECT COUNT(*) FROM dbo.Products WHERE PackageInformation IS NOT NULL AND PackageInformation <> ''")
print("NMW rows with PackageInformation set:", cur.fetchone()[0])

# is there a separate lookup table for PackingCode?
cur.execute("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME LIKE '%Pack%'")
print("NMW Pack-like tables:", cur.fetchall())
