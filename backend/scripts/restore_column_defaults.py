"""Restore DEFAULT constraints that the database dump dropped.

`nexora_platform_dump (1).sql` was generated without column defaults — the file
contains the word DEFAULT zero times — so any database restored from it has
**1 default constraint across 94 tables**. The application was written against
the module migrations, which do declare defaults, so every insert that relies on
one fails with a NOT NULL violation.

The first one this surfaced through is document upload:

    IntegrityError: Cannot insert the value NULL into column 'import_guid',
    table 'nexora_platform.dbo.doc_import'; column does not allow nulls.

`repository.create_import` supplies 9 columns and lets the schema default the
other 13 (`import_guid`, the `is_*` flags, `validation_status`, `uploaded_at`,
`created_at`). With no defaults present, the insert cannot succeed — which means
mobile document capture cannot work at all against such a database.

This script reads the declared defaults back out of a migration file and emits
the ALTER TABLE statements that put them back. It prints them and stops unless
`--apply` is passed, because it changes a live schema and the parse is a
best-effort read of hand-written SQL rather than a guarantee.

    # see what it would do
    backend/.venv/bin/python scripts/restore_column_defaults.py \
        modules/document_extraction/sql/0001_document_extraction_tables.sql

    # actually do it
    ... --apply

Only columns that are currently missing a default are touched; existing
constraints are left alone, so it is safe to re-run.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent

# CREATE TABLE dbo.<name> ( ... )  — captures the table and its column block.
TABLE_RE = re.compile(
    r'CREATE\s+TABLE\s+dbo\.(\w+)\s*\((.*?)\n\s*\)\s*;',
    re.IGNORECASE | re.DOTALL,
)

# <column> <type...> DEFAULT <expr>  — the expression runs to the next comma
# that is not inside parentheses, or to end of line.
COLUMN_DEFAULT_RE = re.compile(
    r'^\s*(\w+)\s+.*?\bDEFAULT\s+(.+?)\s*(?:,\s*)?$',
    re.IGNORECASE,
)


def strip_comments(sql: str) -> str:
    """Removes SQL comments before parsing.

    Not cosmetic. These migrations annotate columns heavily, and a trailing
    comment lands inside the default expression:

        is_excluded BIT NOT NULL DEFAULT 0,   /* kept, not deleted */

    would otherwise yield `DEFAULT 0, /* kept, not deleted */`, and a block
    comment spanning lines produced `DEFAULT */` — a statement that would have
    failed against the server, or worse, not.
    """
    sql = re.sub(r'/\*.*?\*/', '', sql, flags=re.DOTALL)
    return re.sub(r'--[^\n]*', '', sql)


def parse_defaults(sql: str) -> dict[str, dict[str, str]]:
    """{table: {column: default_expression}} as declared in the migration."""
    found: dict[str, dict[str, str]] = {}

    for table, body in TABLE_RE.findall(strip_comments(sql)):
        columns: dict[str, str] = {}
        for line in body.splitlines():
            stripped = line.strip()
            # Skip table-level constraint lines: they can contain the word
            # DEFAULT inside a name without declaring a column default.
            if re.match(
                r'^(CONSTRAINT|PRIMARY|FOREIGN|UNIQUE|CHECK|INDEX)\b',
                stripped,
                re.IGNORECASE,
            ):
                continue
            match = COLUMN_DEFAULT_RE.match(stripped)
            if not match:
                continue
            column, expression = match.group(1), match.group(2).strip()
            # A trailing inline constraint (e.g. "DEFAULT 0 NOT NULL") must not
            # be swallowed into the expression.
            expression = re.sub(
                r'\s+(NOT\s+NULL|NULL|PRIMARY\s+KEY|UNIQUE)\s*$',
                '',
                expression,
                flags=re.IGNORECASE,
            ).strip().rstrip(',')
            if expression:
                columns[column] = expression
        if columns:
            found[table] = columns

    return found


def missing_defaults(cursor, table: str, columns: dict[str, str]) -> list[str]:
    """The subset of [columns] that currently has no default constraint."""
    cursor.execute(
        """
        SELECT c.name
        FROM sys.columns c
        LEFT JOIN sys.default_constraints dc
          ON dc.parent_object_id = c.object_id
         AND dc.parent_column_id = c.column_id
        WHERE c.object_id = OBJECT_ID('dbo.' + ?)
          AND dc.definition IS NULL
        """,
        (table,),
    )
    present = {row[0] for row in cursor.fetchall()}
    return [c for c in columns if c in present]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        'sql_file',
        type=Path,
        help='migration file to read declared defaults from',
    )
    parser.add_argument(
        '--apply',
        action='store_true',
        help='execute the statements instead of only printing them',
    )
    args = parser.parse_args()

    path = args.sql_file if args.sql_file.is_absolute() else BACKEND_DIR / args.sql_file
    if not path.exists():
        print(f'{path} not found', file=sys.stderr)
        return 1

    declared = parse_defaults(path.read_text(encoding='utf-8'))
    if not declared:
        print(f'No column defaults declared in {path.name}.')
        return 0

    sys.path.insert(0, str(BACKEND_DIR))
    from config.database import get_connection

    conn = get_connection()
    statements: list[str] = []
    try:
        cursor = conn.cursor()
        for table, columns in sorted(declared.items()):
            cursor.execute(
                "SELECT OBJECT_ID('dbo.' + ?)",
                (table,),
            )
            if cursor.fetchone()[0] is None:
                print(f'-- dbo.{table}: not present in this database, skipped')
                continue

            gaps = missing_defaults(cursor, table, columns)
            if not gaps:
                print(f'-- dbo.{table}: all {len(columns)} defaults already present')
                continue

            for column in gaps:
                # Constraint named deterministically so a re-run is idempotent
                # and so the origin of the constraint is obvious in sys.objects.
                statements.append(
                    f'ALTER TABLE dbo.{table} ADD CONSTRAINT '
                    f'DF_{table}_{column} DEFAULT {columns[column]} FOR {column};'
                )

        if not statements:
            print('\nNothing to do — every declared default is already in place.')
            return 0

        print(f'\n-- {len(statements)} constraint(s) to add:\n')
        for statement in statements:
            print(statement)

        if not args.apply:
            print('\nDry run. Re-run with --apply to execute.')
            return 0

        for statement in statements:
            cursor.execute(statement)
        conn.commit()
        print(f'\nApplied {len(statements)} constraint(s).')
        return 0
    finally:
        conn.close()


if __name__ == '__main__':
    raise SystemExit(main())
