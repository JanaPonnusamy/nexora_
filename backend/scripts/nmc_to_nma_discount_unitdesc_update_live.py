"""NMC -> NMA sync of DefaultDiscountPercentage, DiscountPerAllowInBill
(max discount), and UnitDescription -- chained through NMW.

Reads/writes the REAL, live per-store SQL Server databases directly
(connection details from NEXORA_PLATFORM.dbo.stores, decrypted with the
store_agent Fernet key) -- NOT OrderNMC (HO's synced mirror) and NOT
NEXORA_PLATFORM's own Products data. NEXORA_PLATFORM.dbo.product_mapping is
read-only here -- it is only the identity bridge (NMA<->NMW and NMW<->NMC
are both matched there, so NMC<->NMA is resolved through NMW; NMW's own
Products data is never read or written).

Safety rules (same chain-building logic as nmc_to_nma_discount_update.py):
  - Only APPROVED/AUTO mapping rows are used (PENDING/REJECTED excluded).
  - A NMW code claimed by more than one NMA source is excluded (ambiguous).
  - A NMC code that would resolve to more than one distinct NMA code through
    the chain is excluded.
  - Inactive products (either side) are excluded.
  - A row is only eligible if at least one of the three target fields
    actually differs; when eligible, all three are set from NMC's live
    values together so NMA ends up fully in sync with NMC for that product.

ALWAYS run _backup_live_store_products.py NMA first before --execute.

Usage:
    backend/.venv/Scripts/python backend/scripts/nmc_to_nma_discount_unitdesc_update_live.py            # dry run only (default, no writes)
    backend/.venv/Scripts/python backend/scripts/nmc_to_nma_discount_unitdesc_update_live.py --execute   # dry run, then perform the guarded UPDATE inside a transaction
"""
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config.database import get_connection as get_platform_connection
import _live_store_conn as live

NMW_STORE_ID = "DEB4780E-CA8D-4CCD-9942-3ACE1CC88EE0"
NMA_STORE_ID = "109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1"
NMC_STORE_ID = "FCBE8B35-B1A1-463E-80C6-73161CDC8F32"

_USABLE_STATUSES = ("APPROVED", "AUTO")


def _build_chain(pconn):
    pcur = pconn.cursor()

    pcur.execute(
        """SELECT source_product_code, target_product_code
           FROM dbo.product_mapping
           WHERE source_store_id=? AND target_store_id=? AND is_deleted=0
             AND status IN (?, ?)""",
        NMW_STORE_ID, NMC_STORE_ID, *_USABLE_STATUSES,
    )
    nmw_to_nmc = pcur.fetchall()  # (NmwCode, NmcCode)

    pcur.execute(
        """SELECT source_product_code, target_product_code
           FROM dbo.product_mapping
           WHERE source_store_id=? AND target_store_id=? AND is_deleted=0
             AND status IN (?, ?)""",
        NMA_STORE_ID, NMW_STORE_ID, *_USABLE_STATUSES,
    )
    nma_to_nmw = pcur.fetchall()  # (NmaCode, NmwCode)

    nmw_to_nma_candidates = defaultdict(set)
    for nma_code, nmw_code in nma_to_nmw:
        nmw_to_nma_candidates[nmw_code].add(nma_code)
    ambiguous_nmw = {k for k, v in nmw_to_nma_candidates.items() if len(v) > 1}
    nmw_to_nma = {
        k: next(iter(v)) for k, v in nmw_to_nma_candidates.items() if k not in ambiguous_nmw
    }

    nmc_to_nma_candidates = defaultdict(set)
    for nmw_code, nmc_code in nmw_to_nmc:
        nma_code = nmw_to_nma.get(nmw_code)
        if nma_code:
            nmc_to_nma_candidates[nmc_code].add(nma_code)
    ambiguous_nmc = {k for k, v in nmc_to_nma_candidates.items() if len(v) > 1}
    chain = {
        k: next(iter(v)) for k, v in nmc_to_nma_candidates.items() if k not in ambiguous_nmc
    }

    counts = {
        "nmw_to_nmc_rows": len(nmw_to_nmc),
        "nma_to_nmw_rows": len(nma_to_nmw),
        "ambiguous_nmw_excluded": len(ambiguous_nmw),
        "ambiguous_nmc_excluded": len(ambiguous_nmc),
        "chain_total": len(chain),
    }
    return chain, counts


def _fetch_products(cur):
    cur.execute(
        """SELECT ProductCode, ProductName, DefaultDiscountPercentage,
                  DiscountPerAllowInBill, UnitDescription, ISNULL(isActive, 1)
           FROM dbo.Products"""
    )
    return {str(r[0]): (r[1], r[2], r[3], r[4], r[5]) for r in cur.fetchall()}


def _norm_num(v):
    return float(v) if v is not None else None


def _norm_text(v):
    return (v or "").strip()


