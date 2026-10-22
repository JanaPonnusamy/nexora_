# Phase 0 status

| Field | Value |
|---|---|
| Phase | 0 — golden formula fixture |
| Status | COMPLETE |
| Contract | `docs/procurement-workspace-unification/contracts/Procurement_Workspace_Master_Phase_Prompts.md` |
| Control | `docs/procurement-workspace-unification/AUTONOMOUS_WORK_CONTROL.md` |
| Last update | 2026-10-19 21:15 IST |
| Migration | none proposed, none applied |
| Production quantity code | unchanged (`decision_rules.py` not edited) |
| Later phases | not started |

## Tests

`python -m pytest tests/test_procurement_formula_compare.py -q`

Result: **14 passed**, 1 warning (pytest could not write `.pytest_cache`; not a test failure).

Legacy figures are a Python transcription of `order_local.sql` plus the Additional Row zeroing in `order_process.py`. The test checks those clauses exist in the SQL file and that `Form1.vb` contains `DATEADD(day, -10, GETDATE())`. SQL Server was not executed.

## Three-way results (packs)

| Case | Target | Legacy SQL orderable | VB Form1 (recency 10) | Nexora `evaluate` |
|---|---|---|---|---|
| spike day/bill (180 sold, max day 80, stock 30, pack 10) | 5 auto | 1 | 1 | 5 |
| avg bill binds (max day/bill/line 20, avg bill 45) | 2 auto | 1 | 1 | 1 |
| confirmed pending 20 | 3 auto | 1 (pending ignored) | 1 | **excluded** (pending added to stock, cover looks adequate) |
| SaleUnit 0 or null | blocked, no packs | 0 excluded | 0 | **50 loose units** |
| zero sales | excluded | excluded | excluded | excluded |
| last sale 20 days ago | review list | excluded | excluded | excluded |
| last sale 12 days ago, parameter 15 | 5 | 1 | **excluded** | 5 when recency argument is 15; **excluded** at the engine default of 10 |
| TotalStock 40, StockInHand 10 | 1 (uses 40) | 0 | 0 | 3 (uses 10) |
| rare mover | 1, not auto-orderable | SQL insert 1, then **0** (status 2) | same | 1 included |
| DontConsider with sales still passed in | excluded | **still orders 1** (no product-level flag in the SQL) | same | excluded |
| same calendar day, max day 80 | 5 | 1 | 1 | 5. If the day splits on time into 40, Nexora drops to 1; legacy OrderQty does not change |
| 6 lines, 1 bill, qty 60, stock 5 | 6 | 1 | 1 | 6 |

## Unknowns left explicit

- `transactionvalidity` values for cancelled and modified bills are not mapped.
- Whether `Transactiondate` contains a time is not verified. The same-day case records both interpretations.
- Confirmed supplier pending has no single verified source column. The fixture only shows what each formula does with the number 20.

## Rollback

Delete `tests/procurement_formula_compare.py`, `tests/test_procurement_formula_compare.py`, and this status note. No runtime behavior depends on them.

## Next authorized action

Stop. Phase 1 starts only after this report is accepted.
