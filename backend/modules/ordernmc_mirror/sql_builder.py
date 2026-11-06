"""Pure SQL text builders for the OrderNMC mirror (no I/O; unit-testable).

Column metadata dicts look like::

    {"name": "ProductCode", "type": "int", "max_length": 4, "precision": 10,
     "scale": 0, "nullable": False, "identity": False}

``type`` is the SYSTEM type name (TYPE_NAME(system_type_id)), so alias types
collapse to their base type.
"""
from __future__ import annotations

LEDGER = "[nexora_mirror].[ledger]"

# Types that cannot be hashed/compared/transported generically -- skipped.
UNSUPPORTED_TYPES = {
    "timestamp", "text", "ntext", "image", "xml", "sql_variant",
    "geography", "geometry", "hierarchyid",
}
_DATE_TYPES = {"datetime", "datetime2", "smalldatetime", "date", "time", "datetimeoffset"}
_FLOAT_TYPES = {"float", "real"}
_MONEY_TYPES = {"money", "smallmoney"}
_CHAR_TYPES = {"char", "varchar", "nchar", "nvarchar"}
_BINARY_TYPES = {"binary", "varbinary"}

# HASHBYTES on SQL Server 2014 accepts at most 8000 bytes (= 4000 nvarchar
# chars), so a wide row is hashed in chunks and the chunk digests re-hashed.
_CHUNK_CHARS = 3800
_NULL = "NCHAR(9216)"   # visible NULL marker so NULL <> ''
_SEP = "NCHAR(31)"


def q(name: str) -> str:
    """Bracket-quote an identifier (']' doubled)."""
    return "[" + str(name).replace("]", "]]") + "]"


def sql_type(col: dict) -> str:
    """Column type as DDL text, e.g. nvarchar(100), decimal(18,2), varchar(max)."""
    t = col["type"]
    ml = col.get("max_length")
    if t in ("varchar", "char", "varbinary", "binary"):
        return f"{t}(max)" if ml == -1 else f"{t}({ml})"
    if t in ("nvarchar", "nchar"):
        return f"{t}(max)" if ml == -1 else f"{t}({ml // 2})"
    if t in ("decimal", "numeric"):
        return f"{t}({col.get('precision')},{col.get('scale')})"
    if t in ("datetime2", "time", "datetimeoffset"):
        return f"{t}({col.get('scale')})"
    return t


def _char_len(col: dict) -> int:
    """Upper bound of the nvarchar length of a column's hash text."""
    t, ml = col["type"], col.get("max_length") or 0
    if t in ("nvarchar", "nchar"):
        return 3520 if ml == -1 else ml // 2
    if t in ("varchar", "char"):
        return 3520 if ml == -1 or ml > 3500 else ml
    if t in _BINARY_TYPES:
        return 3520 if ml == -1 or ml > 1750 else 2 * ml + 2
    return 40


def text_expr(col: dict, alias: str = "t") -> str:
    """Deterministic nvarchar rendering of one column for hashing."""
    c = f"{alias}.{q(col['name'])}"
    t, ml = col["type"], col.get("max_length") or 0
    if t in _DATE_TYPES:
        e = f"CONVERT(nvarchar(40), {c}, 126)"
    elif t in _FLOAT_TYPES or t in _MONEY_TYPES:
        e = f"CONVERT(nvarchar(40), {c}, 2)"
    elif t in _BINARY_TYPES:
        if ml == -1 or ml > 1750:
            e = (f"CONVERT(nvarchar(3500), SUBSTRING({c}, 1, 1740), 2) + N'#' + "
                 f"CAST(DATALENGTH({c}) AS nvarchar(20))")
        else:
            e = f"CONVERT(nvarchar(3502), {c}, 1)"
    elif t in _CHAR_TYPES and (ml == -1 or (t in ("varchar", "char") and ml > 3500)):
        # Long text: leading slice + length (a change past 3500 chars that keeps
        # the length is missed -- acceptable for OrderNMC, which has none).
        e = (f"CAST(LEFT({c}, 3500) AS nvarchar(3500)) + N'#' + "
             f"CAST(DATALENGTH({c}) AS nvarchar(20))")
    else:
        e = f"CAST({c} AS nvarchar(4000))"
    return f"ISNULL({e}, {_NULL})"


def _md5_of(parts: list[str]) -> str:
    return f"HASHBYTES('MD5', {(' + ' + _SEP + ' + ').join(parts)})"


def row_hash_expr(cols: list[dict], alias: str = "t") -> str:
    """binary(8) content hash over ``cols`` (chunked to stay under 8000 bytes)."""
    chunks, cur, size = [], [], 0
    for col in cols:
        n = _char_len(col) + 1
        if cur and size + n > _CHUNK_CHARS:
            chunks.append(cur)
            cur, size = [], 0
        cur.append(text_expr(col, alias))
        size += n
    if cur:
        chunks.append(cur)
    inner = " + ".join(_md5_of(c) for c in chunks)
    return f"CAST(SUBSTRING(HASHBYTES('MD5', {inner}), 1, 8) AS binary(8))"


