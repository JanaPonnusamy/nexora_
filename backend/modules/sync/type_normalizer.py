"""Centralized, schema-driven value normalization for the sync runtime.

The store agent transports rows as JSON, so datetimes arrive as ISO strings,
decimals as floats, binary as hex, etc. Before inserting into the typed
staging table we coerce each value to the Python type that pyodbc binds
correctly for the *target column's* SQL Server type. This is driven entirely
by the destination table schema -- no table or column names are hardcoded.
"""
import datetime
import decimal

_DATETIME_TYPES = {"datetime", "datetime2", "smalldatetime", "datetimeoffset"}
_DATE_TYPES = {"date"}
_TIME_TYPES = {"time"}
_BIT_TYPES = {"bit"}
_DECIMAL_TYPES = {"decimal", "numeric", "money", "smallmoney"}
_INT_TYPES = {"int", "bigint", "smallint", "tinyint"}
_FLOAT_TYPES = {"float", "real"}

_DT_FORMATS = (
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
)

# SQL Server 'datetime' (not datetime2) lower bound.
_SQL_DATETIME_MIN = datetime.datetime(1753, 1, 1)


def get_target_column_meta(cursor, schema_name, table_name):
    """Return {column_name: {type, precision, scale, max_length}}."""
    cursor.execute(
        """
        SELECT c.name, t.name, c.precision, c.scale, c.max_length
        FROM sys.columns c
        INNER JOIN sys.types t ON c.user_type_id = t.user_type_id
        WHERE c.object_id = OBJECT_ID(?)
        """,
        (schema_name + "." + table_name,),
    )
    return {
        row[0]: {
            "type": row[1].lower(),
            "precision": row[2],
            "scale": row[3],
            "max_length": row[4],
        }
        for row in cursor.fetchall()
    }


def get_target_column_types(cursor, schema_name, table_name):
    """Return {column_name: sql_type_lowercase} for a physical table."""
    return {
        name: meta["type"]
        for name, meta in get_target_column_meta(
            cursor, schema_name, table_name
        ).items()
    }


def cast_type(meta):
    """Render a CAST target type string from column metadata (diagnostics)."""
    sql_type = meta["type"]
    if sql_type in _DECIMAL_TYPES:
        p = meta["precision"] or 18
        s = meta["scale"] if meta["scale"] is not None else 0
        return sql_type + "(" + str(p) + "," + str(s) + ")"
    if sql_type in ("char", "varchar", "nchar", "nvarchar", "binary",
                    "varbinary"):
        length = meta["max_length"]
        if length is None or length == -1:
            return sql_type + "(MAX)"
        if sql_type in ("nchar", "nvarchar"):
            length = length // 2
        return sql_type + "(" + str(length) + ")"
    return sql_type


def _parse_datetime(value):
    text = value.strip()
    try:
        return datetime.datetime.fromisoformat(text)
    except ValueError:
        pass
    for fmt in _DT_FORMATS:
        try:
            return datetime.datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError("Unparseable datetime: " + repr(value))


def normalize_value(value, sql_type, scale=None):
    if value is None:
        return None

    sql_type = (sql_type or "").lower()

    # Treat empty/whitespace strings as NULL for any non-textual column.
    if isinstance(value, str) and not value.strip():
        if sql_type not in ("char", "varchar", "nchar", "nvarchar", "text",
                            "ntext"):
            return None

    if sql_type in _DATETIME_TYPES:
        dt = value if isinstance(value, datetime.datetime) else _parse_datetime(value)
        # Guard the narrow SQL Server 'datetime' range on 2014.
        if sql_type in ("datetime", "smalldatetime") and dt < _SQL_DATETIME_MIN:
            return None
        return dt

    if sql_type in _DATE_TYPES:
        if isinstance(value, datetime.date) and not isinstance(value, datetime.datetime):
            return value
        return _parse_datetime(value).date()

    if sql_type in _TIME_TYPES:
        if isinstance(value, datetime.time):
            return value
        text = str(value).strip()
        try:
            return datetime.time.fromisoformat(text)
        except ValueError:
            return _parse_datetime(text).time()

    if sql_type in _BIT_TYPES:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return int(value != 0)
        return 1 if str(value).strip().lower() in ("1", "true", "y", "yes") else 0

    if sql_type in _DECIMAL_TYPES:
        d = value if isinstance(value, decimal.Decimal) else decimal.Decimal(str(value))
        if scale is not None:
            # Quantize to the destination scale so float-string artifacts
            # (e.g. 0.30000000000000004) never trip "decimal loses precision".
            quantum = decimal.Decimal(1).scaleb(-int(scale))
            d = d.quantize(quantum, rounding=decimal.ROUND_HALF_UP)
        return d

    if sql_type in _INT_TYPES:
        if isinstance(value, bool):
            return int(value)
        return int(float(value)) if isinstance(value, str) else int(value)

    if sql_type in _FLOAT_TYPES:
        return float(value)

    # char/varchar/nvarchar/text/uniqueidentifier/etc.
    return value if isinstance(value, str) else str(value)


def _type_and_scale(column_meta, column):
    meta = column_meta.get(column)
    if isinstance(meta, dict):
        return meta.get("type"), meta.get("scale")
    return meta, None


def normalize_rows(rows, columns, column_meta):
    """Build executemany tuples in `columns` order with coerced values.

    `column_meta` may be {col: type} or {col: {type, scale, ...}}.
    """
    staged = []
    for row in rows:
        normalized = []
        for column in columns:
            sql_type, scale = _type_and_scale(column_meta, column)
            normalized.append(normalize_value(row.get(column), sql_type, scale))
        staged.append(tuple(normalized))
    return staged
