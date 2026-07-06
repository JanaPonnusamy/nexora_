from modules.sync import shared_table_builder_repository as repo

_STRING_TYPES = ("char", "varchar", "nchar", "nvarchar", "binary", "varbinary")
_DECIMAL_TYPES = ("decimal", "numeric")
_NUMERIC_FAMILY = (
    "float", "real", "decimal", "numeric", "money", "smallmoney",
    "int", "bigint", "smallint", "tinyint",
)


def _column_type(data_type, max_length, precision, scale):
    dt = (data_type or "varchar").lower()

    if dt in _STRING_TYPES:
        if max_length is None:
            length = "255" if dt in ("char", "nchar") else "MAX"
        elif int(max_length) == -1:
            length = "MAX"
        else:
            length = str(int(max_length))
        return dt + "(" + length + ")"

    if dt in _DECIMAL_TYPES:
        # Exact precision/scale copied from the source catalog.
        p = int(precision) if precision is not None else 18
        if p > 38 or p < 1:
            p = 38
        s = int(scale) if scale is not None else 0
        if s > p:
            s = p
        return dt + "(" + str(p) + "," + str(s) + ")"

    # float/real/int/bigint/bit/date/datetime/... -> bare type name.
    return dt


def _desired(col):
    """Return (sql_type, base_type, precision, scale, nullable_clause)."""
    column_name, data_type, max_length, precision, scale, is_nullable, is_pk = col
    sql_type = _column_type(data_type, max_length, precision, scale)
    base = (data_type or "varchar").lower()
    nullable = "NULL" if (is_nullable and not is_pk) else "NOT NULL"
    p = None
    s = None
    if base in _DECIMAL_TYPES:
        p = int(precision) if precision is not None else 18
        if p > 38 or p < 1:
            p = 38
        s = int(scale) if scale is not None else 0
        if s > p:
            s = p
    return sql_type, base, p, s, nullable


def _column_def(col):
    column_name = col[0]
    sql_type, _, _, _, nullable = _desired(col)
    return "[" + column_name + "] " + sql_type + " " + nullable


def _needs_alter(col, physical):
    """True when the existing numeric column does not match the source type."""
    column_name = col[0]
    _, base, p, s, _ = _desired(col)
    current = physical.get(column_name.lower())
    if current is None or current["in_pk"]:
        return False
    if base not in _NUMERIC_FAMILY or current["type"] not in _NUMERIC_FAMILY:
        return False
    if current["type"] != base:
        return True
    if base in _DECIMAL_TYPES:
        return current["precision"] != p or current["scale"] != s
    return False


def build_shared_tables():
    results = []

    for sync_table_id, table_name in repo.get_active_tables():
        columns = repo.get_table_columns(sync_table_id)
        if not columns:
            results.append({"table": table_name, "status": "SKIPPED_NO_COLUMNS"})
            continue

        pk_cols = [c[0] for c in columns if c[6]]

        if not repo.table_exists(table_name):
            defs = [_column_def(c) for c in columns]
            if pk_cols:
                pk_list = ", ".join("[" + c + "]" for c in pk_cols)
                defs.append(
                    "CONSTRAINT [PK_sync_" + table_name + "] PRIMARY KEY ("
                    + pk_list + ")"
                )
            ddl = (
                "CREATE TABLE sync.[" + table_name + "] ("
                + ", ".join(defs) + ")"
            )
            repo.execute_ddl(ddl)
            results.append(
                {
                    "table": table_name,
                    "status": "CREATED",
                    "columns": len(columns),
                    "pk": pk_cols,
                }
            )
        else:
            physical = repo.get_physical_columns(table_name)
            added = 0
            altered = []
            for col in columns:
                if not repo.column_exists(table_name, col[0]):
                    repo.execute_ddl(
                        "ALTER TABLE sync.[" + table_name + "] ADD "
                        + _column_def(col)
                    )
                    added += 1
                elif _needs_alter(col, physical):
                    sql_type, _, _, _, nullable = _desired(col)
                    repo.execute_ddl(
                        "ALTER TABLE sync.[" + table_name + "] ALTER COLUMN ["
                        + col[0] + "] " + sql_type + " " + nullable
                    )
                    altered.append(
                        {
                            "column": col[0],
                            "from": physical[col[0].lower()]["type"],
                            "to": sql_type,
                        }
                    )
            results.append(
                {
                    "table": table_name,
                    "status": "EXISTS",
                    "columns_added": added,
                    "columns_altered": altered,
                }
            )

    return {
        "status": "SUCCESS",
        "tables_processed": len(results),
        "results": results,
    }
