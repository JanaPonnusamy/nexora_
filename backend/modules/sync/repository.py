from config.database import get_connection


def get_catalog_column(
    schema_name,
    table_name,
    column_name
):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT catalog_id
        FROM sync.sync_schema_catalog
        WHERE schema_name=?
          AND table_name=?
          AND column_name=?
        """,
        (
            schema_name,
            table_name,
            column_name
        )
    )

    row = cur.fetchone()

    conn.close()

    return row


def insert_catalog_column(column):

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
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
            first_discovered_at,
            last_discovered_at,
            is_active
        )
        VALUES
        (
            ?,?,?,?,?,?,?,?,?,?,
            ?,GETDATE(),GETDATE(),1
        )
        """,
        (
            column["schema_name"],
            column["table_name"],
            column["column_name"],
            column["data_type"],
            column["max_length"],
            column["precision_value"],
            column["scale_value"],
            int(column["is_nullable"]),
            int(column["is_identity"]),
            int(column["is_primary_key"]),
            column["ordinal_position"]
        )
    )

    conn.commit()
    conn.close()


def update_catalog_column(column):

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE sync.sync_schema_catalog
        SET
            data_type=?,
            max_length=?,
            precision_value=?,
            scale_value=?,
            is_nullable=?,
            is_identity=?,
            is_primary_key=?,
            ordinal_position=?,
            last_discovered_at=GETDATE()
        WHERE
            schema_name=?
            AND table_name=?
            AND column_name=?
        """,
        (
            column["data_type"],
            column["max_length"],
            column["precision_value"],
            column["scale_value"],
            int(column["is_nullable"]),
            int(column["is_identity"]),
            int(column["is_primary_key"]),
            column["ordinal_position"],
            column["schema_name"],
            column["table_name"],
            column["column_name"]
        )
    )

    conn.commit()
    conn.close()
