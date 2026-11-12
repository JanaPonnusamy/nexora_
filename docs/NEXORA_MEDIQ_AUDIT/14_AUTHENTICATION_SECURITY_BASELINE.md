# 14 — Authentication & Security Baseline
**NEXORA MEDIQ — Phase 1 Baseline Stabilization**

Re-verification (not a re-citation of Phase 0) of the tenant/store authorization model, with concrete implementation-level evidence.

## Server-side authorization is genuinely server-side — VERIFIED

- `backend/dependencies/auth.py:92-95` — `has_full_access(user)` reads `user.get("is_platform_user")` and `user.get("role_names", [])`. Both fields come from the decoded JWT (`decode_access_token`), **never from a client-supplied request field.** This was independently confirmed by reading the function body, not inferred from naming. A malicious or buggy client cannot claim full access by sending an extra field — the check only trusts the token's own claims.
- `backend/dependencies/store_scope.py:86-91` — `assert_tenant_access(user, tenant_id)`: unrestricted-scope users pass through; otherwise it compares the JWT's `tenant_id` claim against the requested `tenant_id` query parameter and raises `403` on mismatch. **VERIFIED.**
- `backend/modules/procurement/access.py:97-102` — `require_procurement_workspace` implements a least-privilege "any genuine procurement module grant qualifies" check via `_require(current_user, grants_procurement_workspace)`. In-code documentation confirms it was written to match the existing live UI's own gating. Every `pm_router.py` handler sampled (across both Phase 0 and this phase's deeper read of the export-defaults endpoints) consistently uses this `require_procurement_workspace` + `assert_tenant_access` pairing.

**Conclusion: the pattern holds up under closer inspection, not just at the surface level.** There is no code path found where the renderer can self-assert elevated access and have the backend believe it.

## auth_controller.py diff — confirmed minimal

The only change present is the single-line `_MULTI_SESSION_ROLES` addition documented in `11`/`12`. No other authentication or session logic in the file was touched. This is not a security-relevant change beyond allowing one additional role to hold concurrent sessions — a convenience/business decision, not a weakening of the access-control model.

## Electron security posture — unchanged, re-confirmed at exact lines

`main.cjs`:
- `contextIsolation: true` (line 242)
- `nodeIntegration: false` (line 243)
- `sandbox: false` (line 244)
- `webviewTag: true` (line 247) — scoped only to the Procurement Web Panel's isolated, no-preload, no-Node, sandboxed, HTTP(S)-only `<webview>` instances (confirmed in Phase 0, re-cited here, not re-verified line-by-line again this pass since nothing in the diff touches this file).

No change to this file is present in the current working tree.

## Device enrollment — scope clarified

`enrollmentGuard.cjs` (11 lines) is **not itself a security boundary.** It is a pure decision function that returns `{action: 'skip' | 'register', ...}` based on whether the user is signed in and whether the device's local enrollment marker has changed. It exists purely to avoid redundant HO enrollment calls — the actual enrollment HTTP/filesystem work happens in the main process based on this function's answer, and that work's own authorization is enforced by the backend endpoint it calls, not by this guard. This clarifies (rather than contradicts) Phase 0's finding — the security boundary for device enrollment is still backend-side, as expected.

## Verdict

**No weakening of the existing tenant/store security model was found, and none is proposed.** All checks validated in Phase 0 hold up under this phase's deeper, implementation-level re-verification. The one uncommitted auth-adjacent change (`SMS_PM` role addition) is minimal, isolated, and does not alter the enforcement pattern itself. Recommendation for Phase 2+: continue requiring every new backend endpoint (including any future AI Intelligence Centre endpoints) to use the same `require_*` + `assert_tenant_access` + (where relevant) `has_full_access` pattern documented here — this is now confirmed as the project's real, working convention, not just its stated intent.
