"""Pass Gen service — generation only (no validation)."""

from modules.pass_gen import repository
from modules.pass_gen.passcode import generate_compact_passcode
from modules.pass_gen.schemas import (
    GenerateRequest,
    GenerateResponse,
    GenerateRowResult,
    PassGenResult,
)


def list_stores(tenant_id=None):
    return repository.list_stores(tenant_id)


def set_store_code(store_id, numeric_code):
    repository.set_numeric_code(store_id, numeric_code)
    return repository.list_stores()


def generate(request: GenerateRequest) -> GenerateResponse:
    """Generate a passcode per (row, store). Rows are independent — each carries
    its own day range and flags; Order No and target date are shared."""
    stores = {s['store_id'].upper(): s for s in repository.list_stores()}

    row_results = []
    for row in request.rows:
        selected = (
            [stores[sid.upper()] for sid in row.store_ids if sid.upper() in stores]
            if row.store_ids
            else list(stores.values())
        )

        results, skipped = [], []
        for store in selected:
            if store['numeric_code'] is None:
                # Unmapped store: no numeric code, so no passcode can be built.
                skipped.append(store['store_code'])
                continue
            results.append(
                PassGenResult(
                    store_id=store['store_id'],
                    store_code=store['store_code'],
                    store_name=store['store_name'],
                    numeric_code=store['numeric_code'],
                    passcode=generate_compact_passcode(
                        store['numeric_code'],
                        request.order_no,
                        row.min_days,
                        row.max_days,
                        row.order_yes,
                        row.compare_last_order,
                        request.target_date,
                    ),
                )
            )

        row_results.append(
            GenerateRowResult(row_id=row.row_id, results=results, skipped=skipped)
        )

    return GenerateResponse(rows=row_results)
