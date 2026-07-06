/* Procurement — Phase 3 (Decision Engine): explainability + metric columns.
   Target database: NEXORA_PLATFORM (SQL Server).

   The Decision Engine computes business rules in Python and bulk-writes the
   results onto procurement_virtual_products. PR-BR-015 mandates that EVERY
   evaluated product (included AND excluded) stores a reason code + reason text.
   PR-BR-012 publishes window metrics used by the protection floors.

   Adds (idempotent):
     reason_code       — inclusion/exclusion controlled vocabulary (PR-BR-015)
     reason_text       — human-readable explanation (PR-BR-015)
     window_sales_qty  — SUM(qty) over the rolling window (PR-BR-012)
     billing_frequency — COUNT(DISTINCT bill) over the window (PR-BR-012)

   The final-quantity determinant (COVERAGE | SPIKE_PROTECTION |
   MAX_BILL_TRIGGER) reuses the existing trigger_reason column; INCLUDE/EXCLUDE
   reuses the existing procurement_action column.
*/

IF COL_LENGTH('procurement.procurement_virtual_products', 'reason_code') IS NULL
    ALTER TABLE procurement.procurement_virtual_products
        ADD reason_code VARCHAR(50) NULL;
GO
IF COL_LENGTH('procurement.procurement_virtual_products', 'reason_text') IS NULL
    ALTER TABLE procurement.procurement_virtual_products
        ADD reason_text VARCHAR(500) NULL;
GO
IF COL_LENGTH('procurement.procurement_virtual_products', 'window_sales_qty') IS NULL
    ALTER TABLE procurement.procurement_virtual_products
        ADD window_sales_qty DECIMAL(18,3) NULL;
GO
IF COL_LENGTH('procurement.procurement_virtual_products', 'billing_frequency') IS NULL
    ALTER TABLE procurement.procurement_virtual_products
        ADD billing_frequency INT NULL;
GO
