"""HO-side implementation of the Remote Order Agent contract (/api/nmv/v1).

This is the server end of the standalone C# agent vendored at repo-root
``remote_order_agent/`` (formerly "NMVSyncAgent"). The agent is outbound-only:
it pulls generated orders from HO, applies them into the remote store's local
OrderNMC, and pushes back the store's order edits.

Contract: ``remote_order_agent/docs/02_HO_API_Contract.md``. It is deliberately
a SEPARATE surface from ``modules.nmv_integration`` (which speaks the Ed25519
``/api/nmv-integration/v1`` dialect): this one uses an opaque device token plus
HMAC-SHA256 request signing, exactly as the shipped-and-tested agent expects.
The order data layer (OrderNMC reads, result apply, one-time enrollment codes)
is reused from ``modules.nmv_integration`` so there is one source of truth for
the actual order rows.
"""
