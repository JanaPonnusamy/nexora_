# Phase 4 — Authentication and Tenant Integration

Date: 2026-11-14. App: `desktop/nextech-mediq` only. No backend route was added or changed. Electron stayed pinned at 22.3.27. No connection was made to `192.168.10.32`. Credentials, tokens, and `.env` values are not recorded in this file.

## Contracts used

All of these already exist. The renderer calls them over HTTP. It does not open SQL Server.

| Method and path | Request | Response used |
|---|---|---|
| `POST /api/auth/login` | `{username, password}` | `{token, token_type, user}` with `user.tenant_id`, `user.roles[]`, `user.modules[]`, `user.is_platform_user` |
| `POST /api/auth/logout` | Bearer token, empty JSON body | `{ok: true}` |
| `GET /api/tenants` | Bearer token | Active tenants the server is willing to show this caller |
| `GET /api/stores` | Bearer token | Active stores, already filtered to the caller's tenant unless the server grants a broader scope |
| `GET /api/stores/tenant/{tenant_id}` | Bearer token | Stores for one tenant, or 403 when the server rejects that tenant |
| `GET /api/stores/{store_id}` | Bearer token | One store |
| `GET /api/stock-availability/products/search` | Bearer token, `tenant_id`, `q`, `only_stock` | Existing Stock Enquiry call, kept working with the session from this phase |

`GET /api/auth/me` exists on the server and is not called. Role-admin routes (`/api/roles`, `/api/role-module-access`) are not called. Navigation uses the `roles` and `modules` already returned by login.

A 401 from the API uses these `detail` strings, and the client treats them as an ended session when the request had sent a bearer token: `Token expired`, `Invalid token`, `Not authenticated`, `Signed in on another system`. Login's own 401 (`Invalid Username Or Password`) does not clear a session, because that request has no bearer token. A 409 from login (`already signed in on another system`) is shown as the server's message.

## What was implemented

