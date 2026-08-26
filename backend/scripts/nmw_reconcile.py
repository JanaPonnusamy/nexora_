"""Reconcile the NMW mirror against the store's live source PSI.

Removes mirror ProductSaleInformation rows the source POS no longer has (lines
superseded by a bill modification and moved to MProductSaleInformation). Safe to
re-run / schedule; a bill whose current rows have not synced yet is skipped.

Usage (from backend/, with backend/.venv):
    python scripts/nmw_reconcile.py               # dry run (preview only)
    python scripts/nmw_reconcile.py --apply       # delete orphan rows
    python scripts/nmw_reconcile.py --apply --tenant <GUID> [--store <GUID>]
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.database import get_connection  # noqa: E402
from modules.nmw_sales_report import reconcile, repository  # noqa: E402


def _default_tenant():
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT TOP 1 CAST(tenant_id AS VARCHAR(50)) FROM dbo.stores "
            "WHERE UPPER(LTRIM(RTRIM(store_code))) = 'NMW'"
        )
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        cur.close()
        conn.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="delete orphan rows (default: dry run)")
    ap.add_argument("--tenant", default=None, help="tenant GUID (default: the NMW tenant)")
    ap.add_argument("--store", default=None, help="platform store GUID (default: the NMW warehouse)")
    args = ap.parse_args()

    tenant = args.tenant or _default_tenant()
    if not tenant:
        print("No NMW tenant found.", file=sys.stderr)
        return 2
    store = args.store or repository.get_nmw_store_id(tenant)
    if not store:
        print("No NMW warehouse store found for tenant.", file=sys.stderr)
        return 2

    result = reconcile.reconcile_store(tenant, store, apply_changes=args.apply)
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
