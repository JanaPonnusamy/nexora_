# 12 — Approval required before implementation

These are not requests to re-decide the prompt. They are facts the source cannot settle. Building past them would guess.

| ID | Blocker | What is known | What is missing |
|---|---|---|---|
| B-01 | `Users.Role` 1 and 2 | Menu split is verified (Form1.vb 288–300) | No lookup table or comment says 1 = Admin and 2 = PM. Confirm the integers before hiding Process Order. |
| B-02 | `transactionvalidity` and modified bills | Filter `= 0` is what both engines use | No code maps values to cancelled vs edited vs duplicate. Need one real bill of each, read-only. |
| B-03 | Calendar day | Nexora casts to date. VB groups `Transactiondate` as stored | Column type and whether a time component splits a day. Schema doc says the column exists; precision was not re-read. |
| B-04 | `SUM(Batches.Stock)` vs `TotalStock` vs `StockInHand` | Formula uses TotalStock in VB and StockInHand in Nexora | No sample was queried. Target stays TotalStock. The discrepancy report is blocked on a read-only query. |
| B-05 | Confirmed supplier pending source | VB `status=1` and `orqty` are the assigned qty. Nexora remaining is final−received after GRN | Which table is the pending balance for the **next** suggestion is not a single column. Need the owner to point at the row that means “supplier has accepted this qty”. |
| B-06 | Store-level export template | Only `procurement.supplier_export_settings` (store+supplier) exists in code | Where the store default and the system default live, or whether they must be added. |
| B-07 | Western Salem portal | Named in OrderBot README only | No selectors in `config.json`. PharmaRack is the only configured portal. |
| B-08 | Additional row | VB zeros it. Nexora orders 1. The prompt does not explicitly pick | Treat VB as current production behavior. Say if qty 1 should return. |
| B-09 | Schema for Not Supplied, portal line status, template version | Not present on `OrderManagement` as named columns | Approve a migration or name existing columns that already mean those states. |
| B-10 | Live database | Not connected this audit | Phases 1 and the stock sample cannot be verified until a read-only connection is allowed. |

Agreed parameters 90 / 15 / 13 / 18 / `Products.TotalStock` are not in this list. They stay as the target even where the code differs.