- Login against `POST /api/auth/login`. The token is written into the session store. The function returns the user object to the screen, not the token.
- Session persistence in `localStorage` under `nextechMediq.session` (separate from supplier-stock-client's key). The record holds the token, the user, a calendar `loginDate`, and the JWT `exp` as `expiresAt`.
- Session restoration on startup from that record. A stale calendar day or a past `exp` drops the record and shows a sign-in notice.
- A timer signs out shortly before `exp`. That sign-out calls logout, then clears the local record.
- Logout calls `POST /api/auth/logout` and always clears the local record, including when the server rejects the call. The logout call does not re-enter the 401 handler.
- Tenant and store selection in the existing top-bar tenant chip. Choices come from `GET /api/tenants` and `GET /api/stores`. A saved tenant that the directory does not return is replaced with the user's own tenant, or the first tenant the server returned. The user cannot type an id.
- The selected tenant is what Stock Enquiry, and the existing AI shelf-classification screen, send as `tenant_id`.
- Permission-aware navigation. Role gates follow the supplier-stock client for the screens this app has: stock viewer, label review, stock-plus-label, SMS purchase manager, salesman, purchase manager, and platform/super admin. An explicit `modules` list with `can_view` further hides Stock Enquiry when that grant is absent. Planned entries stay planned. The user menu hides Settings when that entry is hidden. A direct hash to a hidden route redirects to the first allowed enabled page.
- Unauthorized handling. A 401 on a request that sent a bearer token clears the local session and returns to the login screen with the server message. If that message contains the bearer token, the text shown is `Request failed`.
- API errors still surface FastAPI `detail` text, including validation lists. Transient GET retries are unchanged. POST is not retried.

## Security boundaries

- The token stays in renderer `localStorage`, which is where this app and supplier-stock-client already keep it. It is not sent to the Electron main process, not written into the window title, and not placed in error strings or this document. Main/preload IPC was not given a new channel for it.
- Hiding a nav entry is not authorization. `assert_tenant_access` and the server's role checks remain the authority. The client will not keep a tenant id that `GET /api/tenants` did not return, and it still sends only that id.
- JWT `exp` is read without verifying the signature. A tampered expiry still fails on the server as 401.
- Full-access logins (platform user / super admin) are minted without a session id. Logout still returns `{ok: true}`, but the JWT itself stays valid until `exp`. That is existing server behavior. The client drops its copy anyway. A later request with a copy of that bearer can still succeed until the token expires. This was observed live (see below).

## Test results

### Unit tests (mocked `fetch`, no live API)

Command, from `desktop/nextech-mediq`:

`npm test` — exit code **0**. **61 passed, 0 failed** (2026-11-14).

The new cases cover:

| Case | How | Result |
|---|---|---|
| Valid login | Mocked HTTP 200 with a fake JWT | Session stored. Caller receives the user and not the token. |
| Invalid login | Mocked HTTP 401 `Invalid Username Or Password` | No session. No unauthorized event. |
| Expired token | Stored JWT whose `exp` is in the past | `getSession()` returns null and the reason is `Token expired`. |
| Logout when the server returns 401 | One mocked call | Local session cleared. The call is not repeated. |
| Unauthorized request | Mocked HTTP 401 whose body echoes the bearer token | Session cleared. Shown message is `Request failed` and does not contain the token. |
| Tenant switching | Pure function | A store from the previous tenant is dropped. The first active store of the new tenant is selected. A tenant missing from the directory is replaced. |
| Store switching | Pure function | The selected store's tenant is kept with it. |
| Permission restrictions | Pure function | Stock viewer sees only stock entries. Purchase manager with a module list and no stock grant does not see Stock Enquiry or Administration. Salesman does not see purchase tools or sales reports. Platform user still sees Administration as planned, not enabled. |

### Production build

`npm run build` — exit code **0**. 82 modules. `dist/assets/index-DiE2Dv_p.js` 229.14 kB (gzip 73.39 kB). `dist/assets/index-DCfzlwdZ.css` 19.26 kB (gzip 3.87 kB).

The Electron window was not launched in this phase.

### Live API (2026-11-14)

Dev SQL `192.168.10.73:1433` accepted a TCP connection (4s budget). Port `1434` did not. `backend/.env` `DB_SERVER` is that dev host, not `192.168.10.32`. No secret from that file is recorded here.

`GET http://127.0.0.1:8000/openapi.json` — HTTP **200**.
`GET http://192.168.10.73:8000/openapi.json` — HTTP **200**. On 2026-11-13 that host did not answer. No credentials were sent to it. The app's default API URL is still `http://192.168.10.73:8000`.

Live calls used the existing dev account already configured for supplier-stock-client's dev auto-login. The password and the token are not written here. All of these were against `http://127.0.0.1:8000`.

| Case | HTTP status | Body note (no token, no payload) |
|---|---|---|
| Valid login `POST /api/auth/login` | **200** | A token field was present. User is a platform user with no `tenant_id`, 1 role, 26 modules. |
| Invalid password, same username | **401** | Detail class `invalid-credentials`. No token field. |
| `GET /api/tenants` with `Bearer not-a-token` | **401** | Detail class `invalid-token`. |
| `GET /api/tenants` with an HS256 JWT signed by the local dev secret and `exp` two minutes in the past | **401** | Detail class `token-expired`. |
| `GET /api/tenants` with the login token | **200** | 3 tenants. |
| `GET /api/stores` with the login token | **200** | 10 stores. |
| `GET /api/stores/tenant/{id}` for each of the 3 tenants | **200**, **200**, **200** | Store counts 6, 1, and 3. |
| `GET /api/stores/{id}` for the first two stores | **200**, **200** | Each body had a store name and the same tenant id as the list row. |
| `GET /api/stock-availability/products/search` with the first returned tenant and `q=para` | **200** | 6 store cards. No token field in the body. |
| `POST /api/auth/logout` | **200** | `{ok: true}`. |
| `GET /api/tenants` again with the same bearer after logout | **200** | 3 tenants. The platform-user JWT was not revoked. See security boundaries. |

## What remains unverified

- The login, tenant, and store controls were not clicked inside an Electron window in this phase. The live checks were HTTP calls, plus unit tests of the client logic.
- No non-platform account was signed in. Stock-viewer, purchase-manager, and salesman nav gates are unit-tested against mocked user objects. They were not confirmed by logging those accounts into the API.
- A cross-tenant stock request was not sent as a non-platform user, so this phase does not prove tenant isolation. The platform dev account was allowed to read all three tenants, which is what the server does for that role.
- `POST /api/auth/logout` does not invalidate this platform user's bearer token. Local sign-out is still required, and a copied token works until `exp`.
- Port 1434 on the dev SQL host is still closed. Port 1433 is open, and login no longer depends on 1434.
- Packaging, accessibility, and Windows 7/8 were not run.
