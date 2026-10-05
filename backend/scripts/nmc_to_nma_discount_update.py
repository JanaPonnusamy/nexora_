"""NMC -> NMA DefaultDiscountPercentage sync, chained through NMW.

There is no direct, reviewed NMC<->NMA product mapping. The chain goes:

    NMC product --[NMW->NMC product_mapping run]--> NMW product
                --[NMA->NMW product_mapping run]--> NMA product

Both mapping runs live in NEXORA_PLATFORM.dbo.product_mapping (the Product
Mapping module), not in the legacy dbo.SupplierProductMatch table used by the
older sublocation scripts. Only APPROVED/AUTO rows are used (PENDING and
REJECTED are excluded). The NMA->NMW run is the one that was manually
reviewed to completion (0 PENDING); NMW->NMC is mostly AUTO with a small
PENDING remainder, which is fine since NMC is only the discount *source* here.

Safety rules (mirrors nmc_to_nma_sublocation_update.py conventions):
  - A NMW ProductCode claimed by more than one NMA source ProductCode
    (ambiguous NMA->NMW) is excluded from the chain entirely.
  - A NMC ProductCode that would resolve to more than one distinct NMA
    ProductCode through the chain is excluded.
  - Inactive products (either side) are excluded.
  - Only rows where the NMA DefaultDiscountPercentage actually differs from
    the chained NMC value are eligible -- rows already matching are skipped.

The two mapping tables are read from NEXORA_PLATFORM and the discount values
from the legacy OrderNMC database (same SQL Server instance, different
databases) -- the join itself is done in Python since a three-part-name
cross-database JOIN with GROUP BY/HAVING on these table sizes was observed to
take minutes; two flat SELECTs plus an in-memory dict join take under a
second.

Usage:
    backend/.venv/Scripts/python backend/scripts/nmc_to_nma_discount_update.py            # dry run only (default, no writes)
    backend/.venv/Scripts/python backend/scripts/nmc_to_nma_discount_update.py --execute   # dry run, then perform the guarded UPDATE inside a transaction
"""
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.database import get_connection as get_platform_connection
from modules.legacy_order.database import get_central_connection

NMW_STORE_ID = "DEB4780E-CA8D-4CCD-9942-3ACE1CC88EE0"
NMA_STORE_ID = "109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1"
NMC_STORE_ID = "FCBE8B35-B1A1-463E-80C6-73161CDC8F32"

_USABLE_STATUSES = ("APPROVED", "AUTO")


def _build_chain(pconn):
    """Return {NmcProductCode: NmaProductCode}, plus exclusion counts."""
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


def _fetch_products(ccur, store_name):
    ccur.execute(
        """SELECT ProductCode, ProductName, DefaultDiscountPercentage, ISNULL(IsActive, 1)
           FROM dbo.Products WHERE StoreName = ?""",
        store_name,
    )
    return {str(r[0]): (r[1], r[2], r[3]) for r in ccur.fetchall()}


def _compute_diffs(chain, nmc_products, nma_products):
    diffs = []
    skipped_inactive = 0
    skipped_same = 0
    for nmc_code, nma_code in chain.items():
        nc = nmc_products.get(nmc_code)
        na = nma_products.get(nma_code)
        if nc is None or na is None:
            continue
        nc_name, nc_disc, nc_active = nc
        na_name, na_disc, na_active = na
        if not nc_active or not na_active:
            skipped_inactive += 1
            continue
        nc_v = float(nc_disc) if nc_disc is not None else 0.0
        na_v = float(na_disc) if na_disc is not None else 0.0
        if abs(nc_v - na_v) < 0.0001:
            skipped_same += 1
            continue
        diffs.append({
            "nmc_code": nmc_code, "nmc_name": nc_name, "nmc_discount": nc_v,
            "nma_code": nma_code, "nma_name": na_name, "nma_discount": na_v,
        })
    return diffs, skipped_inactive, skipped_same


def dry_run():
    pconn = get_platform_connection()
    chain, chain_counts = _build_chain(pconn)

    cconn = get_central_connection()
    ccur = cconn.cursor()
    nmc_products = _fetch_products(ccur, "NMC")
    nma_products = _fetch_products(ccur, "NMA")

    diffs, skipped_inactive, skipped_same = _compute_diffs(chain, nmc_products, nma_products)

    print("=== DRY RUN: NMC -> NMA DefaultDiscountPercentage sync (via NMW) ===\n")
    print(f"NMW->NMC usable mapping rows (APPROVED/AUTO):  {chain_counts['nmw_to_nmc_rows']}")
    print(f"NMA->NMW usable mapping rows (APPROVED/AUTO):  {chain_counts['nma_to_nmw_rows']}")
    print(f"Ambiguous NMW targets excluded (NMA->NMW):     {chain_counts['ambiguous_nmw_excluded']}")
    print(f"Ambiguous NMC->NMA chain results excluded:     {chain_counts['ambiguous_nmc_excluded']}")
    print(f"Clean NMC->NMA chain size:                     {chain_counts['chain_total']}")
    print(f"Skipped (inactive on either side):             {skipped_inactive}")
    print(f"Skipped (discount already matches):            {skipped_same}")
    print(f"\n>>> Total rows ELIGIBLE for discount update: {len(diffs)} <<<\n")

    print("--- Sample eligible rows (first 25) ---")
    print("NMC Code | NMC Name | NMC Disc% | NMA Code | NMA Name | Current NMA Disc%")
    for r in diffs[:25]:
        print(f"{r['nmc_code']} | {(r['nmc_name'] or '')[:28]} | {r['nmc_discount']} | "
              f"{r['nma_code']} | {(r['nma_name'] or '')[:28]} | {r['nma_discount']}")

    return cconn, diffs


def execute_update(cconn, diffs):
    if not diffs:
        print("\nNothing to update.")
        return

    ccur = cconn.cursor()
    try:
        updated = []
        for r in diffs:
            ccur.execute(
                """UPDATE dbo.Products SET DefaultDiscountPercentage = ?
                   OUTPUT inserted.ProductCode, inserted.ProductName,
                          deleted.DefaultDiscountPercentage, inserted.DefaultDiscountPercentage
                   WHERE StoreName = 'NMA' AND ProductCode = ?""",
                r["nmc_discount"], r["nma_code"],
            )
            row = ccur.fetchone()
            if row:
                updated.append(row)

        print(f"\n=== UPDATE executed inside transaction: {len(updated)} row(s) affected ===")

        if len(updated) != len(diffs):
            print(f"MISMATCH: dry-run counted {len(diffs)} eligible rows but UPDATE "
                  f"affected {len(updated)}. Rolling back -- no changes committed.")
            cconn.rollback()
            return

        cconn.commit()
        print("COMMITTED.")

        print("\n--- Updated NMA rows ---")
        print("ProductCode | ProductName | OldDiscount% -> NewDiscount%")
        for pc, name, old, new in updated:
            print(f"{pc} | {(name or '')[:30]} | {old} -> {new}")
    except Exception:
        cconn.rollback()
        raise


if __name__ == "__main__":
    cconn, diffs = dry_run()
    if "--execute" in sys.argv:
        execute_update(cconn, diffs)
    else:
        print("\n(dry run only -- pass --execute to apply these updates)")
