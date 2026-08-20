/* Procurement — Supplier Order Optimization Engine: explicit opt-in flag.
   Target database: NEXORA_PLATFORM (SQL Server).

   Adds procurement.supplier_min_order.consider_minimum_order — until now any
   supplier with a min_order_value > 0 was automatically pulled into the
   Optimization engine. This makes participation an explicit per-supplier
   choice (default FALSE for every row, no backfill): a configured
   min_order_value alone no longer enrolls a supplier in Optimization.

   Idempotent.
*/

IF COL_LENGTH('procurement.supplier_min_order', 'consider_minimum_order') IS NULL
    ALTER TABLE procurement.supplier_min_order
        ADD consider_minimum_order BIT NOT NULL DEFAULT 0;
GO
