# Database Inventory — OrderNMC (Legacy)

> **Source:** OrderNMC (SQL Server). **Read-only.** Populate from the extraction scripts in
> `../queries/`. Every row must cite evidence. Status: `Empty`.

## 1. Tables

| # | Table | Purpose (observed) | Rows (approx) | Procurement Relevance | Evidence |
|---|-------|--------------------|---------------|-----------------------|----------|
| | | | | High / Medium / Low / None | extraction run / SP / screen |

## 2. Columns (per table)

> One sub-section per relevant table. Capture exactly as extracted — do not rename or interpret.

### Table: `<name>`

| Column | Data Type | Nullable | Default | PK | FK → | Notes (observed) | Evidence |
|--------|-----------|----------|---------|----|------|------------------|----------|
| | | | | | | | |

## 3. Primary Keys

| Table | PK Columns | Constraint Name | Evidence |
|-------|-----------|-----------------|----------|

## 4. Foreign Keys

| FK Constraint | Child Table.Column | → Parent Table.Column | On Delete/Update | Evidence |
|---------------|--------------------|-----------------------|------------------|----------|

## 5. Constraints (Check / Unique / Default)

| Table | Constraint | Type | Definition | Evidence |
|-------|-----------|------|------------|----------|

## 6. Indexes

| Table | Index | Columns | Unique | Type (Clustered/NC) | Evidence |
|-------|-------|---------|--------|---------------------|----------|

## 7. Views

| View | Purpose (observed) | Base Tables | Procurement Relevance | Evidence |
|------|--------------------|-------------|-----------------------|----------|

## 8. Stored Procedures

| Procedure | Purpose (observed) | Reads | Writes | Called From (screen/code) | Evidence |
|-----------|--------------------|-------|--------|---------------------------|----------|

## 9. Functions

| Function | Type (Scalar/Table) | Purpose (observed) | Evidence |
|----------|---------------------|--------------------|----------|

## 10. Triggers

| Trigger | Table | Event (I/U/D) | Behaviour (observed) | Evidence |
|---------|-------|---------------|----------------------|----------|

## 11. Open questions / anomalies

| # | Observation | Why it matters | Evidence | Resolution |
|---|-------------|----------------|----------|------------|
