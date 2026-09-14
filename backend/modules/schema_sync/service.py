"""Dev -> Production schema comparison + DDL generation + apply.

Compare is always Dev(source, read-only) vs Production(target). Statements
are generated per the platform-owner's explicit choices for this tool:
  * missing tables/columns/indexes/constraints -> created (additive)
  * existing columns that differ in type/nullable/default -> FORCED to match
    Dev (ALTER COLUMN / replace default). Identity can't be altered in place
    on SQL Server, so identity differences are always flagged for manual
    review rather than attempted.
  * stored procedures / views / functions / triggers -> CREATE OR ALTER with
    Dev's exact body when missing or different from target.
  * tables that look like ad-hoc dev artifacts (timestamped *_Stage_xxxxxx
    tables, dated *_Backup_* tables, sysdiagrams) are never created in
    Production - they're internal scratch tables, not schema.
Apply runs each planned statement independently (autocommit) and keeps going
past individual failures so one bad statement doesn't block the rest of a
one-click run; every outcome is reported back to the caller.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from modules.schema_sync import repository
from modules.schema_sync.schemas import (
    CompareResult,
    DiffItem,
    PlannedStatement,
)

_ARTIFACT_PATTERNS = [
    re.compile(r"_Stage_[0-9a-fA-F]{6,}$"),
    re.compile(r"_Backup_?\d{4,}$", re.IGNORECASE),
    re.compile(r"^Products_DiscountBackup_\d+$", re.IGNORECASE),
    re.compile(r"^products_backup", re.IGNORECASE),
]


def _ci(s: str) -> str:
    return (s or "").lower()


def _is_artifact_table(name: str) -> bool:
    if _ci(name) == "sysdiagrams":
        return True
    return any(p.search(name) for p in _ARTIFACT_PATTERNS)


def q(schema: str, name: str) -> str:
    return f"[{schema}].[{name}]"


def _render_type(col: dict) -> str:
    dt = col["DataType"]
    ml = col["MaxLength"]
    pr = col["Precision"]
    sc = col["Scale"]
    if dt in ("nvarchar", "nchar"):
        if ml == -1:
            return f"{dt}(MAX)"
        return f"{dt}({ml // 2})"
    if dt in ("varchar", "char", "varbinary", "binary"):
        return f"{dt}(MAX)" if ml == -1 else f"{dt}({ml})"
    if dt in ("decimal", "numeric"):
        return f"{dt}({pr},{sc})"
    if dt in ("datetime2", "time", "datetimeoffset"):
        return f"{dt}({sc})"
    return dt


def _col_key(c: dict):
    return (c["SchemaName"], c["TableName"])


def _group_columns(rows: list[dict]) -> dict:
    out: dict = {}
    for r in rows:
        out.setdefault(_col_key(r), []).append(r)
    for k in out:
        out[k].sort(key=lambda r: r["ColumnOrder"])
    return out


def _group_pks(rows: list[dict]) -> dict:
    out: dict = {}
    for r in rows:
        k = (r["SchemaName"], r["TableName"])
        out.setdefault(k, {"name": r["PkName"], "cols": []})
        out[k]["cols"].append((r["ColumnOrder"], r["ColumnName"]))
    for k in out:
        out[k]["cols"] = [c for _, c in sorted(out[k]["cols"])]
    return out


def _group_uqs(rows: list[dict]) -> dict:
    out: dict = {}
    for r in rows:
        k = (r["SchemaName"], r["TableName"], r["UqName"])
        out.setdefault(k, []).append((r["ColumnOrder"], r["ColumnName"]))
    for k in out:
        out[k] = [c for _, c in sorted(out[k])]
    return out


def _group_checks(rows: list[dict]) -> dict:
    return {(r["SchemaName"], r["TableName"], r["CheckName"]): r["Definition"] for r in rows}


def _group_fks(rows: list[dict]) -> dict:
    out: dict = {}
    for r in rows:
        k = (r["SchemaName"], r["TableName"], r["FkName"])
        out.setdefault(k, []).append(r)
    for k in out:
        out[k].sort(key=lambda r: r["ColumnOrder"])
    return out


def _group_indexes(rows: list[dict]) -> dict:
    out: dict = {}
    for r in rows:
        k = (r["SchemaName"], r["TableName"], r["IndexName"])
        out.setdefault(k, {"meta": r, "key_cols": [], "inc_cols": []})
        entry = out[k]["inc_cols"] if r["IsIncluded"] else out[k]["key_cols"]
        entry.append((r["KeyOrdinal"] if not r["IsIncluded"] else r["ColumnOrder"], r["ColumnName"], bool(r["IsDescending"])))
    for k in out:
        out[k]["key_cols"].sort()
        out[k]["inc_cols"].sort()
    return out


def _normalize_sql(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _to_create_or_alter(definition: str) -> str:
    return re.sub(
        r"^\s*CREATE\s+(PROCEDURE|PROC|VIEW|FUNCTION|TRIGGER)\b",
        r"CREATE OR ALTER \1",
        definition,
        count=1,
        flags=re.IGNORECASE,
    )


def compare(source_conn: dict, target_conn: dict) -> CompareResult:
    src = repository.fetch_snapshot(source_conn)
    tgt = repository.fetch_snapshot(target_conn)

    dev_cols = _group_columns(src["columns"])
    prod_cols = _group_columns(tgt["columns"])
    prod_ci = {(_ci(s), _ci(t)): (s, t) for (s, t) in prod_cols}

    def prod_key(s, t):
        return prod_ci.get((_ci(s), _ci(t)))

    dev_pks = _group_pks(src["pks"])
    dev_uqs = _group_uqs(src["uqs"])
    prod_uq_names = {(_ci(s), _ci(t), _ci(c)) for (s, t, c) in _group_uqs(tgt["uqs"])}
    dev_checks = _group_checks(src["checks"])
    prod_check_names = {(_ci(s), _ci(t), _ci(c)) for (s, t, c) in _group_checks(tgt["checks"])}
    dev_fks = _group_fks(src["fks"])
    prod_fk_names = {_ci(r["FkName"]) for r in tgt["fks"]}
    dev_idx = _group_indexes(src["indexes"])
    prod_idx_names = {(_ci(s), _ci(t), _ci(i)) for (s, t, i) in _group_indexes(tgt["indexes"])}

    tables_missing: list[DiffItem] = []
    tables_only_target: list[DiffItem] = []
    tables_skipped: list[DiffItem] = []
    column_diffs: list[DiffItem] = []
    index_diffs: list[DiffItem] = []
    constraint_diffs: list[DiffItem] = []
    programmable_diffs: list[DiffItem] = []
    statements: list[PlannedStatement] = []
    seq = [0]

    def add_stmt(category, schema_name, object_name, description, sql):
        seq[0] += 1
        statements.append(PlannedStatement(
            seq=seq[0], category=category, schema_name=schema_name,
            object_name=object_name, description=description, sql=sql,
        ))

    create_tables = []
    skip_keys = set()
    common_tables = []
    for key in dev_cols:
        s, t = key
        if prod_key(s, t):
            common_tables.append(key)
            continue
        if _is_artifact_table(t):
            skip_keys.add((_ci(s), _ci(t)))
            tables_skipped.append(DiffItem(
                category="table", schema_name=s, object_name=t,
                detail="Dev-only scratch/backup artifact - not created in Production",
                severity="info",
            ))
        else:
            create_tables.append(key)

    def is_skip(s, t):
        return (_ci(s), _ci(t)) in skip_keys

    for (s, t) in sorted(set(prod_cols) - {prod_key(*k) for k in dev_cols if prod_key(*k)}):
        tables_only_target.append(DiffItem(
            category="table", schema_name=s, object_name=t,
            detail="Exists only in Production - left untouched, flagged for review",
            severity="warn",
        ))

    # ---- 1. CREATE TABLE for missing tables -------------------------------
    for key in sorted(create_tables):
        s, t = key
        cols = dev_cols[key]
        lines = []
        for c in cols:
            decl = f"    [{c['ColumnName']}] {_render_type(c)}"
            if c["IsIdentity"]:
                decl += " IDENTITY(1,1)"
            decl += " NOT NULL" if not c["IsNullable"] else " NULL"
            dd = (c.get("DefaultDefinition") or "").strip()
            if dd:
                decl += f" DEFAULT {dd}"
            lines.append(decl)
        pk = dev_pks.get(key)
        if pk:
            cols_sql = ", ".join(f"[{c}]" for c in pk["cols"])
            lines.append(f"    CONSTRAINT [{pk['name']}] PRIMARY KEY ({cols_sql})")
        body = ",\n".join(lines)
        sql = f"CREATE TABLE {q(s, t)} (\n{body}\n);"
        add_stmt("table", s, t, f"Create missing table {s}.{t}", sql)
        tables_missing.append(DiffItem(
            category="table", schema_name=s, object_name=t,
            detail=f"Missing in Production ({len(cols)} columns)", severity="warn",
        ))

    # ---- 2. Columns: add missing / force-alter differing ------------------
    for key in sorted(common_tables):
        s, t = key
        ps, pt = prod_key(s, t)
        pmap = {_ci(c["ColumnName"]): c for c in prod_cols[(ps, pt)]}
        for c in dev_cols[key]:
            name = c["ColumnName"]
            existing = pmap.get(_ci(name))
            if existing is None:
                decl = f"[{name}] {_render_type(c)}"
                decl += " NOT NULL" if not c["IsNullable"] else " NULL"
                dd = (c.get("DefaultDefinition") or "").strip()
                if dd:
                    decl += f" DEFAULT {dd}"
                sql = f"ALTER TABLE {q(ps, pt)} ADD {decl};"
                add_stmt("column", ps, pt, f"Add missing column {name}", sql)
                column_diffs.append(DiffItem(
                    category="column", schema_name=ps, object_name=f"{pt}.{name}",
                    detail="Missing in Production", severity="warn",
                ))
                continue

            dev_type = _render_type(c)
            prod_type = _render_type(existing)
            dev_null = bool(c["IsNullable"])
            prod_null = bool(existing["IsNullable"])
            dev_dd = (c.get("DefaultDefinition") or "").strip()
            prod_dd = (existing.get("DefaultDefinition") or "").strip()

            if bool(c["IsIdentity"]) != bool(existing["IsIdentity"]):
                constraint_diffs.append(DiffItem(
                    category="column", schema_name=ps, object_name=f"{pt}.{name}",
                    detail=f"IDENTITY differs (dev={bool(c['IsIdentity'])}, prod={bool(existing['IsIdentity'])}) "
                           f"- cannot be altered in place, requires manual table rebuild",
                    severity="destructive-skipped",
                ))
                continue

            if dev_type != prod_type or dev_null != prod_null:
                null_kw = "NULL" if dev_null else "NOT NULL"
                sql = f"ALTER TABLE {q(ps, pt)} ALTER COLUMN [{name}] {dev_type} {null_kw};"
                add_stmt(
                    "column-alter", ps, pt,
                    f"Alter {name}: {prod_type}{'' if prod_null else ' NOT NULL'} -> {dev_type}{'' if dev_null else ' NOT NULL'}",
                    sql,
                )
                column_diffs.append(DiffItem(
                    category="column", schema_name=ps, object_name=f"{pt}.{name}",
                    detail=f"Type/nullability differs: dev={dev_type} {'NULL' if dev_null else 'NOT NULL'} "
                           f"vs prod={prod_type} {'NULL' if prod_null else 'NOT NULL'} (forced)",
                    severity="destructive-skipped" if not prod_null and prod_type != dev_type else "warn",
                ))

            if dev_dd != prod_dd and dev_dd:
                drop_sql = ""
                # Existing default constraints aren't named in this snapshot; drop
                # by looking it up dynamically at apply time via sys.default_constraints.
                sql = (
                    f"DECLARE @dfname sysname = (SELECT dc.name FROM sys.default_constraints dc "
                    f"JOIN sys.columns col ON col.object_id = dc.parent_object_id AND col.column_id = dc.parent_column_id "
                    f"WHERE dc.parent_object_id = OBJECT_ID(N'{ps}.{pt}') AND col.name = N'{name}');\n"
                    f"IF @dfname IS NOT NULL EXEC('ALTER TABLE {q(ps, pt)} DROP CONSTRAINT [' + @dfname + ']');\n"
                    f"ALTER TABLE {q(ps, pt)} ADD DEFAULT {dev_dd} FOR [{name}];"
                )
                add_stmt("default", ps, pt, f"Replace default on {name}", sql)
                column_diffs.append(DiffItem(
                    category="column", schema_name=ps, object_name=f"{pt}.{name}",
                    detail=f"Default differs: dev=[{dev_dd}] prod=[{prod_dd}] (forced)", severity="warn",
                ))

    # ---- 3. Indexes (additive; skip PK/UQ backing) -------------------------
    for key in sorted(dev_idx):
        s, t, ixname = key
        if is_skip(s, t):
            continue
        meta = dev_idx[key]["meta"]
        if meta["IsPrimaryKey"] or meta["IsUniqueConstraint"]:
            continue
        if (_ci(s), _ci(t), _ci(ixname)) in prod_idx_names:
            continue
        tgt_key = prod_key(s, t) or (s, t)
        key_cols = dev_idx[key]["key_cols"]
        inc_cols = dev_idx[key]["inc_cols"]
        kc = ", ".join(f"[{c}]" + (" DESC" if desc else "") for _, c, desc in key_cols)
        uniq = "UNIQUE " if meta["IsUnique"] else ""
        ctype = "CLUSTERED" if meta["IndexType"] == "CLUSTERED" else "NONCLUSTERED"
        sql = f"CREATE {uniq}{ctype} INDEX [{ixname}] ON {q(*tgt_key)} ({kc})"
        if inc_cols:
            sql += " INCLUDE (" + ", ".join(f"[{c}]" for _, c, _ in inc_cols) + ")"
        sql += ";"
        add_stmt("index", tgt_key[0], f"{tgt_key[1]}.{ixname}", f"Create missing index {ixname}", sql)
        index_diffs.append(DiffItem(
            category="index", schema_name=tgt_key[0], object_name=f"{tgt_key[1]}.{ixname}",
            detail="Missing in Production", severity="warn",
        ))

    # ---- 4. Unique constraints ---------------------------------------------
    for key in sorted(dev_uqs):
        s, t, cn = key
        if is_skip(s, t):
            continue
        if (_ci(s), _ci(t), _ci(cn)) in prod_uq_names:
            continue
        tgt_key = prod_key(s, t) or (s, t)
        cols_sql = ", ".join(f"[{c}]" for c in dev_uqs[key])
        sql = f"ALTER TABLE {q(*tgt_key)} ADD CONSTRAINT [{cn}] UNIQUE ({cols_sql});"
        add_stmt("unique", tgt_key[0], f"{tgt_key[1]}.{cn}", f"Add missing unique constraint {cn}", sql)
        constraint_diffs.append(DiffItem(
            category="unique", schema_name=tgt_key[0], object_name=f"{tgt_key[1]}.{cn}",
            detail="Missing in Production", severity="warn",
        ))

    # ---- 5. Check constraints ----------------------------------------------
    for key in sorted(dev_checks):
        s, t, cn = key
        if is_skip(s, t):
            continue
        if (_ci(s), _ci(t), _ci(cn)) in prod_check_names:
            continue
        tgt_key = prod_key(s, t) or (s, t)
        sql = f"ALTER TABLE {q(*tgt_key)} WITH CHECK ADD CONSTRAINT [{cn}] CHECK {dev_checks[key]};"
        add_stmt("check", tgt_key[0], f"{tgt_key[1]}.{cn}", f"Add missing check constraint {cn}", sql)
        constraint_diffs.append(DiffItem(
            category="check", schema_name=tgt_key[0], object_name=f"{tgt_key[1]}.{cn}",
            detail="Missing in Production", severity="warn",
        ))

    # ---- 6. Foreign keys (last; both endpoints must exist/be created) -----
    for key in sorted(dev_fks):
        s, t, fkname = key
        if is_skip(s, t):
            continue
        if _ci(fkname) in prod_fk_names:
            continue
        rows = dev_fks[key]
        rs, rt = rows[0]["RefSchema"], rows[0]["RefTable"]
        if is_skip(rs, rt):
            continue
        child_key = prod_key(s, t) or (s, t)
        ref_key = prod_key(rs, rt) or (rs, rt)
        cc = ", ".join(f"[{r['ColumnName']}]" for r in rows)
        rc = ", ".join(f"[{r['RefColumn']}]" for r in rows)
        sql = (
            f"ALTER TABLE {q(*child_key)} WITH CHECK ADD CONSTRAINT [{fkname}] "
            f"FOREIGN KEY ({cc}) REFERENCES {q(*ref_key)} ({rc});"
        )
        add_stmt("foreign-key", child_key[0], f"{child_key[1]}.{fkname}", f"Add missing foreign key {fkname}", sql)
        constraint_diffs.append(DiffItem(
            category="foreign-key", schema_name=child_key[0], object_name=f"{child_key[1]}.{fkname}",
            detail="Missing in Production", severity="warn",
        ))

    # ---- 7. Programmable objects (CREATE OR ALTER) -------------------------
    prod_prog = {(_ci(p["SchemaName"]), _ci(p["ObjectName"])): p for p in tgt["programmables"]}
    for p in src["programmables"]:
        key = (_ci(p["SchemaName"]), _ci(p["ObjectName"]))
        existing = prod_prog.get(key)
        kind = {"SQL_STORED_PROCEDURE": "procedure", "VIEW": "view",
                "SQL_SCALAR_FUNCTION": "function", "SQL_TABLE_VALUED_FUNCTION": "function",
                "SQL_INLINE_TABLE_VALUED_FUNCTION": "function", "SQL_TRIGGER": "trigger"}.get(p["TypeDesc"], "object")
        if kind == "trigger" and p.get("ParentTableName") and is_skip(p["SchemaName"], p["ParentTableName"]):
            continue
        if existing is None:
            sql = _to_create_or_alter(p["Definition"])
            add_stmt(kind, p["SchemaName"], p["ObjectName"], f"Create missing {kind} {p['ObjectName']}", sql)
            programmable_diffs.append(DiffItem(
                category=kind, schema_name=p["SchemaName"], object_name=p["ObjectName"],
                detail="Missing in Production", severity="warn",
            ))
        elif _normalize_sql(existing["Definition"]) != _normalize_sql(p["Definition"]):
            sql = _to_create_or_alter(p["Definition"])
            add_stmt(kind, p["SchemaName"], p["ObjectName"], f"Update {kind} {p['ObjectName']} to match Dev", sql)
            programmable_diffs.append(DiffItem(
                category=kind, schema_name=p["SchemaName"], object_name=p["ObjectName"],
                detail="Definition differs from Dev (will be overwritten)", severity="warn",
            ))

    summary = {
        "tables_missing": len(tables_missing),
        "tables_only_in_target": len(tables_only_target),
        "tables_skipped_as_artifacts": len(tables_skipped),
        "column_diffs": len(column_diffs),
        "index_diffs": len(index_diffs),
        "constraint_diffs": len(constraint_diffs),
        "programmable_diffs": len(programmable_diffs),
        "total_statements": len(statements),
    }

    return CompareResult(
        generated_at=datetime.now(timezone.utc).isoformat(),
        tables_missing_in_target=tables_missing,
        tables_only_in_target=tables_only_target,
        tables_skipped_as_artifacts=tables_skipped,
        column_diffs=column_diffs,
        index_diffs=index_diffs,
        constraint_diffs=constraint_diffs,
        programmable_diffs=programmable_diffs,
        statements=statements,
        summary=summary,
    )


def apply(target_conn: dict, statements: list) -> list[dict]:
    """Best-effort apply: runs every statement even if an earlier one fails,
    so a single bad statement (e.g. a column-alter blocked by data that can't
    convert) never blocks unrelated tables/indexes/procs from going through."""
    results = []
    for stmt in statements:
        try:
            repository.execute_ddl(target_conn, stmt.sql)
            results.append({"seq": stmt.seq, "category": stmt.category, "object_name": stmt.object_name,
                             "ok": True, "message": "Applied"})
        except Exception as exc:  # noqa: BLE001 - surfaced to the caller, not swallowed
            results.append({"seq": stmt.seq, "category": stmt.category, "object_name": stmt.object_name,
                             "ok": False, "message": str(exc)})
    return results
