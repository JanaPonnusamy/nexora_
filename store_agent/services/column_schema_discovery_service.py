
import json
from pathlib import Path

class ColumnSchemaDiscoveryService:

    def __init__(self, connection):
        self.connection = connection
        self.schema_path = Path(__file__).resolve().parent.parent / "schema"

    def discover(self):
        sql = """
        SELECT c.TABLE_SCHEMA,c.TABLE_NAME,c.COLUMN_NAME,c.DATA_TYPE,
               c.CHARACTER_MAXIMUM_LENGTH,c.NUMERIC_PRECISION,
               c.NUMERIC_SCALE,c.IS_NULLABLE,c.ORDINAL_POSITION,
               CASE WHEN COLUMNPROPERTY(OBJECT_ID(c.TABLE_SCHEMA + '.' + c.TABLE_NAME),
               c.COLUMN_NAME,'IsIdentity') = 1 THEN 1 ELSE 0 END AS IS_IDENTITY,
               CASE WHEN pk.COLUMN_NAME IS NOT NULL THEN 1 ELSE 0 END AS IS_PRIMARY_KEY
        FROM INFORMATION_SCHEMA.COLUMNS c
        LEFT JOIN (
            SELECT KU.TABLE_SCHEMA,KU.TABLE_NAME,KU.COLUMN_NAME
            FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS TC
            INNER JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE KU
            ON TC.CONSTRAINT_NAME = KU.CONSTRAINT_NAME
            WHERE TC.CONSTRAINT_TYPE='PRIMARY KEY'
        ) pk
        ON c.TABLE_SCHEMA=pk.TABLE_SCHEMA
        AND c.TABLE_NAME=pk.TABLE_NAME
        AND c.COLUMN_NAME=pk.COLUMN_NAME
        ORDER BY c.TABLE_SCHEMA,c.TABLE_NAME,c.ORDINAL_POSITION
        """

        cur = self.connection.cursor()
        cur.execute(sql)

        rows = []
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

        return {"column_count": len(rows), "output_file": str(output_file)}
