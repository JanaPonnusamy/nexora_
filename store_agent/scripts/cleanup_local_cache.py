"""One-time retroactive cleanup for an existing store_agent.db cache.

The sync orchestrators now prune sync_row_cache incrementally on every future
sync cycle (see prune_stale_row_hashes / prune_missing_row_hashes on
SqliteCacheService). That only stops NEW bloat -- it does nothing for rows
already sitting in a cache built before this fix shipped. This script trims
the existing backlog in one pass so a store doesn't have to wait out a full
window cycle to shrink back down.

Only touches ROLLING_WINDOW / custom_where tables (via last_sync_time
staleness), never plain UPSERT (full-scan) tables -- for those, "not synced
recently" does not mean "deleted at source", it can just mean "unchanged", so
an offline script with no source-DB connection cannot safely tell the two
apart. UPSERT-table cache entries are only ever pruned by the live
reconciliation in _diff_and_upload (which has the real source row set).

Usage:
    python cleanup_local_cache.py [path\\to\\store_agent.db]

If no path is given, resolves the same way SqliteCacheService does:
NEXORA_INSTALL_PATH\\cache\\store_agent.db, falling back to the dev-mode
config_cache path next to this repo.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from store_agent.services.maintenance_service import run_cache_maintenance


def _default_db_path():
    install_path = os.environ.get("NEXORA_INSTALL_PATH")
    if install_path:
        return Path(install_path) / "cache" / "store_agent.db"
    return Path(__file__).resolve().parent.parent / "config_cache" / "store_agent.db"


# Canonical trim logic now lives in maintenance_service (also run on a timer
# inside the agent). This script just invokes a one-off pass.
def cleanup(db_path, log_retention_days=30):
    return run_cache_maintenance(db_path, log_retention_days=log_retention_days)


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else _default_db_path()
    before = path.stat().st_size
    result = cleanup(path)
    after = path.stat().st_size
    print(f"DB: {path}")
    print(f"Size before: {before / 1024 / 1024:.2f} MB")
    print(f"Size after:  {after / 1024 / 1024:.2f} MB")
    for table, removed in result["row_cache_removed_by_table"].items():
        print(f"  sync_row_cache[{table}]: removed {removed}")
    print(f"  sync_execution_log: removed {result['sync_execution_log_removed']}")
    print(f"  sync_execution: removed {result['sync_execution_removed']}")
    print(f"  sync_ack: removed {result['sync_ack_removed']}")
