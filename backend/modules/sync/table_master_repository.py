from config.database import get_connection


def promote_table_master():

    conn = get_connection()

    try:

        cursor = conn.cursor()

        cursor.execute(
            '''
            SELECT COUNT(*)
            FROM dbo.sync_table_registry
            '''
        )

        registry_tables = cursor.fetchone()[0]

        cursor.execute(
            '''
            INSERT INTO sync.sync_table_master
            (
                sync_table_id,
                table_name,
                is_active,
                sync_mode,
                watermark_column,
                window_days,
                window_months,
                custom_where,
                sync_order,
                created_at
            )
            SELECT
                NEWID(),
                r.table_name,
                0,
                'UPSERT',
                NULL,
                NULL,
                NULL,
                NULL,
                r.sync_order,
                GETDATE()
            FROM dbo.sync_table_registry r
            LEFT JOIN sync.sync_table_master m
                ON m.table_name = r.table_name
            WHERE m.table_name IS NULL
            '''
        )

        promoted_tables = cursor.rowcount

        cursor.execute(
            '''
            SELECT COUNT(*)
            FROM sync.sync_table_master
            '''
        )

        total_master_tables = cursor.fetchone()[0]

        conn.commit()

        return {
            "status": "success",
            "registry_tables": registry_tables,
            "promoted_tables": promoted_tables,
            "existing_tables": (
                registry_tables - promoted_tables
            ),
            "total_master_tables": total_master_tables
        }

    except Exception:

        conn.rollback()
        raise

    finally:

        conn.close()
