# Document Extraction Engine — Excel Export Contract (frozen)

Status: Frozen before Chunk 5 begins; **binding on Chunk 13 (Excel Export)** — `export_excel.py` must populate exactly these sheets/columns/order/types, not invent its own layout when it's eventually built.

One workbook per export call. A batch export (`POST /exports` with multiple `import_ids`) produces **one workbook** containing all selected invoices. Sheet 2 is the exact pharmacy-import layout requested by the business. Sheet 3 retains the normalized OCR product rows with `Import ID` and `Invoice Number` so batch exports remain traceable.

`csv` export format is Sheet 2 (Products) only, per the API doc's existing constraint — single-table format can't represent six sheets.

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

One row per non-excluded invoice line, in the exact pharmacy-import column order supplied for this feature. Available reviewed OCR fields are mapped directly; unsupported numeric fields use `0`, boolean flags use `FALSE`, and unsupported identifiers remain blank. Expiry is exported as `MM/YY` for compatibility.

| # | Column |
|---:|---|
| 1 | No |
| 2 | Product Name |
| 3 | Packing |
| 4 | Batch |
| 5 | Qty |
| 6 | Free |
| 7 | Rate |
| 8 | Tax % |
| 9 | PDisc. |
| 10 | Amount |
| 11 | Mfr |
| 12 | DC |
| 13 | PDisc.Amount |
| 14 | CSt.Amount |
| 15 | St.Amount |
| 16 | Goods Value |
| 17 | Prod. Code |
| 18 | SDisAmt |
| 19 | CashDiscAmt |
| 20 | Exp.dt |
| 21 | Mrp |
| 22 | Sales |
| 23 | Drugs |
| 24 | PTR |
| 25 | Batchid |
| 26 | Net Rate |
| 27 | Net Rate Amount |
| 28 | OFFER |
| 29 | OFFER RATE |
| 30 | MRP VALUE |
| 31 | PackCode |
| 32 | PTS |
| 33 | DC-REF |
| 34 | OfferType |
| 35 | Cdis |
| 36 | Sdis |
| 37 | Case |
| 38 | GodownID |
| 39 | Repl |
| 40 | SchOfferId |
| 41 | OfferSlno |
| 42 | Sch.Dis |
| 43 | Sch.DisAmt |
| 44 | MixedCase |
| 45 | Parentid |
| 46 | autodisc |
| 47 | volume |
| 48 | SplOfferid |
| 49 | SplDis |
| 50 | SplDisAmt |
| 51 | Pdisc% |
| 52 | TotalVolume |
| 53 | SO no |
| 54 | SO Sno |
| 55 | Gross Weight |
| 56 | Edited-Spldisc |
| 57 | Edited-Schdisc |
| 58 | SpL Zero |
| 59 | Sch Zero |
| 60 | SplZeroId |
| 61 | SchZeroID |
| 62 | SGST |
| 63 | CGST |
| 64 | IGST |
| 65 | GST Cess |
| 66 | Abate Perc |
| 67 | GST Based on |
| 68 | HSN Code |
| 69 | Rate Changable |
| 70 | Mixed case(qty) |
| 71 | Rate pack |
| 72 | Alias Code |
| 73 | Calamity CESS |
| 74 | Remarks |
| 75 | Calamity % |
| 76 | Extra Cess / Base Unit |
| 77 | Extra Cess Amt |
| 78 | Tax Slab Code |
| 79 | HQ Approval Status |

## Sheet 3 — OCR Products

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

## Sheet 4 — GST Summary

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

## Sheet 5 — Validation Errors

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

## Sheet 6 — OCR Metadata

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
- Column order above is fixed. The 79-column Products layout must never be reordered; OCR Products remains the audit/traceability view for multi-invoice exports.
