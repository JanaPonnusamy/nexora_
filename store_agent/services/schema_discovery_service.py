
import json
from pathlib import Path
from typing import Any, Dict, List


class SchemaDiscoveryService:
    """
    SYNC-024A

    Real Store Database Schema Discovery

    Responsibilities:
        - Verify connected database
        - Discover tables
        - Discover columns
        - Discover primary keys
        - Discover foreign keys
        - Discover row counts
        - Generate schema snapshot

    No HO writes.
    No sync execution.
    """

    def __init__(self, connection):
        self.connection = connection

    def discover_schema(self) -> Dict[str, Any]:

        server_info = self._get_server_info()

        tables = self._get_tables()

        columns = {}
        primary_keys = {}

        for table in tables:
            table_name = table["table_name"]

            columns[table_name] = self._get_columns(table_name)

            primary_keys[table_name] = self._get_primary_keys(
                table_name
            )

        foreign_keys = self._get_foreign_keys()

        row_counts = self._get_row_counts()

        return {
            "server_name": server_info["server_name"],
            "database_name": server_info["database_name"],
            "table_count": len(tables),
            "tables": tables,
            "columns": columns,
            "primary_keys": primary_keys,
            "foreign_keys": foreign_keys,
            "row_counts": row_counts
        }

    def save_snapshot(
        self,
        snapshot: Dict[str, Any],
        output_path: str
    ) -> str:

        output_file = Path(output_path)

        output_file.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        with open(
            output_file,
            "w",
            encoding="utf-8"
        ) as fp:
            json.dump(
                snapshot,
                fp,
                indent=4
            )

        return str(output_file)

    def _get_server_info(self) -> Dict[str, str]:

        sql = """
        SELECT
            @@SERVERNAME AS server_name,
            DB_NAME() AS database_name
        """

        cursor = self.connection.cursor()

        cursor.execute(sql)

        row = cursor.fetchone()

        return {
            "server_name": row.server_name,
            "database_name": row.database_name
        }

    def _get_tables(self) -> List[Dict[str, str]]:

        sql = """
        SELECT
            TABLE_SCHEMA,
            TABLE_NAME
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_TYPE='BASE TABLE'
        ORDER BY TABLE_NAME
        """

        cursor = self.connection.cursor()

        cursor.execute(sql)

        rows = cursor.fetchall()

        return [
            {
                "schema_name": row.TABLE_SCHEMA,
                "table_name": row.TABLE_NAME
            }
            for row in rows
        ]

    def _get_columns(
        self,
        table_name: str
    ) -> List[Dict[str, Any]]:

        sql = """
        SELECT
            COLUMN_NAME,
            DATA_TYPE,
            CHARACTER_MAXIMUM_LENGTH,
            IS_NULLABLE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = ?
        ORDER BY ORDINAL_POSITION
        """

        cursor = self.connection.cursor()

        cursor.execute(sql, table_name)

        rows = cursor.fetchall()

        return [
            {
                "column_name": row.COLUMN_NAME,
                "data_type": row.DATA_TYPE,
                "max_length": row.CHARACTER_MAXIMUM_LENGTH,
                "is_nullable": row.IS_NULLABLE
            }
            for row in rows
        ]

    def _get_primary_keys(
        self,
        table_name: str
    ) -> List[str]:

        sql = """
        SELECT
            KU.COLUMN_NAME
        FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS TC
        INNER JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE KU
            ON TC.CONSTRAINT_NAME = KU.CONSTRAINT_NAME
        WHERE
            TC.CONSTRAINT_TYPE='PRIMARY KEY'
            AND KU.TABLE_NAME = ?
        ORDER BY KU.ORDINAL_POSITION
        """

        cursor = self.connection.cursor()

        cursor.execute(sql, table_name)

        rows = cursor.fetchall()

        return [
            row.COLUMN_NAME
            for row in rows
        ]

    def _get_foreign_keys(self):

        sql = """
        SELECT
            FK.TABLE_NAME AS child_table,
            CU.COLUMN_NAME AS child_column,
            PK.TABLE_NAME AS parent_table,
            PT.COLUMN_NAME AS parent_column
        FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS C
        INNER JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS FK
            ON C.CONSTRAINT_NAME = FK.CONSTRAINT_NAME
        INNER JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS PK
            ON C.UNIQUE_CONSTRAINT_NAME = PK.CONSTRAINT_NAME
        INNER JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE CU
            ON C.CONSTRAINT_NAME = CU.CONSTRAINT_NAME
        INNER JOIN
        (
            SELECT
                I1.TABLE_NAME,
                I2.COLUMN_NAME
            FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS I1
            INNER JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE I2
                ON I1.CONSTRAINT_NAME = I2.CONSTRAINT_NAME
            WHERE I1.CONSTRAINT_TYPE='PRIMARY KEY'
        ) PT
            ON PT.TABLE_NAME = PK.TABLE_NAME
        """

        cursor = self.connection.cursor()

        cursor.execute(sql)

        rows = cursor.fetchall()

        return [
            {
                "child_table": row.child_table,
                "child_column": row.child_column,
                "parent_table": row.parent_table,
                "parent_column": row.parent_column
            }
            for row in rows
        ]

    def _get_row_counts(self) -> Dict[str, int]:

        sql = """
        SELECT
            T.NAME AS table_name,
            SUM(P.ROWS) AS row_count
        FROM SYS.TABLES T
        INNER JOIN SYS.PARTITIONS P
            ON T.OBJECT_ID = P.OBJECT_ID
        WHERE P.INDEX_ID IN (0,1)
        GROUP BY T.NAME
        """

        cursor = self.connection.cursor()

        cursor.execute(sql)

        rows = cursor.fetchall()

        return {
            row.table_name: int(row.row_count)
            for row in rows
        }
