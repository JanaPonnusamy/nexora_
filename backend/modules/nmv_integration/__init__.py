"""NMV Store Integration (HO side).

An HTTPS pull/push boundary between Nexora HO / OrderNMC and the remote NMV
store, whose VB.NET OrderManagement app runs against an NMV-local SQL database
HO must never reach directly over the Internet.

See CONTRACT.md for the dependency matrix, sync contract, API contract,
migration plan, security model and failure/retry model.

This module is additive and isolated: it adds endpoints + three additive
OrderNMC tables and does not modify the Legacy Order workflow or the existing
five LAN stores (NMA/NMW/NMC/NMG/NMS).
"""
