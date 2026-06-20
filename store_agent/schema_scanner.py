from store_agent.database import get_connection

class SchemaScanner:

    def get_identity_columns(self):

        conn = get_connection()
        cur = conn.cursor()

        rows = cur.execute("""
        SELECT
            s.name AS schema_name,
            t.name AS table_name,
            c.name AS column_name
        FROM sys.columns c
        INNER JOIN sys.tables t
            ON c.object_id = t.object_id
        INNER JOIN sys.schemas s
            ON t.schema_id = s.schema_id
        WHERE c.is_identity = 1
        ORDER BY s.name,t.name,c.column_id
        """).fetchall()

        conn.close()

        return rows
