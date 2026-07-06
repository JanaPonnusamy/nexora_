
import sqlite3
from store_agent.catalog.catalog_models import CATALOG_DB_PATH

class MetadataRuntimeReader:

    def get_tables(self):

        conn = sqlite3.connect(CATALOG_DB_PATH)
        conn.row_factory = sqlite3.Row

        try:
            rows = conn.execute(
                "SELECT * FROM sync_table_catalog WHERE is_active=1 ORDER BY sync_order"
            ).fetchall()

            return [dict(x) for x in rows]

        finally:
            conn.close()

    def get_columns(self, table_name):

        conn = sqlite3.connect(CATALOG_DB_PATH)
        conn.row_factory = sqlite3.Row

        try:
            rows = conn.execute(
                "SELECT * FROM sync_column_catalog WHERE table_name=? ORDER BY column_order",
                (table_name,)
            ).fetchall()

            return [dict(x) for x in rows]

        finally:
            conn.close()
