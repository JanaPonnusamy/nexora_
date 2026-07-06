"""Phase 028D - HO Schema Evolution Engine.

Before a merge, guarantee the shared target table exists in the `sync` schema
with: store_id + tenant_id context columns, the mapped business columns, a
row_hash column, and a STORE-SCOPED composite primary key
(store_id, <business pk cols>) so multiple stores share one physical table
without colliding. Only shared sync.* tables - never tenant schemas.
"""
import logging

from modules.sync.shared_table_builder_service import _column_type

logger = logging.getLogger(__name__)


def _norm(value):
    """Trim whitespace; tolerate None. Used for case/space-safe comparisons."""
    return (value or "").strip()


def _desired_columns(cursor, table_name):
    # Compare the master table name trimmed so trailing-space configuration
    # rows still resolve to the right table.
    cursor.execute(
        """
        SELECT m.column_name,
               COALESCE(c.data_type, m.data_type) AS data_type,
               c.max_length, c.precision_value, c.scale_value,
               c.is_nullable, m.is_pk
        FROM sync.sync_column_mapping m
        LEFT JOIN sync.sync_schema_catalog c
            ON c.table_name = m.table_name AND c.column_name = m.column_name
        INNER JOIN sync.sync_table_master t
            ON t.sync_table_id = m.sync_table_id
        WHERE LTRIM(RTRIM(t.table_name)) = ? AND m.is_selected = 1
        ORDER BY m.column_order
        """,
        (_norm(table_name),),
    )
    return cursor.fetchall()


def _col_def(col, force_nullable=False):
    """Build a column definition.

    During automatic schema evolution (force_nullable=True) the column is
    always emitted as NULL, even when the source metadata says NOT NULL - you
    cannot ADD a NOT NULL column to a populated table (SQL Server error 4901).
    The CREATE path leaves force_nullable=False because a brand-new table is
    empty, so NOT NULL on PK columns is safe there.
    """
    column_name, data_type, max_length, precision, scale, is_nullable, is_pk = col
    sql_type = _column_type(data_type, max_length, precision, scale)
    if force_nullable:
        nullable = "NULL"
    else:
        nullable = "NULL" if (is_nullable and not is_pk) else "NOT NULL"
    return "[" + _norm(column_name) + "] " + sql_type + " " + nullable


def _object_id(cursor, table_name):
    cursor.execute("SELECT OBJECT_ID(?, 'U')", ("sync." + _norm(table_name),))
    return cursor.fetchone()[0]


def _col_exists(cursor, table_name, column_name):
    """True only if the column physically exists in sync.<table_name>.

    Reads the SQL Server system catalog (sys.schemas/sys.tables/sys.columns)
    rather than COL_LENGTH(), and compares schema/table/column names trimmed
    and case-insensitively so an existing column is never misreported as
    missing because of casing or trailing spaces.
    """
    cursor.execute(
        """
        SELECT 1
        FROM sys.columns c
        INNER JOIN sys.tables  t ON t.object_id = c.object_id
        INNER JOIN sys.schemas s ON s.schema_id = t.schema_id
        WHERE UPPER(LTRIM(RTRIM(s.name))) = UPPER(?)
          AND UPPER(LTRIM(RTRIM(t.name))) = UPPER(?)
          AND UPPER(LTRIM(RTRIM(c.name))) = UPPER(?)
        """,
        ("sync", _norm(table_name), _norm(column_name)),
    )
    return cursor.fetchone() is not None


def ensure_table(cursor, table_name):
    """Idempotent. Returns 'CREATED' | 'REBUILT' | 'ALTERED' | 'OK'.
    Runs on the caller's cursor so it shares the merge transaction."""
    table_name = _norm(table_name)
    columns = _desired_columns(cursor, table_name)
    if not columns:
        return "NO_CONFIG"

    pk_cols = [_norm(c[0]) for c in columns if c[6]]
    exists = _object_id(cursor, table_name) is not None
    store_scoped = exists and _col_exists(cursor, table_name, "store_id")

    if not exists or not store_scoped:
        # Build (or rebuild legacy business-PK table) in store-scoped shape.
        defs = ["[store_id] uniqueidentifier NOT NULL",
                "[tenant_id] uniqueidentifier NULL"]
        defs += [_col_def(c) for c in columns]
        defs.append("[row_hash] varchar(64) NULL")
        if pk_cols:
            key = ", ".join("[" + c + "]" for c in (["store_id"] + pk_cols))
            defs.append(
                "CONSTRAINT [PK_sync_" + table_name + "] PRIMARY KEY (" + key + ")"
            )
        if exists:
            cursor.execute("DROP TABLE sync.[" + table_name + "]")
        cursor.execute(
            "CREATE TABLE sync.[" + table_name + "] (" + ", ".join(defs) + ")"
        )
        return "REBUILT" if exists else "CREATED"

    # Store-scoped table already present: add only genuinely missing columns,
    # always as NULL so a populated table can never trip error 4901.
    altered = False
    for col in columns:
        col_name = _norm(col[0])
        present = _col_exists(cursor, table_name, col_name)
        logger.debug(
            "SchemaEvolution Table=%s Column=%s Exists=%s %s",
            table_name, col_name, present, "Skipping" if present else "Adding",
        )
        if not present:
            cursor.execute(
                "ALTER TABLE sync.[" + table_name + "] ADD "
                + _col_def(col, force_nullable=True)
            )
            altered = True

    row_hash_present = _col_exists(cursor, table_name, "row_hash")
    logger.debug(
        "SchemaEvolution Table=%s Column=row_hash Exists=%s %s",
        table_name, row_hash_present, "Skipping" if row_hash_present else "Adding",
    )
    if not row_hash_present:
        cursor.execute(
            "ALTER TABLE sync.[" + table_name + "] ADD [row_hash] varchar(64) NULL"
        )
        altered = True

    return "ALTERED" if altered else "OK"
