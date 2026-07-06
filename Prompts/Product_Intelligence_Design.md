# Product Intelligence Workspace - UI Design

## Purpose
The Product Intelligence Workspace extends the existing Procurement Refresh/VPL workflow.
It DOES NOT replace Refresh or VPL.

Workflow:

```
Order Cycle
    ↓
Refresh
    ↓
VPL Creation
    ↓
Load Product Intelligence Grid
```

## Design Principles

- No hardcoded stores.
- Multi-tenant.
- Read active stores dynamically.
- Grid built dynamically.
- VPL remains the source list.
- Product matching uses Common Product Mapping.
- No calculations inside UI.

## Screen Layout

### Toolbar

- Refresh Selector
- Snapshot
- Search
- Supplier Filter
- Manufacturer Filter
- Export

### Main Grid

Columns:

1. Product Code
2. Product Name
3. Consolidated Suggested Qty
4. Consolidated Purchase Qty
5. One dynamic column per active store

Each store column shows:

- Suggested Qty
- Current Stock

If product is unavailable in a store:

Cell remains blank.

Hover loads:

- Previous Sales
- Previous Purchases
- Last Sale Date
- Last Purchase Date
- Non Moving Days

### Right Detail Panel

- Supplier Details
- Purchase Rate
- Margin
- Last Purchase
- Scheme
- Stock Distribution

### Bottom Charts

1. Sales Trend
2. Purchase Trend
3. Store Comparison
4. Stock Trend
5. Price Trend
6. Non Moving Trend

## Product Intelligence Engine

When grid loads:

```
Read VPL

↓

Resolve Common Product

↓

Find Products in all Active Stores

↓

Calculate

↓

Populate Grid
```

## Consolidated Formula

```
Consolidated Suggested

=
SUM(Store Suggested Qty)

Consolidated Purchase

=
MAX(0,
SUM(Store Suggested Qty)
-
SUM(Store Stock))
```

Rows are never removed.

Negative purchase quantity becomes zero.

## Internal Transfer

Products remain visible even when purchase quantity becomes zero.

Reason:

Another store may contain excess stock.

The workspace must highlight redistribution opportunities.
