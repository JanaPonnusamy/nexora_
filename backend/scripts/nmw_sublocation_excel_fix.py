"""One-off: restore Products.SubLocation on the NMW branch DB from the manually
curated D:\\Nathan Wholesale Files\\sUBLOCATION.xlsx sheet.

The blanket TAB fill (nmw_sublocation_tab_fill.py) overwrote SubLocation for every
product that had NULL, including ones that were already manually placed in the
Excel sheet (e.g. inhalers/rotacaps put in 'CNT'). This joins the sheet to
Products by ProductCode and restores the Excel's Sublocation value.

Run with --apply to actually commit; without it, only previews the diff.
"""
import sys

import pandas as pd

from modules.legacy_order import database, repository

APPLY = "--apply" in sys.argv
EXCEL_PATH = r"D:\Nathan Wholesale Files\sUBLOCATION.xlsx"

df = pd.read_excel(EXCEL_PATH)
df = df.dropna(subset=["ProductCode", "Sublocation"])
df["ProductCode"] = df["ProductCode"].astype(str).str.strip()
df["Sublocation"] = df["Sublocation"].astype(str).str.strip()

store = repository.get_store("NMW")
if not store:
    raise SystemExit("Store 'NMW' not found in central Stores table")

conn = database.get_branch_connection(
    store["server_name"], store["database"], store["username"], store["password"]
)
cur = conn.cursor()

mismatches = []
for _, row in df.iterrows():
    current = cur.execute(
        "SELECT SubLocation FROM Products WHERE ProductCode = ?", row["ProductCode"]
    ).fetchval()
    if current != row["Sublocation"]:
        mismatches.append((row["ProductCode"], row["ProductName"], current, row["Sublocation"]))

print(f"Excel rows: {len(df)}, mismatched with current DB value: {len(mismatches)}")
for code, name, current, target in mismatches[:15]:
    print(f"  {code}  {name!r}  {current} -> {target}")

if APPLY:
    for code, _name, _current, target in mismatches:
        cur.execute(
            "UPDATE Products SET SubLocation = ? WHERE ProductCode = ?", target, code
        )
    print(f"Updated {len(mismatches)} rows.")
    conn.commit()
    print("Committed.")
else:
    print("Preview only (no changes made). Re-run with --apply to commit.")

conn.close()
