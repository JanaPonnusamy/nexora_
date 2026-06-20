from config.database import get_connection


def bulk_register_schema_catalog(rows):

    conn = get_connection()

    try:

        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE #SchemaCatalogStage
            (
                schema_name varchar(128) NOT NULL,
                table_name varchar(128) NOT NULL,
                column_name varchar(128) NOT NULL,
                data_type varchar(100) NULL,
                max_length int NULL,
                precision_value int NULL,
                scale_value int NULL,
                is_nullable bit NULL,
                is_identity bit NULL,
                is_primary_key bit NULL,
                ordinal_position int NULL,
                first_discovered_store_id uniqueidentifier NULL
            )
            """
        )

        stage_rows = []

        for row in rows:

            stage_rows.append(
                (
                    row["schema_name"],
                    row["table_name"],
                    row["column_name"],
                    row["data_type"],
                    row["max_length"],
                    row["precision_value"],
                    row["scale_value"],
                    row["is_nullable"],
                    row["is_identity"],
                    row["is_primary_key"],
                    row["ordinal_position"],
                    row.get("first_discovered_store_id")
                )
            )

        cursor.fast_executemany = True

        cursor.executemany(
            """
            INSERT INTO #SchemaCatalogStage
            (
                schema_name,
                table_name,
                column_name,
                data_type,
                max_length,
                precision_value,
                scale_value,
                is_nullable,
                is_identity,
                is_primary_key,
                ordinal_position,
                first_discovered_store_id
            )
            VALUES
            (
                ?,?,?,?,?,?,?,?,?,?,?,?
            )
            """,
            stage_rows
        )

        cursor.execute(
            """
            UPDATE target
            SET
                target.data_type = stage.data_type,
                target.max_length = stage.max_length,
                target.precision_value = stage.precision_value,
                target.scale_value = stage.scale_value,
                target.is_nullable = stage.is_nullable,
                target.is_identity = stage.is_identity,
                target.is_primary_key = stage.is_primary_key,
                target.ordinal_position = stage.ordinal_position,
                target.last_discovered_at = GETDATE()
            FROM sync.sync_schema_catalog target
            INNER JOIN #SchemaCatalogStage stage
                ON target.schema_name = stage.schema_name
               AND target.table_name = stage.table_name
               AND target.column_name = stage.column_name
            """
        )

        updated_rows = cursor.rowcount

        cursor.execute(
            """
            INSERT INTO sync.sync_schema_catalog
            (
                schema_name,
                table_name,
                column_name,
                data_type,
                max_length,
                precision_value,
                scale_value,
                is_nullable,
                is_identity,
                is_primary_key,
                ordinal_position,
                first_discovered_store_id,
                first_discovered_at,
                last_discovered_at,
                is_active
            )
            SELECT
                stage.schema_name,
                stage.table_name,
                stage.column_name,
                stage.data_type,
                stage.max_length,
                stage.precision_value,
                stage.scale_value,
                stage.is_nullable,
                stage.is_identity,
                stage.is_primary_key,
                stage.ordinal_position,
                stage.first_discovered_store_id,
                GETDATE(),
                GETDATE(),
                1
            FROM #SchemaCatalogStage stage
            LEFT JOIN sync.sync_schema_catalog target
                ON target.schema_name = stage.schema_name
               AND target.table_name = stage.table_name
               AND target.column_name = stage.column_name
            WHERE target.catalog_id IS NULL
            """
        )

        inserted_rows = cursor.rowcount

        cursor.execute(
            """
            DROP TABLE #SchemaCatalogStage
            """
        )

        conn.commit()

        return {
            "inserted": inserted_rows,
            "updated": updated_rows,
            "total": len(rows)
        }

    except Exception:

        conn.rollback()
        raise

    finally:

        conn.close()