def key_hash_expr(key_cols: list[dict], alias: str = "t") -> str:
    """binary(8) identity hash of a row's key."""
    return row_hash_expr(key_cols, alias)


def keyset_where(key_cols: list[dict], alias: str = "t") -> str:
    """Strictly-after predicate for keyset paging on a composite key:
    (k1 > ?) OR (k1 = ? AND k2 > ?) OR ...   -- params: see keyset_params."""
    ors = []
    for i, col in enumerate(key_cols):
        ands = [f"{alias}.{q(k['name'])} = ?" for k in key_cols[:i]]
        ands.append(f"{alias}.{q(col['name'])} > ?")
        ors.append("(" + " AND ".join(ands) + ")")
    return "(" + " OR ".join(ors) + ")"


def keyset_params(values: list) -> list:
    out = []
    for i in range(len(values)):
        out.extend(values[:i])
        out.append(values[i])
    return out


def store_filter(store_column: str | None, n_stores: int, alias: str = "t") -> str:
    """``t.[StoreName] IN (?, ?)`` for a store-scoped target, else ''."""
    if not store_column or n_stores <= 0:
        return ""
    return f"{alias}.{q(store_column)} IN ({', '.join('?' * n_stores)})"


def retention_filter(retention: tuple | None, alias: str = "t") -> str:
    """``t.[date_col] >= <today - N days>`` for a table with a retention window
    (old history is never sent to the remote), else ''. No bind params."""
    if not retention:
        return ""
    column, days = retention
    return f"{alias}.{q(column)} >= DATEADD(day, -{int(days)}, CAST(GETDATE() AS date))"


def pk_page_sql(table: str, cols: list[dict], key_cols: list[dict],
                has_cursor: bool, store_column: str | None = None,
                n_stores: int = 0, retention: tuple | None = None) -> str:
    """One keyset page of a PK table, filtered to rows whose hash differs from
    the target's ledger, plus the page's last row (rn = @n) so the caller can
    always advance the cursor.

    Params: page_size, [store names], [keyset params], target_id, table_id,
    page_size.
    """
    select_cols = ", ".join(f"t.{q(c['name'])}" for c in cols)
    order = ", ".join(f"t.{q(c['name'])}" for c in key_cols)
    preds = [store_filter(store_column, n_stores), retention_filter(retention)]
    if has_cursor:
        preds.append(keyset_where(key_cols))
    preds = [x for x in preds if x]
    where = f"WHERE {' AND '.join(preds)}" if preds else ""
    return (
        f"WITH p AS (SELECT TOP (?) {select_cols}, "
        f"{key_hash_expr(key_cols)} AS __ph, {row_hash_expr(cols)} AS __rh, "
        f"ROW_NUMBER() OVER (ORDER BY {order}) AS __rn "
        f"FROM [dbo].{q(table)} AS t {where} ORDER BY {order}) "
        f"SELECT p.*, l.rh AS __lrh FROM p LEFT JOIN {LEDGER} AS l "
        f"ON l.target_id = ? AND l.table_id = ? AND l.ph = p.__ph "
        f"WHERE l.rh IS NULL OR l.rh <> p.__rh OR p.__rn = ? ORDER BY p.__rn"
    )


def heap_groups_sql(table: str, cols: list[dict], key_cols: list[dict],
                    store_column: str | None = None, n_stores: int = 0,
                    retention: tuple | None = None) -> str:
    """Changed key-groups of a table without a primary key (full scan; such
    tables are small). A group = all source rows sharing the key; its hash is
    (sum of row hashes mod p, row count), so any edit/insert/removal inside a
    group changes it. Returns every row of the first @n changed groups.

    Params: [store names], page_size, target_id, table_id.
    """
    select_cols = ", ".join(f"t.{q(c['name'])}" for c in cols)
    preds = [x for x in (store_filter(store_column, n_stores), retention_filter(retention)) if x]
    where = f" WHERE {' AND '.join(preds)}" if preds else ""
    return (
        f"WITH r AS (SELECT {select_cols}, {key_hash_expr(key_cols)} AS __ph, "
        f"{row_hash_expr(cols)} AS __rh FROM [dbo].{q(table)} AS t{where}), "
        f"g AS (SELECT __ph, CAST(CAST(CAST(SUM(CAST(CAST(SUBSTRING(__rh, 1, 4) AS int) AS bigint)) "
        f"% 2147483647 AS int) AS binary(4)) + CAST(CAST(COUNT_BIG(*) AS int) AS binary(4)) AS binary(8)) AS __grh "
        f"FROM r GROUP BY __ph), "
        f"c AS (SELECT TOP (?) g.__ph, g.__grh FROM g LEFT JOIN {LEDGER} AS l "
        f"ON l.target_id = ? AND l.table_id = ? AND l.ph = g.__ph "
        f"WHERE l.rh IS NULL OR l.rh <> g.__grh ORDER BY g.__ph) "
        f"SELECT r.*, c.__grh FROM r JOIN c ON c.__ph = r.__ph ORDER BY r.__ph"
    )
