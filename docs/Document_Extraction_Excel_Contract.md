# Document Extraction Engine — Excel Export Contract (frozen)

Status: Frozen before Chunk 5 begins; **binding on Chunk 13 (Excel Export)** — `export_excel.py` must populate exactly these sheets/columns/order/types, not invent its own layout when it's eventually built.

One workbook per export call. A batch export (`POST /exports` with multiple `import_ids`) produces **one workbook** containing all selected invoices — Sheets 1, 3, 4, 5 get one row per invoice (or per invoice × sub-item, e.g. one GST slab row per rate), Sheet 2 gets one row per product line across every included invoice. Every sheet carries `Import ID` and `Invoice Number` as its first two columns specifically so rows from different invoices in the same batch stay traceable after the file leaves this system.

`csv` export format is Sheet 2 (Products) only, per the API doc's existing constraint — single-table format can't represent five sheets.

---

## Sheet 1 — Invoice Header

One row per invoice in the export batch.

| # | Column | Source | Type | Required |
|---|---|---|---|---|
| 1 | Import ID | `doc_import.import_id` | integer | Yes |
| 2 | Supplier Name | `supplier_name` | text | Yes |
| 3 | GST Number | `gst_number` | text | No |
| 4 | DL Number | `dl_number` | text | No |
| 5 | Invoice Number | `invoice_number` | text | Yes |
| 6 | Invoice Date | `invoice_date` | date | Yes |
| 7 | Invoice Type | `invoice_type` | text | No |
| 8 | Order Number | `order_number` | text | No |
| 9 | Transport | `transport` | text | No |
| 10 | Salesman | `salesman` | text | No |
| 11 | Credit Days | `credit_days` | integer | No |
| 12 | Gross Amount | `gross_amount` | decimal(18,2) | No |
| 13 | Discount Amount | `discount_amount` | decimal(18,2) | No |
| 14 | Scheme Discount | `scheme_discount` | decimal(18,2) | No |
| 15 | Cash Discount | `cash_discount` | decimal(18,2) | No |
| 16 | Taxable Amount | `taxable_amount` | decimal(18,2) | No |
| 17 | CGST Amount | `cgst_amount` | decimal(18,2) | No |
| 18 | SGST Amount | `sgst_amount` | decimal(18,2) | No |
| 19 | IGST Amount | `igst_amount` | decimal(18,2) | No |
| 20 | CESS Amount | `cess_amount` | decimal(18,2) | No |
| 21 | Round Off | `round_off` | decimal(10,2) | No |
| 22 | Net Amount | `net_amount` | decimal(18,2) | Yes |
| 23 | Item Count | `item_count` | integer | No |
| 24 | Total Quantity | `total_quantity` | decimal(18,3) | No |
| 25 | IRN Number | `irn_number` | text | No (e-invoice only) |
| 26 | Ack Number | `ack_number` | text | No (e-invoice only) |
| 27 | Ack Date | `ack_date` | date | No (e-invoice only) |
| 28 | Validation Status | `validation_status` | text | Yes |

## Sheet 2 — Products

One row per `doc_import_item` **excluding `is_excluded = 1` rows**, across every invoice in the batch.

| # | Column | Source | Type | Required |
|---|---|---|---|---|
| 1 | Import ID | `doc_import_item.import_id` | integer | Yes |
| 2 | Invoice Number | `doc_import.invoice_number` (joined) | text | Yes |
| 3 | Line No | `line_number` | integer | Yes |
| 4 | Product Code | `product_code` | text | No (null until Product Resolution runs — Chunk 9) |
| 5 | Product Name | `normalized_product_name` (fallback: `ocr_product_name`) | text | Yes |
| 6 | Pack | `pack` | text | No |
| 7 | HSN Code | `hsn_code` | text | No |
| 8 | Batch Number | `batch_number` | text | No |
| 9 | Expiry Date | `expiry_date` (fallback: raw `expiry_raw` text if unparsed) | date | No |
| 10 | Quantity | `quantity` | decimal(18,3) | Yes |
| 11 | Free Quantity | `free_quantity` | decimal(18,3) | No |
| 12 | PTR | `ptr` | decimal(18,4) | No |
| 13 | Purchase Rate | `purchase_rate` | decimal(18,4) | No |
| 14 | MRP | `mrp` | decimal(18,4) | No |
| 15 | GST % | `gst_percent` | decimal(5,2) | No |
| 16 | Discount % | `discount_percent` | decimal(5,2) | No |
| 17 | Discount Amount | `discount_amount` | decimal(18,2) | No |
| 18 | Amount | `amount` | decimal(18,2) | Yes |
| 19 | Confidence | `confidence` | decimal(5,2) | No |

