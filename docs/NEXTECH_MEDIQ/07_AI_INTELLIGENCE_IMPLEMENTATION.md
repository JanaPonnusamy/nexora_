# NexTech MediQ — Phase 7 AI Intelligence Centre

**Date:** 2026-11-14  
**App:** `desktop/nextech-mediq` (Electron stays `22.3.27`)  
**Status:** One existing model path is integrated. The eight operational intelligence features are **not implemented**.

This document records what the code actually does. It does not treat a rolling average, a days-cover threshold, or a weighted supplier score as a model prediction.

No production config, production database, or `send_log.json` was changed. Nothing was committed. `192.168.10.32` was not contacted. No purchase order was submitted and no stock quantity was changed. `IMPLEMENTATION_MASTER_TRACKER.md`, login, session, tenant, store, and navigation files were not edited. `supplier-stock-client` and `quick-stock-client` were not edited. There is no `order-management-client` directory in this workspace. No backend route was added.

Live historical row counts were **not verified**. This session did not query SQL.

## 1. Audit — what AI actually exists

Search covered `backend/modules` (excluding vendored `site-packages`), the web app in `frontend/`, and the desktop clients. The only `anthropic.Anthropic()` call in application code is the shelf-category classifier.

### 1.1 Shelf-category classifier (the only model call)

| Item | Fact |
|---|---|
| Module | `backend/modules/procurement/product_category_ai.py` |
| Caller | `shelf_sort_service.classify_and_store` |
| HTTP | `POST /api/procurement/shelf-sort/classify?tenant_id=` in `pm_router.py` |
| Auth | `require_procurement_workspace` plus `assert_tenant_access` |
| Model name in source | `claude-opus-4-8` (`_MODEL`). The HTTP body does **not** echo this name. |
| SDK | Official Anthropic SDK, `messages.create`, structured JSON schema. Batch size 60. `max_tokens=8000`. |
| Input | Product names (1–2000) and an optional index-aligned `units` list (UnitDescription / pack text). |
| Output vocabulary | Fixed list in `export_document_service._SHELF_ORDER` (Tablet through Others). Invalid categories are dropped. |
| Persistence | Matching suggestions are upserted as `source='llm'`, `confirmed=false`. A suggestion does not overwrite a confirmed manual row (`product_category_repository.upsert`). |
| What it does not do | It does not set order quantity, stock, or purchase-order state. |

`llm_available` is `product_category_ai.is_available()`, which is only `bool(os.environ.get("ANTHROPIC_API_KEY"))`. It is not a live health check.

Degradation, from the source:

1. No names, or no `ANTHROPIC_API_KEY`: `classify()` returns `{}` without calling the API. The HTTP response is `{suggestions: {}, llm_available: false}` when the key is absent.
2. `anthropic` import fails, or `messages.create` / JSON parsing throws: `classify()` logs a warning and returns `{}`. If the key is still set, `classify_and_store` still returns `llm_available: true` with empty suggestions. The endpoint does not distinguish "model returned nothing valid" from "the call failed".
3. Shelf **sorting** does not call the LLM. `resolve_categories` is deterministic: learned table, then local UnitDescription / keyword rules (`_detect_category`), then another store's UnitDescription, then `Others`. Previously saved LLM suggestions are used only after a human or the classify endpoint has written them, and only as learned rows.

The web client already surfaces this honestly:

- `frontend/src/services/procurementService.ts` `shelfSortClassify`
- `frontend/src/pages/procurement/ShelfCategoryTrainingPage.tsx` — if `llm_available` is false, the page tells the user auto-suggest is off and leaves manual selection in place. It does not invent categories.

`GET /api/procurement/shelf-sort/categories` returns that fixed vocabulary. The handler has no auth dependency in `pm_router.py`. It is a list, not a prediction.

### 1.2 Other code that is not a model

Searched for `llm_available`, `anthropic`, `openai`, `sklearn`, `joblib`, `pickle.load`, and `transformers` under `backend/modules`. No second model client.

