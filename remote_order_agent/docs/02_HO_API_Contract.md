# HO API contract for the NMV Sync Agent — v1 (DRAFT for HO to implement)

Base URL: `https://<ho-host>/api/nmv/v1` (TLS 1.2+, valid certificate). All bodies UTF-8 JSON. Times are ISO-8601 with offset (`2026-10-08T09:30:00+05:30`).

The agent is the only client. It is outbound-only; HO never connects to the store.

## Common request headers

| Header | Value |
|---|---|
| `Authorization` | `Bearer <device_token>` |
| `X-Nexora-Store-Id` | `4A2CEFF0-13C5-484C-B263-DE297E1E23E3` |
| `X-Nexora-Store-Code` | `NMV` |
| `X-Nexora-Timestamp` | Unix seconds. HO rejects skew greater than 300 s |
| `X-Nexora-Signature` | lowercase hex `HMAC_SHA256(device_secret, ts + "\n" + METHOD + "\n" + path_and_query + "\n" + sha256_hex(body))`. Use an empty body for GET |
| `X-Request-Id` | GUID per HTTP attempt (for logs) |
| `Idempotency-Key` | On every POST; identical on retries of the same logical request |

HO rejects any request where the token, store id and store code do not belong to the same enrolled device.

**Common response envelope:** `{"ok": true|false, "store_code": "NMV", "store_id": "...", "error": {"code": "...", "message": "...", "retryable": bool}?, ...}`. The agent rejects any response whose `store_code` or `store_id` differs from its own.

**Status codes:**

| Status | Meaning | Agent behaviour |
|---|---|---|
| 200 | Processed (check the body) | — |
| 400 / 422 | Invalid request | Not retried as-is |
| 401 / 403 | Authentication / authorisation | Long backoff |
| 409 | Conflict | — |
| 429 / 5xx / timeout | Transient | Retried with backoff |

## 1. Enrollment (one-time)
`POST /agent/register` (no Bearer token; the body carries the one-time code)
```json
{"store_code":"NMV","store_id":"4A2C…","enrollment_code":"<one-time, issued by HO admin>","machine_name":"DESKTOP-2","agent_version":"1.0.0"}
```
→ `{"ok":true,"store_code":"NMV","store_id":"…","device_id":"<guid>","device_token":"…","device_secret":"…"}`
The agent stores the token and secret with DPAPI. Re-enrolling revokes the previous device credentials.

## 2. Heartbeat
`POST /agent/heartbeat`
```json
{"device_id":"…","agent_version":"1.0.0","queue":{"pending":3,"rejected":0,"oldest_pending_at":"…"},
 "last_success":{"orders_pull":"…","results_push":"…","pos_master":"…","pos_incremental":"…"},
 "current_order_id":202610081200001}
```
→ `{"ok":true,"store_code":"NMV","store_id":"…","server_time":"…"}`

## 3. Order pull
`GET /orders/pending?limit=5`
Returns orders created by Nexora for NMV that have no APPLIED/REJECTED ack for their current version, oldest first.
```json
{"ok":true,"store_code":"NMV","store_id":"…","orders":[{
  "order_id": 202610081200001,
  "version": 1,
  "store_code": "NMV",
  "order_no": 1,
  "order_datetime": "2026-10-08T12:00:00+05:30",
  "min_days": 15, "max_days": 20,
  "last_sale_bill_no": "C12345",          // optional – agent computes from POS if null
  "last_bill_datetime": "…",               // optional
  "last_grn": 98765,                       // optional – agent computes from POS if null
  "line_count": 412,
  "lines_sha256": "<hex>",
  "lines": [{
     "product_code": 10234,               // int, = POS Products.ProductCode
     "product_name": "…",
     "total_stock": 4, "sale_unit": 10, "purchase_price": 12.5, "mrp": 18.0,
     "sub_location": "A1", "unit_description": "10 TAB",
     "last_received_date": "…", "last_sale_date": "…", "transaction_date": "…",
     "sls_qty": 120, "max_sale_qty": 10,
     "wanted_date": "…",                  // optional, defaults to order_datetime
     "wanted_type": "Regular Order Based Min & Max",
     "status": 0,                         // 0 = open, 2 = excluded (e.g. Additional Row)
     "order_qty": 3,                      // int, in packs (OrderQty)
     "org_order_qty": 3,                  // optional, defaults to order_qty
     "product_type": 1,                   // 0 = Non Pharma, 1 = Pharma
     "product_type_name": "Pharma",       // must be 'Pharma' or 'Non Pharma'
     "min_qty": 20, "max_qty": 30, "frequence": 7,
     "remarks": null
  }]
}]}
```

