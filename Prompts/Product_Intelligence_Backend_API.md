# Product Intelligence Workspace - Backend Specification

## Module

procurement.product_intelligence

## Database

### procurement_refresh_master

- refresh_id
- tenant_id
- cycle_id
- refresh_date
- created_by
- status

### procurement_vpl

Existing table.

### supplier_product_match

Existing mapping table.

### product_intelligence_cache

Columns

- cache_id
- refresh_id
- tenant_id
- vpl_id
- common_product_id
- consolidated_suggest_qty
- consolidated_purchase_qty
- generated_on

### product_intelligence_store

One row per Store.

Columns

- cache_store_id
- cache_id
- store_id
- product_id
- stock_qty
- suggested_qty
- avg_sale
- last_sale_date
- last_purchase_date
- non_moving_days

No fixed store columns are stored.

Store count is dynamic.

## APIs

### POST

/api/procurement/intelligence/build

Build Product Intelligence cache
from latest Refresh + VPL.

### GET

/api/procurement/intelligence

Returns grid.

### GET

/api/procurement/intelligence/{cache_id}

Returns product details.

### GET

/api/procurement/intelligence/{cache_id}/stores

Returns dynamic store metrics.

### GET

/api/procurement/intelligence/{cache_id}/hover/{store_id}

Returns

- last sale
- last purchase
- sales history
- purchase history
- non moving days

Used only for hover popup.

### GET

/summary

Returns

- total products
- purchase quantity
- transfer quantity
- stock quantity

## Backend Flow

```
Refresh

↓

VPL

↓

Resolve Common Product

↓

Discover Active Stores

↓

Collect Product Data

↓

Calculate Consolidated Values

↓

Populate Cache

↓

UI Reads Cache Only
```

## Rules

- No hardcoded stores.
- Store discovery by tenant metadata.
- UI never queries transaction tables directly.
- Cache rebuilt on every Refresh.
- Product rows always remain visible.
- Blank cells indicate product not mapped in that store.
- Hover endpoint provides historical information.
