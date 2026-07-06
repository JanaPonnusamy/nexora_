from config.database import get_connection


def get_active_tables():
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT sync_table_id, table_name
            FROM sync.sync_table_master
            WHERE is_active = 1
            ORDER BY sync_order
            """
        )
        return cur.fetchall()
    finally:
        conn.close()


def get_table_columns(sync_table_id):
    conn = get_connection()
    try:
        cur = conn.cursor()
        # The catalog is the discovered source-of-truth schema. Physical DDL
        # follows the catalog type (incl. exact numeric precision/scale); the
        # mapping data_type is only a fallback when no catalog row exists.
        cur.execute(
            """
            SELECT m.column_name,
                   COALESCE(c.data_type, m.data_type) AS data_type,
                   c.max_length,
                   c.precision_value, c.scale_value, c.is_nullable, m.is_pk
            FROM sync.sync_column_mapping m
            LEFT JOIN sync.sync_schema_catalog c
                ON c.table_name = m.table_name
               AND c.column_name = m.column_name
            WHERE m.sync_table_id = ?
              AND m.is_selected = 1
            ORDER BY m.column_order
            """,
            (sync_table_id,),
        )
        return cur.fetchall()
    finally:
        conn.close()


def get_physical_columns(table_name):
    """Current physical column types for sync.<table_name>."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT c.name, t.name, c.precision, c.scale,
                   (SELECT COUNT(*) FROM sys.index_columns ic
                    INNER JOIN sys.indexes ix
                        ON ix.object_id = ic.object_id
                       AND ix.index_id = ic.index_id
                    WHERE ic.object_id = c.object_id
                      AND ic.column_id = c.column_id
                      AND ix.is_primary_key = 1) AS in_pk
            FROM sys.columns c
            INNER JOIN sys.types t ON c.user_type_id = t.user_type_id
            WHERE c.object_id = OBJECT_ID(?)
            """,
            ("sync." + table_name,),
        )
        return {
            row[0].lower(): {
                "type": row[1].lower(),
                "precision": row[2],
                "scale": row[3],
                "in_pk": bool(row[4]),
            }
            for row in cur.fetchall()
        }
    finally:
        conn.close()


def execute_ddl(sql):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql)
        conn.commit()
    finally:
        conn.close()


def column_exists(table_name, column_name):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT COL_LENGTH(?, ?)",
            ("sync." + table_name, column_name),
        )
        return cur.fetchone()[0] is not None
    finally:
        conn.close()


def table_exists(table_name):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT OBJECT_ID(?, 'U')", ("sync." + table_name,))
        return cur.fetchone()[0] is not None
    finally:
        conn.close()
