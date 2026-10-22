# 09 — Test coverage and risk register

No test suite was executed. Production data was not used. Coverage below is from file names and the functions they are known to call.

## Present

| Area | Test | Gap left |
|---|---|---|
| Nexora sizing | `tests/test_procurement_decision_engine.py` (PARA-500 pack ceiling, exclusions) | Does not assert the agreed gross MAX of avg×18, max bill, max day, **avg bill**. Does not use TotalStock. |
| Nexora workflow | `tests/test_procurement_pm_workflow.py` | Assign and export validations. Not the VB keyboard. |
| Nexora orchestration / GRN | `tests/test_procurement_orchestration.py`, `tests/test_procurement_sprint3.py` | Receipt math. Not Not-Supplied release. |
| Legacy workflow | `tests/test_legacy_order_workflow.py` | Finalize guards. Not `FetchSourceData`. |
| Legacy auth | `backend/tests/test_legacy_order_store_access.py` | Store scope. Not VB Role 1/2. |
| Product mapping | `product_mapping` unit tests around `scoring.py` (AUTO_MIN) | Not the 180-day warning. |

## Missing (required before calling a phase done)

| ID | Case | Why it matters |
|---|---|---|
| T-01 | VB local SQL vs agreed formula on the two numeric examples in the rulebook | Stops a silent blend |
| T-02 | `transactionvalidity` values for a cancelled bill and a modified bill | C-07, C-09 are UNKNOWN |
| T-03 | Two lines, one bill, same product | Avg bill and max bill |
| T-04 | Two timestamps, one calendar day | VB groups raw datetime |
| T-05 | `DontConsiderInOrder = 1` excluded from qty and from skip release | carry_forward_skips omits the flag |
| T-06 | SaleUnit 0 blocks; does not become 1 or loose units | C-12 |
| T-07 | TotalStock 40, StockInHand 10, same sales | Profile must follow TotalStock |
| T-08 | Confirmed pending 20 reduces packs; draft assignment does not | C-13 |
| T-09 | Partial receipt 4 of 10 leaves pending 6 | reconciliation_rules already; need a row test |
| T-10 | Not Supplied releases pending and keeps the original export row | New |
| T-11 | Sale after receipt below min-days stays suppressed | C-17 |
| T-12 | `until_next_demand` stays when a sale exists but new suggested qty is 0; releases when suggested qty > 0 even if the skip’s sale check would differ | Defect regression |
| T-13 | `until_next_sales` releases only on a valid sale, then eligibility | C-15 |
| T-14 | Margin below threshold warns; monopoly price change warns; no auto overwrite of manual supplier | C-19 |
| T-15 | Purchase older than 90 days → stale label, not ranked | C-20 |
| T-16 | PTR 100, 10% , 10+2 → 75 on a fixture row | Formula unit test |
| T-17 | Fuzzy match score 94 stays unassigned until confirm | scoring.py AUTO_MIN 96 |
| T-18 | Second export creates a new file record and does not call the portal | C-23 |
| T-19 | Excel exception does not set exported | C-24 |
| T-20 | Portal retry does not submit a line that already has a portal order id | OrderBot has no id today |
| T-21 | Unknown availability blocks portal and allows Excel override | New |
| T-22 | Role 2 cannot start Process Order; Role 1 can, still not via the passcode UI | C-32 |
| T-23 | Two sessions, one active order, second start rejected | C-33 |
| T-24 | Store switch drops in-flight response | C-31 |
| T-25 | Up/Down saves qty; failed save stays on the row | C-27 |
| T-26 | Delete on All does nothing; Delete on a supplier filter hides the row only | C-29 |
| T-27 | Bulk Not Supplied shows count and does nothing until confirm | New |
| T-28 | Layout reset restores default columns; hidden optional column does not remove Order Qty | New |
| T-29 | Close with outstanding receipt is allowed; close is blocked only when the summary is dismissed without confirm | Agreed close rule |
| T-30 | Additional-row fixture is not on the Qty Check list | C-14 |

## Risks

| Risk | Severity | Note |
|---|---|---|
| Building the grid on `decision_rules.evaluate` as it stands | High | Changes packs vs VB on spiky and avg-bill items, and uses StockInHand |
| Treating OrderBot click as success | High | `place_order` does not read an order id |
| VB delete-and-insert generation | High | A “refresh” that calls `InsertDataIntoDestination` removes live edits from `OrderManagement` after backup |
| Plain password in `Users.Password` and in portal config files | High | Do not copy those values into docs or git |
| `until_next_demand` sale release | High | Confirmed in current Nexora |
| 1366×768 with three panels open | Medium | Prior audit: drawer must be collapsed by default |
