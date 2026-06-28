# Evidence & Traceability

Evidence is the backbone of LPIE: **every documented behaviour must trace to a concrete source.** This
folder holds the master evidence log and the rules for citing it.

## Evidence reference format

Use a stable, copy-pasteable reference in every `Evidence Source` field:

| Source type | Reference format | Example |
|-------------|------------------|---------|
| VB.NET code | `vb:<File>:<line>` | `vb:Form1.vb:1442` |
| Python code | `py:<path>:<line>` | `py:procurements/services/cycle_service.py:10` |
| Stored procedure | `sp:<ProcName>` | `sp:nx_sp_BuildVirtualProductList` |
| Table/Column | `db:<Table>.<Column>` | `db:customer_demands.mobile` |
| Captured SQL | `rt:<operation>#<n>` | `rt:LoadOrderData#1` |
| Screen | `ui:<Screen>` | `ui:OrderProcess` |
| Report/Export | `rpt:<name>` / `exp:<name>` | `exp:SupplierCSV` |

## Rules

- Every row in every catalog/template cites at least one reference above.
- Add a corresponding line to `evidence_log.md` the first time a source is used.
- If a behaviour cannot be evidenced, mark it `Status: Draft` and add an Open Question — **do not** state
  it as fact.
