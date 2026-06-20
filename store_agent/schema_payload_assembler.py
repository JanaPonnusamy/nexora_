class SchemaPayloadAssembler:

    def assemble(self, store_id, database_name, catalog):

        return {
            "store_id": store_id,
            "database_name": database_name,
            "tables": catalog.get("tables", [])
        }