## Sheet 3 — GST Summary

One row per (invoice, GST slab) pair, unpacked from `doc_import.gst_slab_breakup_json`.

| # | Column | Source | Type | Required |
|---|---|---|---|---|
| 1 | Import ID | `doc_import.import_id` | integer | Yes |
| 2 | Invoice Number | `doc_import.invoice_number` | text | Yes |
| 3 | GST Rate % | slab `rate` | decimal(5,2) | Yes |
| 4 | Taxable Amount | slab `taxable` | decimal(18,2) | Yes |
| 5 | CGST Amount | slab `cgst` | decimal(18,2) | No |
| 6 | SGST Amount | slab `sgst` | decimal(18,2) | No |
| 7 | IGST Amount | slab `igst` | decimal(18,2) | No |
| 8 | Total GST Amount | slab `cgst + sgst + igst` (or slab `total` if present) | decimal(18,2) | Yes |
| 9 | Net Amount | slab `net` | decimal(18,2) | No |

## Sheet 4 — Validation Errors

One row per finding, unpacked from `doc_import.validation_json` across every invoice in the batch. An invoice with zero findings contributes zero rows (not a blank placeholder row).

| # | Column | Source | Type | Required |
|---|---|---|---|---|
| 1 | Import ID | `doc_import.import_id` | integer | Yes |
| 2 | Invoice Number | `doc_import.invoice_number` | text | Yes |
| 3 | Rule Code | finding `rule_code` | text | Yes |
| 4 | Severity | finding `severity` | text (`ERROR`\|`WARNING`) | Yes |
| 5 | Field | finding `field` | text | No |
| 6 | Line No | resolved from finding `item_id` → `doc_import_item.line_number` | integer | No (blank = header-level) |
| 7 | Message | finding `message` | text | Yes |
| 8 | Expected Value | finding `expected_value` | text | No |
| 9 | Actual Value | finding `actual_value` | text | No |

## Sheet 5 — OCR Metadata

One row per invoice — a confidence/audit summary, not a bounding-box dump (bounding boxes aren't persisted in V1; see Design doc §15).

| # | Column | Source | Type | Required |
|---|---|---|---|---|
| 1 | Import ID | `doc_import.import_id` | integer | Yes |
| 2 | Invoice Number | `invoice_number` | text | Yes |
| 3 | Source Type | `source_type` | text | Yes |
| 4 | Page Count | `page_count` | integer | No |
| 5 | OCR Confidence % | `ocr_confidence` | decimal(5,2) | No |
| 6 | Supplier Match Method | `supplier_match_method` | text | No |
| 7 | Supplier Match Confidence % | `supplier_match_confidence` | decimal(5,2) | No |
| 8 | Uploaded At | `uploaded_at` | datetime | Yes |
| 9 | Reviewed At | `reviewed_at` | datetime | No |
| 10 | Exported At | this export event's `exported_at` | datetime | Yes |

---

## Formatting rules (binding on Chunk 13)

- Header row on every sheet: bold, frozen (Excel "freeze panes" on row 1) so it stays visible while scrolling.
- Date columns: `YYYY-MM-DD`. Datetime columns: `YYYY-MM-DD HH:MM:SS` (local time of the exporting server — no timezone conversion asked for or performed).
- Decimal columns: plain numeric Excel cells (not text), so the importing pharmacy software can sum/filter them directly — never format currency with a locale symbol baked into the cell text.
- Column order above is fixed. Adding a column later is additive-only (append at the end of the relevant sheet); never reorder or remove a column without a new contract version, since the whole point of freezing this now is that downstream pharmacy-software import mappings can be built against it without breaking later.
