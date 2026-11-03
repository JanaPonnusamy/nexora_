"""OrderNMC mirror: one-way HO OrderNMC -> remote-PC OrderNMC replication.

A remote PC on the Internet (reachable only by its own outbound calls) keeps a
local OrderNMC copy for the legacy VB tools. The store agent on that PC pulls
from HO and upserts locally; HO is the source of truth for every row it has,
and rows that exist only on the remote side are never touched or deleted.

Change detection is HO-side and needs no schema change on the legacy tables:
each source table is paged by its primary key, every row is hashed in SQL, and
the hash is compared with a per-target ledger of what that target has already
acknowledged. Only new/changed rows travel. Tables untouched since the last
completed pass (sys.dm_db_index_usage_stats) are skipped without a scan.

The ledger/state tables live in the SOURCE OrderNMC under the additive
``nexora_mirror`` schema (same instance -> the hash/ledger join stays local).
Target assignments + the remote SQL credentials live in NEXORA_PLATFORM
(``dbo.ordernmc_mirror_targets``), Fernet-encrypted with the same key as store
DB passwords, so a credential change needs no visit to the remote PC.
"""
