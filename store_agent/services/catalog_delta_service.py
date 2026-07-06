import hashlib

import requests


class CatalogDeltaService:
    """Phase 028C - Schema Discovery + Catalog Delta.

    Reads the store SQL Server schema, compares each column against the local
    SQLite catalog and uploads only changed/new entries to HO, which updates
    sync.sync_schema_catalog.
    """

    _DISCOVERY_SQL = """
        SELECT s.name, t.name, c.name, ty.name,
               c.max_length, c.precision, c.scale,
               c.is_nullable, c.is_identity,
               CASE WHEN pk.column_id IS NOT NULL THEN 1 ELSE 0 END,
               c.column_id
        FROM sys.tables t
        INNER JOIN sys.schemas s ON s.schema_id = t.schema_id
        INNER JOIN sys.columns c ON c.object_id = t.object_id
        INNER JOIN sys.types ty ON ty.user_type_id = c.user_type_id
        LEFT JOIN (
            SELECT ic.object_id, ic.column_id
            FROM sys.index_columns ic
            INNER JOIN sys.indexes i
                ON i.object_id = ic.object_id AND i.index_id = ic.index_id
            WHERE i.is_primary_key = 1
        ) pk ON pk.object_id = c.object_id AND pk.column_id = c.column_id
        WHERE t.is_ms_shipped = 0
        ORDER BY s.name, t.name, c.column_id
    """

    def __init__(self, connection, cache, ho_api_url, store_id):
        self.connection = connection
        self.cache = cache
        self.base = ho_api_url.rstrip("/")
        self.store_id = store_id

    @staticmethod
    def _hash(row):
        parts = [str(x) for x in row[3:10]]
        return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()

    def discover(self):
        cursor = self.connection.cursor()
        cursor.execute(self._DISCOVERY_SQL)
        return cursor.fetchall()

    def run(self):
        rows = self.discover()
        cached = self.cache.get_catalog_hashes()

        delta_payload = []
        catalog_entries = []
        for row in rows:
            schema_name, table_name, column_name = row[0], row[1], row[2]
            key = schema_name + "." + table_name + "." + column_name
            row_hash = self._hash(row)
            if cached.get(key) == row_hash:
                continue
            delta_payload.append({
                "schema_name": schema_name,
                "table_name": table_name,
                "column_name": column_name,
                "data_type": row[3],
                "max_length": row[4],
                "precision_value": row[5],
                "scale_value": row[6],
                "is_nullable": bool(row[7]),
                "is_identity": bool(row[8]),
                "is_primary_key": bool(row[9]),
                "ordinal_position": row[10],
                "first_discovered_store_id": self.store_id,
            })
            catalog_entries.append((
                schema_name, table_name, column_name, row[3], row[4],
                row[5], row[6], int(bool(row[7])), int(bool(row[8])),
                int(bool(row[9])), row_hash,
            ))

        if not delta_payload:
            return {"discovered": len(rows), "delta": 0, "uploaded": 0}

        response = requests.post(
            self.base + "/api/sync/schema/register",
            json=delta_payload,
            timeout=600,
        )
        response.raise_for_status()

        # Persist locally only after HO accepted the delta.
        self.cache.upsert_catalog(catalog_entries)
        return {"discovered": len(rows), "delta": len(delta_payload),
                "uploaded": len(delta_payload)}