| Area | What it actually is |
|---|---|
| `decision_rules.py` | Pure business rules. `average_daily_sales` is window quantity / rolling days. `days_cover` is effective available / that average. `stock_status` is OUT / LOW / SAFE / OVERSTOCK from current cover cut-offs (`stock_low_cut` default 3, `stock_safe_cut` default 15). `suggested_qty` comes from those rules (coverage, spike protection, max-bill trigger, rare-mover top-up). |
| `intelligence_service.py` | Sums existing per-store suggested quantities and warehouse stock. Priority is CRITICAL / HIGH / MEDIUM / NONE from those sums. `confidence` there is the weakest **product-mapping** edge, not a forecast interval. `POST /api/procurement/intelligence/build` and `/refresh-build` write a procurement grid. This centre does not call them. |
| `suggestion_service.py` | Deterministic supplier rank. Weights: last purchase 40, frequency 30, PTR 20, live stock 10. |
| `abnormal_sales.py` | Ratio rule over a 90-day bill window. Abnormal if bill qty / average of other bills `>= 5`. Warning if `>= 3`. Needs at least 2 other counted bills. `GET /api/procurement/refreshes/{id}/abnormal-sales` reads that. `PUT .../sales/dont-consider` writes `DontConsiderInOrder`. This centre does not call either route. |
| `expiry_report` / `expiry_stock` | Supplier-ack settlement figures (given / received / pending). Not an expiry-risk model. |
| `document_extraction/preprocessing.py` | Comment plus a projection-profile orientation guess that the file itself says is not auto-applied. Not a loaded classifier. |
| PaddleOCR `cls=True` | OCR angle correction inside document extraction. Not operational intelligence. |
| `workspace_repository.py` comment | "client-side classifier" means the planning-state grid rules, not an LLM. |

Desktop `supplier-stock-client` and `quick-stock-client` have no `llm_available` or shelf-classify client. The web app's only LLM client is the training page above.

### 1.3 Historical data (code only)

A prior read of the procurement SQL (`docs/NEXORA_LEGACY_CONSOLIDATION/07_HISTORICAL_DATA_AND_PREDICTION_READINESS.md`) describes line-level sales in `sync.ProductSaleInformation`, GRN lines in `sync.PurchaseTrans`, and monthly stock in `sync.ProductTrans.StockInHand`. That document also says the engines only aggregate a rolling window, and that the earliest stored date cannot be known from code.

This phase did not re-query those tables. **Whether any tenant has enough history to train or validate a forecast is unknown / not verified.**

## 2. Integration layer

New module: `desktop/nextech-mediq/src/services/aiIntelligence.js`.

It calls only:

- `POST /api/procurement/shelf-sort/classify?tenant_id=`
- `GET /api/procurement/shelf-sort/categories`

Transport is the existing `apiGet` / `apiPost` in `src/api/client.js` (Bearer token already attached there). Tests inject a fake `post` / `get` and do not open a socket.

Interpretation rules:

- `llm_available === true`: suggestions are labelled **Model suggestion (unconfirmed)**. Confidence, freshness, and model name stay null unless those fields are actually on the JSON. The live route does not send them.
- `llm_available === false`: suggestions are discarded, including a contradictory payload. Outcome is `model_unavailable`. No keyword category is substituted.
- Missing `llm_available`, or a non-object body: nothing is treated as model output.
- Network or HTTP errors propagate. They are not turned into an empty "prediction".
- Empty names never call the endpoint.
- The layer does not call `POST /shelf-sort/categories` (human confirm), abnormal-sales flag writes, intelligence build, assignment, or export.

UI: `src/modules/ai-intelligence/AiIntelligencePage.jsx`, routed at `#/ai-intelligence` from `src/app/App.jsx`.

The page does not fetch on open. Vocabulary load and classify are separate buttons. Classify stays disabled until the operator acknowledges that the existing endpoint stores unconfirmed suggestions and does not change stock or submit an order.

`src/navigation/navConfig.js` was not edited. The sidebar entry can still read **Planned** because that file belongs to the auth/navigation worker. The route itself renders this page, and planned sidebar links are still navigable.

## 3. Eight-feature evaluation

Shared facts:

- **Historical sufficiency:** unknown / not verified. Tables described in section 1.3 were not counted in this session.
- **Validation metrics:** none. No holdout, MAPE, precision, or recall exists for these features in the code that was read.
- **Model:** none for all eight.
- **This centre's behaviour:** not called, not displayed, not replaced with a local calculation.

### 3.1 Sales demand forecasting

