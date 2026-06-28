# Schema Extraction Scripts (READ-ONLY)

These scripts extract **metadata only** from OrderNMC. They **never** modify data or schema
(SELECT-only against `INFORMATION_SCHEMA` and `sys.*`). Output feeds `../database/database_inventory.md`.

## Usage

- Run `extract_schema_metadata.sql` against the **OrderNMC** database with a read-only login.
- Each numbered section corresponds to an inventory section. Paste results into the matching table.
- Record the run (date, server, who ran it) in `../evidence/evidence_log.md`.

> Do not add INSERT/UPDATE/DELETE/DDL here. This folder is strictly read-only extraction.