def _compute_diffs(chain, nmc_products, nma_products):
    diffs = []
    skipped_inactive = 0
    skipped_same = 0
    skipped_missing = 0
    for nmc_code, nma_code in chain.items():
        nc = nmc_products.get(nmc_code)
        na = nma_products.get(nma_code)
        if nc is None or na is None:
            skipped_missing += 1
            continue
        nc_name, nc_disc, nc_max, nc_unit, nc_active = nc
        na_name, na_disc, na_max, na_unit, na_active = na
        if not nc_active or not na_active:
            skipped_inactive += 1
            continue

        nc_disc_v, na_disc_v = _norm_num(nc_disc), _norm_num(na_disc)
        nc_max_v, na_max_v = _norm_num(nc_max), _norm_num(na_max)
        nc_unit_v, na_unit_v = _norm_text(nc_unit), _norm_text(na_unit)

        disc_diff = nc_disc_v is not None and (na_disc_v is None or abs(nc_disc_v - na_disc_v) >= 0.0001)
        max_diff = nc_max_v is not None and (na_max_v is None or abs(nc_max_v - na_max_v) >= 0.0001)
        unit_diff = nc_unit_v != "" and nc_unit_v != na_unit_v

        if not (disc_diff or max_diff or unit_diff):
            skipped_same += 1
            continue

        diffs.append({
            "nmc_code": nmc_code, "nmc_name": nc_name,
            "nma_code": nma_code, "nma_name": na_name,
            "new_discount": nc_disc_v, "old_discount": na_disc_v,
            "new_max": nc_max_v, "old_max": na_max_v,
            "new_unit": nc_unit, "old_unit": na_unit,
        })
    return diffs, skipped_inactive, skipped_same, skipped_missing


def dry_run():
    pconn = get_platform_connection()
    chain, chain_counts = _build_chain(pconn)

    nmc_conn = live.connect("NMC")
    nma_conn = live.connect("NMA")
    nmc_products = _fetch_products(nmc_conn.cursor())
    nma_products = _fetch_products(nma_conn.cursor())

    diffs, skipped_inactive, skipped_same, skipped_missing = _compute_diffs(chain, nmc_products, nma_products)

    print("=== DRY RUN (LIVE STORE DBs): NMC -> NMA Discount/Max/UnitDescription sync (via NMW) ===\n")
    print("Source: NMC live DB   Target: NMA live DB   Bridge: NEXORA_PLATFORM.product_mapping (identity only)\n")
    print(f"NMW->NMC usable mapping rows (APPROVED/AUTO):  {chain_counts['nmw_to_nmc_rows']}")
    print(f"NMA->NMW usable mapping rows (APPROVED/AUTO):  {chain_counts['nma_to_nmw_rows']}")
    print(f"Ambiguous NMW targets excluded (NMA->NMW):     {chain_counts['ambiguous_nmw_excluded']}")
    print(f"Ambiguous NMC->NMA chain results excluded:     {chain_counts['ambiguous_nmc_excluded']}")
    print(f"Clean NMC->NMA chain size:                     {chain_counts['chain_total']}")
    print(f"Skipped (code not found live -- sync drift):   {skipped_missing}")
    print(f"Skipped (inactive on either side):             {skipped_inactive}")
    print(f"Skipped (all 3 fields already match):          {skipped_same}")
    print(f"\n>>> Total rows ELIGIBLE for update: {len(diffs)} <<<\n")

    print("--- Sample eligible rows (first 25) ---")
    print("NMC Code | NMC Name | NMA Code | NMA Name | Disc(old->new) | Max(old->new) | Unit(old->new)")
    for r in diffs[:25]:
        print(f"{r['nmc_code']} | {(r['nmc_name'] or '')[:22]} | {r['nma_code']} | {(r['nma_name'] or '')[:22]} | "
              f"{r['old_discount']}->{r['new_discount']} | {r['old_max']}->{r['new_max']} | "
              f"{(r['old_unit'] or '')[:12]!r}->{(r['new_unit'] or '')[:12]!r}")

    return nma_conn, diffs


def execute_update(nma_conn, diffs):
    if not diffs:
        print("\nNothing to update.")
        return

    cur = nma_conn.cursor()
    try:
        updated = []
        for r in diffs:
            cur.execute(
                """UPDATE dbo.Products
                   SET DefaultDiscountPercentage = ISNULL(?, DefaultDiscountPercentage),
                       DiscountPerAllowInBill = ISNULL(?, DiscountPerAllowInBill),
                       UnitDescription = CASE WHEN ? <> '' THEN ? ELSE UnitDescription END
                   OUTPUT inserted.ProductCode, inserted.ProductName
                   WHERE ProductCode = ?""",
                r["new_discount"], r["new_max"], r["new_unit"] or "", r["new_unit"], r["nma_code"],
            )
            row = cur.fetchone()
            if row:
                updated.append(row)

        print(f"\n=== UPDATE executed inside transaction on NMA's LIVE store DB: {len(updated)} row(s) affected ===")

        if len(updated) != len(diffs):
            print(f"MISMATCH: dry-run counted {len(diffs)} eligible rows but UPDATE "
                  f"affected {len(updated)}. Rolling back -- no changes committed.")
            nma_conn.rollback()
            return

        nma_conn.commit()
        print("COMMITTED.")
        print("\n--- Updated NMA rows ---")
        for pc, name in updated:
            print(f"{pc} | {(name or '')[:30]}")
    except Exception:
        nma_conn.rollback()
        raise


if __name__ == "__main__":
    nma_conn, diffs = dry_run()
    if "--execute" in sys.argv:
        execute_update(nma_conn, diffs)
    else:
        print("\n(dry run only -- pass --execute to apply these updates)")
