"""Generate a one-time NMV device enrollment code from the HO box.

This is the CLI equivalent of the super-admin endpoint
    POST /api/nmv-integration/v1/admin/stores/{store_code}/enrollment
It exists so a code can be minted on the HO server without the SPA/HTTPS being
up yet. It calls the SAME implementation
(modules.nmv_integration.enrollment.generate_enrollment_code) -- there is no
second enrollment mechanism.

The plaintext code is printed to stdout ONCE. Only its SHA-256 hash is stored in
dbo.nmv_enrollment_code. Nothing writes the code to a log file; do not pipe this
output anywhere persistent.

Usage:
    python scripts/nmv_enrollment_code.py                       # store NMV, default TTL
    python scripts/nmv_enrollment_code.py --store-code NMV
    python scripts/nmv_enrollment_code.py --ttl-seconds 1800
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.nmv_integration import enrollment, repository


def main():
    parser = argparse.ArgumentParser(description="Mint a one-time NMV enrollment code.")
    parser.add_argument("--store-code", default="NMV")
    parser.add_argument("--ttl-seconds", type=int, default=None,
                        help=f"Code lifetime (default {enrollment.ENROLLMENT_TTL_SECONDS}s).")
    args = parser.parse_args()

    store = repository.resolve_platform_store(args.store_code)
    if not store:
        print(
            f"ERROR: store not found for code={args.store_code!r}. "
            "Verify dbo.stores has this store provisioned in NEXORA_PLATFORM.",
            file=sys.stderr,
        )
        return 2
    if not store.get("is_active", True):
        print(f"ERROR: store {store['store_code']} is inactive.", file=sys.stderr)
        return 2

    # created_by is left blank (CLI, no HO user session). Audit records 'cli'.
    result = enrollment.generate_enrollment_code(
        store, {"sub": None, "username": "cli"}, ttl_seconds=args.ttl_seconds
    )

    # Print the code ONCE. This is the only place the plaintext ever appears.
    print("")
    print("  NMV enrollment code (one-time, do NOT reuse or store):")
    print(f"    {result['enrollment_code']}")
    print("")
    print(f"  store_code         : {result['store_code']}")
    print(f"  store_id           : {result['store_id']}")
    print(f"  code_id            : {result['code_id']}")
    print(f"  expires_at (UTC)   : {result['expires_at']}")
    print(f"  expires_in_seconds : {result['expires_in_seconds']}")
    print("")
    print("  Paste it into NMV Settings and click Enroll device. It is valid for")
    print("  a single enrollment and only for this store.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
