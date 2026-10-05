"""FILE_TRANSFER sync mode: package builder + transport adapters.

Additive to the existing DIRECT_HTTP sync path (store_agent/services/*). Used
by stores with internet-only connectivity (no LAN/domain route to HO): instead
of posting each chunk to HO in real time, a whole cycle's changed rows are
batched into one signed/checksummed ZIP package and handed to a Transport
adapter (file-drop folder, SFTP, or authenticated SMTP/IMAP email).

The sync "engine" itself -- table/column selection, row-hash diffing,
watermark tracking, chunking -- is NOT reimplemented here. It is the same
code DIRECT_HTTP uses (store_agent/services/data_extraction_service.py,
hash_generation_service.py, chunk_builder_service.py, sqlite_cache_service.py).
Only the "how do changed rows reach HO" step differs; see
store_agent/services/file_transfer_runtime_orchestrator.py.
"""