**Rules the agent enforces:**
- `order_id` is a bigint that is globally unique and never reused. It must not collide with legacy VB ids (`yyyyMMddmmss`, 12 digits). Recommendation: 15 digits.
- `product_code` is unique within an order.
- `status` must be 0 or 2.
- `order_qty` and `org_order_qty` must be integers ≥ 0.
- `lines.length == line_count`.

**`lines_sha256`:**
- Lines are sorted by `product_code` ascending.
- Each line is canonicalised as `product_code|order_qty|org_order_qty|status|product_type`, all as base-10 integers with no padding.
- The canonical lines are joined with `\n` (no trailing newline).
- The hash is SHA-256 of the UTF-8 bytes of that string, as lowercase hex.

**Amendments:** send the same `order_id` with a higher `version`. The agent applies an amendment only if no user change has been captured for that order. Otherwise it acks `REJECTED` with reason `USER_EDITS_EXIST`.

### Order acknowledgement
`POST /orders/{order_id}/ack`, with `Idempotency-Key: ack-{order_id}-{version}-{state}`
```json
{"order_id":202610081200001,"version":1,"state":"APPLIED|REJECTED|DEFERRED",
 "payload_sha256":"<hex as computed by agent>","applied_line_count":412,
 "reason_code":null,"reason":null,"applied_at":"…"}
```
→ `{"ok":true,"store_code":"NMV","store_id":"…","order_id":…,"version":…,"state":"APPLIED"}`. The echoed values must match the request.

`DEFERRED` means a valid order is waiting because the previous order is still being edited. HO keeps returning it from `/orders/pending`.

**Reason codes:**

| Code | Meaning |
|---|---|
| `HASH_MISMATCH` | Line hash did not match `lines_sha256` |
| `COUNT_MISMATCH` | Line count did not match `line_count` |
| `WRONG_STORE` | Order is not for NMV |
| `INVALID_LINE` | A line failed validation |
| `DUPLICATE_PRODUCT` | Same `product_code` twice in one order |
| `ID_CONFLICT` | `order_id` already exists locally with a different payload |
| `USER_EDITS_EXIST` | Amendment refused because the order already has user edits |
| `UNKNOWN_PRODUCTS` | Lines reference products not found locally (only when strict mode is configured) |

## 4. Order result push
`POST /order-results`, with `Idempotency-Key: <batch_id>`
```json
{"batch_id":"<guid, reused on retry of the same set>","queue_epoch":"<guid>","count":2,
 "items_sha256":"<sha256 of the change_ids joined by ',' ascending>",
 "items":[{
   "change_id": 1051,                       // HO dedup key = (store_id, queue_epoch, change_id)
   "operation": "U",                        // I | U | D
   "captured_at": "2026-10-08T12:31:04.120+05:30",
   "order_id": 202610081200001, "product_code": 10234,
   "before": {"order_qty":3,"or_qty":null,"qtycheck":0,"remarks":null,"or_supplier":null,"or_supplier_code":null,"status":"0"},
   "after":  {"order_qty":5,"or_qty":null,"qtycheck":1,"remarks":"OrderQty Changed 2 Add","or_supplier":null,"or_supplier_code":null,"status":"0"},
   "db_login":"sa","host_name":"DESKTOP-2","app_name":".Net SqlClient Data Provider"
 }]}
```
→
```json
{"ok":true,"store_code":"NMV","store_id":"…","batch_id":"…","items_sha256":"…",
 "accepted":[1051],"duplicates":[1050],
 "rejected":[{"change_id":1052,"code":"UNKNOWN_ORDER","message":"…","retryable":true}]}
```

**Rules:**
- Every sent `change_id` must appear in exactly one of `accepted`, `duplicates` or `rejected`.
- `batch_id` and `items_sha256` must be echoed.
- Otherwise the agent treats the whole batch as failed and retries it.
- HO must apply items per order in ascending `change_id` order.

## 5. Recommended HO-side storage (informative)
- `nmv_order_result(store_id, queue_epoch, change_id PK, …)` as an append-only ledger.
- A materialised "current state" table per `(order_id, product_code)`, updated in `change_id` order.
