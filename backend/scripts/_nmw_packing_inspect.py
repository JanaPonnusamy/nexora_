"""Read-only inspection: does NMW.dbo.Products have a Packing column? Does
NMC.dbo.Products have SaleUnit? Do ProductCodes line up between the two
(NMW and NMC are one GST entity)?
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _live_store_conn as live

for code in ("NMW", "NMC"):
    conn = live.connect(code)
    cur = conn.cursor()
    cur.execute("SELECT DB_NAME()")
    print(code, "DB:", cur.fetchone()[0])
    cur.execute(
        "SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_NAME='Products' ORDER BY ORDINAL_POSITION"
    )
    cols = [f"{r[0]}({r[1]})" for r in cur.fetchall()]
    print(code, "Products columns:", cols)
    cur.execute("SELECT COUNT(*) FROM dbo.Products")
    print(code, "row count:", cur.fetchone()[0])
    print()

nmw = live.connect("NMW")
nmc = live.connect("NMC")
nmw_codes = {r[0] for r in nmw.cursor().execute("SELECT ProductCode FROM dbo.Products").fetchall()}
nmc_codes = {r[0] for r in nmc.cursor().execute("SELECT ProductCode FROM dbo.Products").fetchall()}
overlap = nmw_codes & nmc_codes
print(f"NMW codes: {len(nmw_codes)}, NMC codes: {len(nmc_codes)}, overlap: {len(overlap)}")
