class SchemaCatalogBuilder:

    def build(self, tables, columns, primary_keys, identity_columns):

        return {
            "tables": tables,
            "columns": columns,
            "primary_keys": primary_keys,
            "identity_columns": identity_columns
        }
