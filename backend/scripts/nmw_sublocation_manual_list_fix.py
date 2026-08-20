"""One-off: apply a manually curated ProductCode -> SubLocation mapping on NMW.

Run with --apply to actually commit; without it, only previews the diff.
"""
import sys

from modules.legacy_order import database, repository

APPLY = "--apply" in sys.argv

MAPPING = {
    "5893648": "SURG",  # AIR BED 9720 (UPHEALTHY)
    "5878775": "FOOD",  # APTAMIL 1 REF [GOLD] 400GM
    "5876948": "FOOD",  # APTAMIL 2 REF [GOLD] 400GM
    "5883910": "INJ",   # BASAGLAR CARTRIDGE 3ML
    "5867658": "INJ",   # BASALOG REFIL 3ML CARTRIDGES
    "5866823": "TAB B",   # BETACAP TR 20
    "5870123": "OIN",     # CANDID CREAM 30G
    "5870636": "LOT",     # CETAPHIL GENTLE SKIN CLEANSER 250ML
    "5869546": "TAB C",   # COGNITAM 800MG
    "5882324": "OIN",     # CWIN CREAM 30GM
    "5893640": "POW",     # ELECTRAL ASSORTED 5*4.4GM
    "5869682": "CNT",     # ELTROXIN 125MG
    "5880348": "FOOD",    # ENSURE DIABETIC VAN 200GM REF
    "5877164": "FOOD",    # ENSURE VANNILA 375GM REFIL
    "5891966": "OIN",     # ERYIT OC CREAM 15GM
    "5875997": "TAB G",   # GABAGESIC PLUS
    "5874874": "INJ",     # INSUGEN 30/70 REFIL 3ML
    "5869635": "TAB J",   # JARDIANCE 25MG
    "5881286": "FOOD",    # LACTARE GRANULES [CARDAMON] 250GM
    "5891603": "OIN",     # MONISON'S BALM 45GM
    "5893645": "OIN",     # MUPIRUS CREAM 5GM
    "5893647": "SURG",    # NEBULIZER MACHINE UH 506 (UPHEALTHY)
    "5869886": "TAB O",   # ONDERO MET 2.5/500MG
    "5880415": "SURG",    # ONE TOUCH SELECT PLUS 50'S
    "5888626": "OIN",     # PRILOX CREAM 10GM
    "5893652": "SURG",    # PULSE OXIMETER (UPHEALTHY)
    "5883051": "OIN",     # SKINLITE CREAM 15GM
    "5870029": "TAB T",   # TELISTA -D
    "5870751": "LOT",     # V WASH PLUS 100ML
    "5893649": "SURG",    # WALKER FOLDING UH911 (UPHEALTHY)
    "5893650": "SURG",    # WALKER FOLDING UH913L (UPHEALTHY)
    "5893651": "SURG",    # WHEEL CHAIR 809 (UPHEALTHY)
    "5886594": "INJ",     # XSULIN 30/70 CARTRIDGE 3ML
    "5877636": "SYP Z",   # ZINCOVIT CL SYRUP
    "5866892": "TAB Z",   # ZORYL M 0.5
}

store = repository.get_store("NMW")
if not store:
    raise SystemExit("Store 'NMW' not found in central Stores table")

conn = database.get_branch_connection(
    store["server_name"], store["database"], store["username"], store["password"]
)
cur = conn.cursor()

print(f"{len(MAPPING)} products in mapping")
for code, target in MAPPING.items():
    row = cur.execute(
        "SELECT ProductName, SubLocation FROM Products WHERE ProductCode = ?", code
    ).fetchone()
    if row is None:
        print(f"  {code}  NOT FOUND")
        continue
    print(f"  {code}  {row.ProductName!r}  {row.SubLocation} -> {target}")

if APPLY:
    updated = 0
    for code, target in MAPPING.items():
        cur.execute(
            "UPDATE Products SET SubLocation = ? WHERE ProductCode = ?", target, code
        )
        updated += cur.rowcount
    print(f"Updated {updated} rows.")
    conn.commit()
    print("Committed.")
else:
    print("\nPreview only (no changes made). Re-run with --apply to commit.")

conn.close()