- **Required input:** dated sales quantity by product and store, plus a horizon. The decision engine instead reads a rolling window (`rolling_days`, often 90) and divides by that length.
- **Algorithm:** none. `average_daily_sales` in `decision_rules.py` is a calculation.
- **Fallback:** not applicable here. The order engines keep using their own rules. This screen does not stand in for them.
- **Deterministic vs model:** deterministic calculation, elsewhere. Not a prediction.
- **Confidence / freshness:** the classify API does not provide them, and no forecast API exists.
- **Forbid:** "AI forecast", "predicted demand", "expected sales next month".
- **Provenance:** no model. No forecast endpoint to attribute.

### 3.2 Stock-out risk prediction

- **Required input:** a stock time series and a demand path. `sync.Products.TotalStock` is a current snapshot. `ProductTrans.StockInHand` is monthly, and current readers take the latest month. Stock-out intervals (start and end) were not found.
- **Algorithm:** none. `stock_status` returns `OUT` when effective available is `<= 0`, and `LOW` when cover is under the low cut. `intelligence_service` counts stores where suggested qty `> 0` and stock `<= 0` at build time. That is a present-state count.
- **Fallback:** none in this centre.
- **Deterministic vs model:** deterministic label, not a risk probability.
- **Confidence / freshness:** not returned by any endpoint this centre calls.
- **Forbid:** "probability of stock-out", "days until stock-out" as a model output.
- **Provenance:** no model.

### 3.3 Excess stock identification

- **Required input:** current effective available and average daily sales, which the decision engine already has for a refresh. A true excess model would also need a policy for what "excess" means beyond the cover cap.
- **Algorithm:** none. `stock_status` returns `OVERSTOCK` when cover is above `stock_safe_cut` (default 15 days).
- **Fallback:** none in this centre.
- **Deterministic vs model:** deterministic threshold.
- **Confidence / freshness:** not applicable; not shown.
- **Forbid:** "AI identified dead stock" or "predicted excess".
- **Provenance:** no model. Non-moving reports are a separate current-state dwell calculation and are not wired here.

### 3.4 Expiry risk intelligence

- **Required input:** batch expiry dates and a consumption path. Expiry modules read supplier acknowledgement and settlement rows. That is event history of claims, not a probability that a batch will expire unsold.
- **Algorithm:** none found for expiry risk.
- **Fallback:** none in this centre.
- **Deterministic vs model:** existing expiry screens are settlement reports.
- **Confidence / freshness:** not returned.
- **Forbid:** "expiry risk score", "predicted wastage".
- **Provenance:** no model.

### 3.5 Supplier performance intelligence

- **Required input:** dated receipts, lead time, fill rate, quality or rejection events. GRN lines exist in code (`sync.PurchaseTrans`). Lead time and on-time rate were not found as a computed model. Supplier stock tables are overwritten snapshots, not a history (prior audit, not re-measured here).
- **Algorithm:** none. `suggestion_service` ranks suppliers with the fixed weights in section 1.2.
- **Fallback:** none in this centre. That ranker was not called, so its score is not displayed as intelligence.
- **Deterministic vs model:** deterministic weighted score, elsewhere.
- **Confidence / freshness:** the ranker stores a rounded score, not a confidence interval. Not shown here.
- **Forbid:** "supplier performance prediction", "reliability probability".
- **Provenance:** no model.

### 3.6 Purchase recommendation assistance

- **Required input:** the decision-engine inputs (window sales, stock, pending, in transit, reserved, min/max days, sale unit). Those stay inside procurement.
- **Algorithm:** none in this centre. `suggested_qty` is the business-rule output described in section 1.2. Network `consolidated_purchase_qty` subtracts warehouse stock from summed store suggestions. Both are calculations. Acting on them is a buyer action in Purchase Manager, not an automatic submission.
- **Fallback:** the pharmaceutical rules remain the authority. This screen does not replace or override them.
- **Deterministic vs model:** deterministic calculation, not called here.
- **Confidence / freshness:** mapping `confidence` on the intelligence grid is a match-edge score, not a quantity confidence. It is not shown here.
- **Forbid:** "AI recommended purchase order", "auto-generated order", any button that posts an order or writes a quantity.
- **Provenance:** no model. This client has no order-submit function.

### 3.7 Natural-language operational queries

