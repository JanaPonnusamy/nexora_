"""Sale Analysis — grouped product-trend report (summary + detail).

A "group" is a saved, named set of product codes (e.g. the whole "Friends Adult
Diaper" family) that the user builds by searching products by name or supplier.
The report then reports, per group and per product, current stock vs sales over a
chosen window with an excess-stock / stock-cover-days view driven by a target
cover period. Read-only over the synced ``sync.*`` data; group definitions are
persisted in NEXORA_PLATFORM (``dbo.sale_analysis_group`` / ``_group_item``).
"""
