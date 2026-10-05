"""Update NMW.dbo.Products.PackageInformation from NMC.dbo.Products.SaleUnit,
matched by ProductCode (NMW and NMC are one GST entity, so codes line up
directly -- no fuzzy matching needed, confirmed 100% ProductCode overlap).

NMC connection is READ-ONLY (SELECT only, never written to).
NMW's Products table MUST be backed up first --
    backend/.venv/Scripts/python backend/scripts/_backup_live_store_products.py NMW "D:\\VBDOTNET\\nmw\\Update"

Only rows where NMC has a non-null SaleUnit and it differs from NMW's current
PackageInformation are updated. SaleUnit (float) is rendered as plain text
(no trailing ".0" for whole numbers).
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _live_store_conn as live

REPORT_OUT = sys.argv[1] if len(sys.argv) > 1 else r"D:\VBDOTNET\nmw\Update\NMW_PackageInformation_from_NMC_SaleUnit_result.csv"


def format_sale_unit(value):
    f = float(value)
    if f.is_integer():
        return str(int(f))
    return str(f)


nmc_conn = live.connect("NMC")
nmc_cur = nmc_conn.cursor()
nmc_cur.execute("SELECT ProductCode, SaleUnit FROM dbo.Products WHERE SaleUnit IS NOT NULL")
nmc_saleunit = {code: su for code, su in nmc_cur.fetchall()}
print(f"NMC: {len(nmc_saleunit)} products with a non-null SaleUnit")

nmw_conn = live.connect("NMW")
nmw_cur = nmw_conn.cursor()
nmw_cur.execute("SELECT ProductCode, ProductName, PackageInformation FROM dbo.Products")
nmw_rows = nmw_cur.fetchall()
print(f"NMW: {len(nmw_rows)} products total")

plan = []
for code, name, current_pkg in nmw_rows:
    su = nmc_saleunit.get(code)
    if su is None:
        continue
    new_pkg = format_sale_unit(su)
    if (current_pkg or "") == new_pkg:
        continue
    plan.append({"code": code, "name": name, "old": current_pkg, "new": new_pkg})

print(f"Plan built: {len(plan)} row(s) to update")

cur = nmw_conn.cursor()
updated = []
try:
    for r in plan:
        cur.execute(
            """UPDATE dbo.Products
               SET PackageInformation = ?
               OUTPUT inserted.ProductCode
               WHERE ProductCode = ?""",
            r["new"], r["code"],
        )
        row = cur.fetchone()
        if row:
            updated.append(r)

    print(f"UPDATE executed inside transaction: {len(updated)} row(s) affected")
    if len(updated) != len(plan):
        print(f"MISMATCH: planned {len(plan)} but affected {len(updated)}. Rolling back.")
        nmw_conn.rollback()
        sys.exit(1)

    nmw_conn.commit()
    print("COMMITTED.")
except Exception:
    nmw_conn.rollback()
    raise

with open(REPORT_OUT, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["ProductCode", "ProductName", "OldPackageInformation", "NewPackageInformation"])
    for r in updated:
        w.writerow([r["code"], r["name"], r["old"], r["new"]])

print(f"Wrote {len(updated)} rows to {REPORT_OUT}")
