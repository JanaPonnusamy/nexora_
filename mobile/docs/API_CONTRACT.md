# API Contract — Phase 1

The mobile app consumes the **existing** FastAPI backend. No endpoint below was
invented; each maps to a real route. Nothing here modifies the backend.

> **Live-verified** against a running HO backend: `POST /api/auth/login` (valid →
> 200 + bearer token; bad creds → 401 `Invalid Username Or Password`),
> `GET /api/auth/me` (valid → 200; bad token → 401 `Invalid token`), and
> `GET /api/stores` (200, returns the store list). A platform user with no
> `tenant_id` (e.g. `superadmin`) resolves stores via `GET /api/stores`;
> `GET /api/stores/tenant/{id}` is the path for tenant-scoped users.

## Consumed in Phase 1

### `POST /api/auth/login` — public
Request:
```json
{ "username": "string", "password": "string" }
```
Response:
```json
{
  "token": "<jwt>",
  "token_type": "bearer",
  "user": {
    "user_id": "uuid",
    "username": "string",
    "first_name": "string|null",
    "is_platform_user": false,
    "is_active": true,
    "tenant_id": "uuid|null",
    "modules": [
      { "module": "...", "name": "...", "can_view": true, "can_create": false,
        "can_edit": false, "can_delete": false, "can_export": false }
    ],
    "roles": [
      { "role_id": "uuid", "role_name": "...", "store_id": "uuid",
        "store_code": "...", "store_name": "..." }
    ]
  }
}
```
The JWT is sent as `Authorization: Bearer <token>` on every authenticated call.

> Note: the `setupdeploy` account is rejected by this endpoint (403) — it is
> reserved for setup provisioning and is intentionally unsupported in the app.

### `GET /api/auth/me` — bearer
Returns the same `user` object; used on launch to validate a stored token and
restore the session. A `401` here tears the session down and returns to login.

### `GET /api/stores` — bearer
Full store list (used for **platform** users). Each item:
```json
{ "store_id": "uuid", "tenant_id": "uuid", "store_code": "...",
  "store_name": "...", "server_name": "...", "database_name": "...",
  "is_active": true }
```

### `GET /api/stores/tenant/{tenant_id}` — bearer
Slim, tenant-scoped list: `store_id`, `store_code`, `store_name`.

### `GET /health` — public
Connectivity probe (not yet surfaced in the UI; available for a "test
connection" affordance).

## Store selection source of truth

For a **store-scoped** user, the entitled stores are already present in the
login payload's `roles[]` (each carries `store_id/store_code/store_name`), so
store selection needs **no** extra request. `GET /api/stores*` is only used as a
fallback for platform users who have no store roles.

---

## Missing / not-yet-available endpoints (documented, NOT invented)

These are needed by later phases and are **not** assumed to exist. They must be
added server-side (or an existing route confirmed) before the corresponding
feature is built:

| Need | Status | Notes |
|------|--------|-------|
| Token refresh | **Missing** | No `/api/auth/refresh` exists. Tokens expire (default 720 min); the app currently requires re-login on expiry. |
| Logout / token revocation | **Missing** | Logout is client-side only (wipes the stored JWT). |
| Explicit "active store" persistence server-side | **Not required** | Store selection is a client concern; persisted locally in secure storage. |
| CRM endpoints | **Missing** | No backend routes exist yet. |
| Education endpoints | **Missing** | No backend routes exist yet. |
| Mobile-optimised dashboard summary | **Missing** | Phase 1 dashboard is a thin shell; a future aggregated endpoint would reduce round-trips. |

Existing endpoints that later phases will reuse (already in the backend, not
touched in Phase 1): `/api/stock-availability/*`, `/api/supplier-stock-analysis/*`,
`/api/procurement/*`, `/api/reports/*`, `/api/time-report/*`,
`/api/product-mapping/*`, and the `/api/sync/*` runtime routes.
