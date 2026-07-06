"""Validation for the multi-store cache-collision fix.

Cache identity must be (store_id, table_name, source_pk). Before the fix two
stores sharing the runtime DB collided on (table_name, source_pk): the second
store's rows were seen as "already synced" and skipped.
"""
import sqlite3

import pytest

from store_agent.services.sqlite_cache_service import SqliteCacheService

NMA = "NMA-STORE-ID"
NMC = "NMC-STORE-ID"
TABLE = "Products"


def _cache(tmp_path, store_id):
    return SqliteCacheService(db_path=tmp_path / "store_agent.db", store_id=store_id)


def test_first_sync_of_second_store_is_not_skipped(tmp_path):
    """The exact reported bug: NMA syncs first, NMC's first-ever sync must NOT
    inherit NMA's cached hashes."""
    nma = _cache(tmp_path, NMA)
    # NMA fully syncs Products (ProductCode 1..3).
    nma.upsert_row_hashes(TABLE, [("1", "h1"), ("2", "h2"), ("3", "h3")])

    # NMC opens the SAME shared runtime DB and looks up its own cache.
    nmc = _cache(tmp_path, NMC)
    cached = nmc.get_row_hashes(TABLE)

    # NMC must see an EMPTY cache -> examined == uploaded, skipped == 0.
    assert cached == {}, "NMC inherited NMA's cache -> rows would be wrongly skipped"


def test_each_store_keeps_independent_hashes(tmp_path):
    nma = _cache(tmp_path, NMA)
    nmc = _cache(tmp_path, NMC)
    nma.upsert_row_hashes(TABLE, [("2", "hash-from-NMA")])
    nmc.upsert_row_hashes(TABLE, [("2", "hash-from-NMC")])

    assert nma.get_row_hashes(TABLE) == {"2": "hash-from-NMA"}
    assert nmc.get_row_hashes(TABLE) == {"2": "hash-from-NMC"}
    assert nma.row_cache_count(TABLE) == 1
    assert nmc.row_cache_count(TABLE) == 1


def test_subsequent_sync_uploads_only_changed(tmp_path):
    nmc = _cache(tmp_path, NMC)
    nmc.upsert_row_hashes(TABLE, [("1", "h1"), ("2", "h2"), ("3", "h3")])

    # Re-sync: row 2 changed, rows 1 and 3 unchanged.
    cached = nmc.get_row_hashes(TABLE)
    incoming = {"1": "h1", "2": "h2-CHANGED", "3": "h3"}
    changed = [(pk, h) for pk, h in incoming.items() if cached.get(pk) != h]

    assert changed == [("2", "h2-CHANGED")]


def test_watermark_state_is_store_scoped(tmp_path):
    nma = _cache(tmp_path, NMA)
    nmc = _cache(tmp_path, NMC)
    nma.set_last_watermark(TABLE, "2026-06-01")
    nmc.set_last_watermark(TABLE, "2026-06-23")

    assert nma.get_last_watermark(TABLE) == "2026-06-01"
    assert nmc.get_last_watermark(TABLE) == "2026-06-23"


def test_delete_is_store_scoped(tmp_path):
    nma = _cache(tmp_path, NMA)
    nmc = _cache(tmp_path, NMC)
    nma.upsert_row_hashes(TABLE, [("2", "hA")])
    nmc.upsert_row_hashes(TABLE, [("2", "hC")])

    nma.delete_row_hashes(TABLE, ["2"])

    assert nma.get_row_hashes(TABLE) == {}
    assert nmc.get_row_hashes(TABLE) == {"2": "hC"}  # NMC untouched


def test_legacy_schema_is_migrated_automatically(tmp_path):
    """A pre-fix DB (store-unaware PK) must auto-migrate to the store-aware
    schema on first open, without crashing."""
    db_path = tmp_path / "store_agent.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE sync_row_cache (
            table_name TEXT NOT NULL,
            source_pk TEXT NOT NULL,
            row_hash TEXT NOT NULL,
            last_sync_time TEXT,
            PRIMARY KEY (table_name, source_pk)
        );
        CREATE TABLE sync_table_state (
            table_name TEXT PRIMARY KEY,
            last_full_sync TEXT,
            last_incremental_sync TEXT,
            last_watermark TEXT
        );
        """
    )
    conn.execute(
        "INSERT INTO sync_row_cache VALUES ('Products','2','contaminated','x')"
    )
    conn.commit()
    conn.close()

    # Opening the cache must migrate the legacy schema.
    nmc = SqliteCacheService(db_path=db_path, store_id=NMC)

    # New store_id column present, and contaminated legacy rows are gone.
    cols = {r[1] for r in sqlite3.connect(db_path).execute(
        "PRAGMA table_info(sync_row_cache)"
    ).fetchall()}
    assert "store_id" in cols
    assert nmc.get_row_hashes("Products") == {}

    # And the migrated cache is fully functional.
    nmc.upsert_row_hashes("Products", [("2", "fresh")])
    assert nmc.get_row_hashes("Products") == {"2": "fresh"}


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
