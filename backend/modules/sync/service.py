from .repository import (
    get_catalog_column,
    insert_catalog_column,
    update_catalog_column
)


def register_schema(payload):

    result = {
        "status": "success",
        "tables_processed": 0,
        "columns_processed": 0,
        "new_columns": 0,
        "updated_columns": 0
    }

    for table in payload.tables:

        result["tables_processed"] += 1

        for column in table.columns:

            result["columns_processed"] += 1

            row = {
                "schema_name": table.schema_name,
                "table_name": table.table_name,
                "column_name": column.column_name,
                "data_type": column.data_type,
                "max_length": column.max_length,
                "precision_value": column.precision_value,
                "scale_value": column.scale_value,
                "is_nullable": column.is_nullable,
                "is_identity": column.is_identity,
                "is_primary_key": column.is_primary_key,
                "ordinal_position": column.ordinal_position
            }

            exists = get_catalog_column(
                table.schema_name,
                table.table_name,
                column.column_name
            )

            if exists:
                update_catalog_column(row)
                result["updated_columns"] += 1
            else:
                insert_catalog_column(row)
                result["new_columns"] += 1

    return result