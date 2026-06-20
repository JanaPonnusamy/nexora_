"""
SYNC-024C
install_sync_024c_column_schema_discovery_generator.py
"""

from pathlib import Path
import textwrap

ROOT = Path(__file__).resolve().parent.parent

SERVICE_FILE = ROOT / "store_agent" / "services" / "column_schema_discovery_service.py"
RUNNER_FILE = ROOT / "store_agent" / "run_column_schema_discovery.py"

SERVICE_CODE = r'''
import json
import pyodbc
from pathlib import Path

class ColumnSchemaDiscoveryService:

    def __init__(self):
        self.base_path = Path(__file__).resolve().parent.parent
        self.schema_path = self.base_path / "schema"
        self.config_path = self.base_path / "config"

    def _load_agent_config(self):
        config_file = self.config_path / "agent_config.json"
        return json.loads(config_file.read_text(encoding="utf-8"))

    def discover(self):

        cfg = self._load_agent_config()

        conn = pyodbc.connect(
            "DRIVER={SQL Server};"
            f"SERVER={cfg['database_server']};"
            f"DATABASE={cfg['database_name']};"
            f"UID={cfg['database_username']};"
            f"PWD={cfg['database_password']};"
            "TrustServerCertificate=yes;"
        )

        sql = """
        SELECT
            c.TABLE_SCHEMA,
            c.TABLE_NAME,
            c.COLUMN_NAME,
            c.DATA_TYPE,
            c.CHARACTER_MAXIMUM_LENGTH,
            c.NUMERIC_PRECISION,
            c.NUMERIC_SCALE,
            c.IS_NULLABLE,
            c.ORDINAL_POSITION,
            CASE WHEN COLUMNPROPERTY(
                OBJECT_ID(c.TABLE_SCHEMA + '.' + c.TABLE_NAME),
                c.COLUMN_NAME,
                'IsIdentity'
            ) = 1 THEN 1 ELSE 0 END AS IS_IDENTITY,
            CASE WHEN pk.COLUMN_NAME IS NOT NULL THEN 1 ELSE 0 END AS IS_PRIMARY_KEY
        FROM INFORMATION_SCHEMA.COLUMNS c
        LEFT JOIN (
            SELECT
                KU.TABLE_SCHEMA,
                KU.TABLE_NAME,
                KU.COLUMN_NAME
            FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS TC
            INNER JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE KU
                ON TC.CONSTRAINT_NAME = KU.CONSTRAINT_NAME
            WHERE TC.CONSTRAINT_TYPE='PRIMARY KEY'
        ) pk
            ON c.TABLE_SCHEMA = pk.TABLE_SCHEMA
            AND c.TABLE_NAME = pk.TABLE_NAME
            AND c.COLUMN_NAME = pk.COLUMN_NAME
        ORDER BY
            c.TABLE_SCHEMA,
            c.TABLE_NAME,
            c.ORDINAL_POSITION
        """

        rows = []
        cur = conn.cursor()
        cur.execute(sql)

        for r in cur.fetchall():
            rows.append({
                "schema_name": r.TABLE_SCHEMA,
                "table_name": r.TABLE_NAME,
                "column_name": r.COLUMN_NAME,
                "data_type": r.DATA_TYPE,
                "max_length": r.CHARACTER_MAXIMUM_LENGTH,
                "precision_value": r.NUMERIC_PRECISION,
                "scale_value": r.NUMERIC_SCALE,
                "is_nullable": str(r.IS_NULLABLE).upper() == "YES",
                "is_identity": bool(r.IS_IDENTITY),
                "is_primary_key": bool(r.IS_PRIMARY_KEY),
                "ordinal_position": r.ORDINAL_POSITION
            })

        output_file = self.schema_path / "schema_column_snapshot.json"
        output_file.write_text(json.dumps(rows, indent=4), encoding="utf-8")

        conn.close()

        return {
            "column_count": len(rows),
            "output_file": str(output_file)
        }
'''

RUNNER_CODE = '''
from services.column_schema_discovery_service import ColumnSchemaDiscoveryService

def main():
    result = ColumnSchemaDiscoveryService().discover()
    print(result)

if __name__ == "__main__":
    main()
'''

def write_file(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(data).strip() + "\n", encoding="utf-8")

write_file(SERVICE_FILE, SERVICE_CODE)
write_file(RUNNER_FILE, RUNNER_CODE)

print("SYNC-024C installer completed")
