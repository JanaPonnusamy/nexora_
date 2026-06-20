from modules.sync.repository import (
    bulk_register_schema_catalog
)


def register_schema(payload):

    rows = []

    if isinstance(payload, list):

        for row in payload:

            rows.append(
                {
                    "schema_name": row["schema_name"],
                    "table_name": row["table_name"],
                    "column_name": row["column_name"],
                    "data_type": row["data_type"],
                    "max_length": row.get("max_length"),
                    "precision_value": row.get("precision_value"),
                    "scale_value": row.get("scale_value"),
                    "is_nullable": row.get("is_nullable", False),
                    "is_identity": row.get("is_identity", False),
                    "is_primary_key": row.get("is_primary_key", False),
                    "ordinal_position": row["ordinal_position"],
                    "first_discovered_store_id": row.get(
                        "first_discovered_store_id"
                    )
                }
            )

    result = bulk_register_schema_catalog(rows)

    return {
        "status": "success",
        "columns_processed": result["total"],
        "new_columns": result["inserted"],
        "updated_columns": result["updated"]
    }