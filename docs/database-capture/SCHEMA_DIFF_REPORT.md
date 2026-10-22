# Schema difference report

Capture: `docs/database-capture/nexora_schema_reference.sqlite`
Opened and queried after capture. Source: `NEXORA_PLATFORM` on SQL Server 2014 (12.0.2000.8). One read-only connection. No migration was executed. No row samples were copied. This is not a backup.

`OrderHeaderDetails` is not in this database (0 matching tables). It stays on OrderNMC.

| Object | Class | Captured | Expected from repo | Action |
|---|---|---|---|---|
| `procurement.procurement_cycles`, `procurement_refreshes`, `procurement_virtual_products`, `procurement_order_items`, `procurement_order_item_assignments` | NO_CHANGE | Present. 23 procurement tables, 440 columns. | Existing platform migrations. | Do not recreate. |
| `procurement.rule_definition` and the other 0026 tables | MISSING_OBJECT | Absent. `procurement_refreshes.rule_snapshot_id` absent. | `0026_procurement_rules_registry.sql` | Apply only on an authorized non-production target, after backup. |
| `procurement.vpl_history_batch`, `vpl_history_line` | MISSING_OBJECT | Absent. | `0027_vpl_history.sql` | Same gate. 0027 does not require 0026 because `rule_snapshot_id` has no foreign key. |
| `procurement_order_items.row_version` | ALTER_REQUIRED | Column absent (28 columns captured, no `row_version`). | 0027 adds `INT NOT NULL DEFAULT 1`. | Same gate. Rollback must drop the default constraint first. |
| `supplier_export_settings` | NO_CHANGE | Present. Store + supplier key only. | No store-default or system-default table in the repo. | DECISION_REQUIRED before adding tiers. |
| Confirmed supplier pending column | UNVERIFIED | Not identified in this column list. | Do not invent one. | Remains blocked. |
| Applied migration ledger | UNVERIFIED | Not queried. | Repo SQL files are the source of the scripts, not proof they ran. | Compare `sys.tables` as above; do not replay blindly. |

Preflight before any apply: `SELECT DB_NAME()` must be the authorized database, not shared `NEXORA_PLATFORM`, unless the owner explicitly approves production. Post-check: `0026` and `0027` verify scripts expect `ok = 1`.

## OrderNMC OrderHeaderDetails (live read, 2026-10-19)

Separate source. Not the platform capture above, and not a backup.

One read-only connection. `DB_NAME()` returned `OrderNMC` on `CLIENT-3\SQLEXPRESS`. No other OrderNMC table was queried for rows. No write.

`dbo.OrderHeaderDetails`: **5914 rows**, **9 columns**, no extras beyond the insert list in `order_process.py`.

| Column | Type | Null |
|---|---|---|
| StoreName | varchar(50) | YES |
| OrderId | bigint | NO |
| OrderNo | int | YES |
| OrderDateTime | datetime | YES |
| LastSaleBillNo | varchar(50) | YES |
| LastBillDateTime | datetime | YES |
| LastGRN | bigint | YES |
| MinDays | int | YES |
| MaxDays | int | YES |

Three newest rows were read. Store name, `LastSaleBillNo`, and `LastGRN` were redacted in the notes. `LastGRN` is `bigint`, which matches a numeric watermark, not a new text column. `LastBillDateTime` on those three rows was midnight. That sample does not prove the time component for every row. `docs/database-capture/nexora_schema_reference.sqlite` was not present during this pass, so the earlier platform schema-and-counts note was not re-queried here.

## Checksums

| File | SHA-256 |
|---|---|
| `0026_procurement_rules_registry.sql` | `862c97e6d5ff5954ccb87e058fa76578f793b7e0dfcffef823c6ad24448a67c2` |
| `0026_procurement_rules_registry_rollback.sql` | `6e2904e9fa93cc83035bc93717f2a750fbf54217320261994e5b273d87cf188e` |
| `0026_procurement_rules_registry_verify.sql` | `c7455b007f58a1fb9055013d2d078da9b0b35fa865b68574b207ec1c97a63c6d` |
| `0027_vpl_history.sql` | `84d57d56214f750e2b320ba92ecbdf979582387b42cf3ca8536ad8fb9b240b8a` |
| `0027_vpl_history_rollback.sql` | `a06e2e5f26cce8996fa01723bbbefd5dcd33e8c56460682672c1d2c54cb67f57` |
| `0027_vpl_history_verify.sql` | `2932fdca3b8361b55c132c1006599433808db7d942b9e9f3ad9d039b1517c1b7` |
