"""Device identity: per-device keypair registration + signature-based auth.

A store agent / desktop client generates an Ed25519 keypair at registration
(private key sealed with OS DPAPI on the device), registers the PUBLIC key +
machine fingerprint here, and thereafter obtains short-lived access tokens by
SIGNING a challenge with its private key. No password/secret is ever shipped in
the app, and a device is revocable from HO. Stores are assigned to a device
from HO (device_store_assignments), so one agent can serve N stores.
"""