- **Required input:** a question plus an authorised data scope.
- **Algorithm:** none. There is no text-to-SQL, chat, or tool-calling route. The only LLM prompt classifies product names into the shelf vocabulary.
- **Fallback:** if someone types a question into the classify box, it is sent as a product name only after they explicitly request classification. It is not answered as an operational query. With `llm_available` false, no category is filled in.
- **Deterministic vs model:** the shelf call is a model suggestion about category, not an answer about sales or stock.
- **Confidence / freshness:** not in the classify payload.
- **Forbid:** "ask MediQ about stock", "the assistant checked sales".
- **Provenance:** no query model. Shelf suggestions, when the flag is true, come from `POST /api/procurement/shelf-sort/classify`. The response does not name the model; source code names `claude-opus-4-8`.

### 3.8 Anomaly detection

- **Required input:** per-bill quantities for a product inside the 90-day window, excluding lines already marked do-not-consider, with at least two other bills.
- **Algorithm:** none. `abnormal_sales.classify_product` is the 5× / 3× ratio in section 1.2. No learned threshold.
- **Fallback:** if there are fewer than two other bills, the bill is not flagged. That is the rule, not a model degrade path.
- **Deterministic vs model:** deterministic ratio. The review endpoint can write a sales flag, so this centre does not call it.
- **Confidence / freshness:** the payload includes multipliers and `window_days`, not a model confidence. Not shown here.
- **Forbid:** "AI anomaly", "fraud detection", "unusual demand predicted".
- **Provenance:** no model.

## 4. What was implemented

| File | Role |
|---|---|
| `desktop/nextech-mediq/src/services/aiIntelligence.js` | Client for the two existing shelf routes, plus the eight-feature "not available" catalogue. |
| `desktop/nextech-mediq/src/modules/ai-intelligence/AiIntelligencePage.jsx` | Centre UI. Labels model suggestions as unconfirmed. States when confidence, freshness, and model name were not returned. |
| `desktop/nextech-mediq/src/modules/ai-intelligence/aiIntelligence.css` | Layout for that page only. |
| `desktop/nextech-mediq/tests/aiIntelligence.test.js` | Mocked classify and vocabulary tests, including `llm_available: false`. |
| `desktop/nextech-mediq/src/app/App.jsx` | `#/ai-intelligence` renders `AiIntelligencePage` instead of the planned placeholder. |

The UI copy uses **calculation** only in the boundary statement, to say this screen will not relabel procurement maths as a prediction. It does not render those calculations. Model output is labelled **Model suggestion (unconfirmed)** and only after `llm_available` is true.

## 5. Tests

Command, from `desktop/nextech-mediq`:

```text
npm test
```

which runs `node --test tests/*.test.js tests/*.test.mjs`.

Result on 2026-11-14: **40 passed, 0 failed** (13 of them are the new AI tests; the rest are the existing client tests and still pass).

Covered:

- eight features stay `implemented: false` and `model: null`
- `llm_available: true` keeps the suggestion and does not invent confidence, freshness, or a model name
- `llm_available: false` drops contradictory suggestions
- a body without `llm_available` is not model output
- confidence, freshness, and model name are copied only when present
- the POST URL is only `/api/procurement/shelf-sort/classify`
- a thrown network error is not replaced with a suggestion
- empty names do not call the endpoint
- a bad vocabulary payload does not invent categories

The live API was not called. A down host cannot be papered over by these tests, and the page shows the request error instead of a fabricated category.

## 6. Deliberately not built

- Sales forecast, stock-out probability, excess score, expiry risk, supplier-performance model, purchase recommendation, natural-language Q&A, and anomaly model.
- Any dashboard that shows ordinary procurement totals as AI.
- Local keyword classification presented as a fallback prediction. The server already applies those rules inside shelf sort. This screen does not pretend that path is the model.
- Automatic or manual purchase-order submission.
- Stock quantity edits, `DontConsiderInOrder` writes, category confirmation (`POST /shelf-sort/categories`), intelligence build, and refresh-build.
- New backend routes, schema changes, or a configured `ANTHROPIC_API_KEY`.
- A claim that `claude-opus-4-8` ran for a given request. The HTTP payload does not say so. Availability is only the server's `llm_available` boolean, and that boolean means "API key is set", not "the last call succeeded".
- Navigation status flip in `navConfig.js` (left to the worker editing navigation).
- Edits to the master tracker, auth, session, tenant, store, supplier-stock client, or quick-stock client.
