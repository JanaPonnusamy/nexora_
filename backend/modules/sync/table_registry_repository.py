from config.database import get_connection


def populate_table_registry():

    conn = get_connection()

    try:

        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                COUNT(DISTINCT table_name)
            FROM sync.sync_schema_catalog
            """
        )

        tables_discovered = cursor.fetchone()[0]

        cursor.execute(
            """
            INSERT INTO dbo.sync_table_registry
            (
                tenant_id,
                table_name,
                sync_order,
                chunk_enabled,
                refresh_enabled,
                is_active
            )
            SELECT
                '00000000-0000-0000-0000-000000000000',
                src.table_name,
                999,
                1,
                1,
                1
            FROM
            (
                SELECT DISTINCT
                    table_name
                FROM sync.sync_schema_catalog
            ) src
            LEFT JOIN dbo.sync_table_registry trg
                ON trg.table_name = src.table_name
            WHERE trg.table_name IS NULL
            """
        )

        new_tables = cursor.rowcount

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM dbo.sync_table_registry
            """
        )

        total_registry_tables = cursor.fetchone()[0]

        conn.commit()

        return {
            "status": "success",
            "tables_discovered": tables_discovered,
            "new_tables": new_tables,
            "existing_tables": (
                tables_discovered - new_tables
            ),
            "total_registry_tables": total_registry_tables
        }

    except Exception:

        conn.rollback()
        raise

    finally:

        conn.close()
