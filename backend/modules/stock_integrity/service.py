from modules.stock_integrity import repository


def get_integrity_report(tenant_id, store_id=None):
    rows = repository.get_mismatches(tenant_id, (store_id or "").strip() or None)
    return {
        "rows": rows,
        "mismatch_count": len(rows),
    }


def get_sync_drift_report(tenant_id, store_id):
    """Compares live store DB Batches.Stock against what's currently synced.

    Tests the hypothesis that mismatches trace back to the sync pipeline
    rather than to batch-vs-total logic: if live and synced batch totals
    already disagree, TotalStock never had a chance to be right regardless
    of which formula is used against it.
    """
    live_positive = repository.get_live_positive_batches(store_id)
    synced_positive = repository.get_synced_positive_batches(tenant_id, store_id)

    live_totals, synced_totals = {}, {}
    for (product_code, _batch_code), stock in live_positive.items():
        live_totals[product_code] = live_totals.get(product_code, 0) + stock
    for (product_code, _batch_code), stock in synced_positive.items():
        synced_totals[product_code] = synced_totals.get(product_code, 0) + stock

    drifted = []
    for code in set(live_totals) | set(synced_totals):
        live_total = live_totals.get(code, 0)
        synced_total = synced_totals.get(code, 0)
        if live_total != synced_total:
            drifted.append(
                {
                    "product_code": code,
                    "live_batch_total": live_total,
                    "synced_batch_total": synced_total,
                    "difference": synced_total - live_total,
                }
            )

    names = repository.get_product_names(tenant_id, store_id, [d["product_code"] for d in drifted])
    for d in drifted:
        d["product_name"] = names.get(d["product_code"])

    drifted.sort(key=lambda d: (d["product_name"] or "", d["product_code"]))

    return {
        "rows": drifted,
        "drift_count": len(drifted),
        "live_product_count": len(live_totals),
        "synced_product_count": len(synced_totals),
    }


def repair_store(tenant_id, store_id, actor_user_id=None):
    """One-time backlog repair: corrects stale sync.Batches.Stock rows using
    live store data. Only pulls/compares rows where Stock > 0 on either side
    (diff_positive_batches), so genuinely-zero-on-both-sides rows are never
    fetched or touched. Only fixes rows that already exist in sync.Batches --
    see repository.repair_batch_stock docstring. Safe to re-run.
    """
    live_positive = repository.get_live_positive_batches(store_id)
    synced_positive = repository.get_synced_positive_batches(tenant_id, store_id)
    diffs = repository.diff_positive_batches(live_positive, synced_positive)
    result = repository.repair_batch_stock(tenant_id, store_id, diffs, actor_user_id)

    verify = get_integrity_report(tenant_id, store_id)
    return {
        "repaired": result["repaired"],
        "remaining_mismatches": verify["mismatch_count"],
    }
