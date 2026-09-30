"""One-off: export NMW supplier code 589's stock list (procurement.supplier_stock)
to an .xlsx file in the scratchpad directory."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from openpyxl import Workbook

from modules.supplier_stock_analysis.repository import list_supplier_products

TENANT_ID = "A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D"
NMW_STORE_ID = "DEB4780E-CA8D-4CCD-9942-3ACE1CC88EE0"
SUPPLIER_CODE = "589"

OUT_PATH = Path(r"C:\Users\Pharma\AppData\Local\Temp\claude\e--Nexora\40953c0a-e698-48f2-9bbe-bfb0f8508761\scratchpad\nmw_supplier_589_stock.xlsx")

rows = list_supplier_products(TENANT_ID, SUPPLIER_CODE, store_id=NMW_STORE_ID, search="", only_available=False)

if not rows:
    print("NO_ROWS")
    sys.exit(0)

wb = Workbook()
ws = wb.active
ws.title = "Supplier 589 Stock"
ws.append(["Supplier Product Code", "Supplier Product Name", "Stock"])
for r in rows:
    code = r.get("supplier_product_code")
    try:
        code = int(code)
    except (TypeError, ValueError):
        pass
    ws.append([code, r.get("supplier_product_name"), r.get("available_stock")])

OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
wb.save(OUT_PATH)
print(f"ROWS={len(rows)}")
print(f"PATH={OUT_PATH}")
